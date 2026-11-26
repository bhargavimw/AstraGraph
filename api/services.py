"""Business logic behind the API, built on the existing astragraph package.

Nothing here reimplements astronomy or vision: it calls the same modules the
Streamlit app uses (pipeline, world_model, academy, synthetic) and converts
their results into the API's response models.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from itertools import islice
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

import cv2
import numpy as np
from numpy.typing import NDArray
from skyfield import almanac
from skyfield.api import Star, load, wgs84

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "app"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from astragraph.academy import AstronomyAcademy, check_quiz_answer, normalize_edges, same_shape  # noqa: E402
from astragraph.constellation_db import ConstellationDB, load_config, resolve_path  # noqa: E402
from astragraph.geometry import mean_sky_position  # noqa: E402
from astragraph.pipeline import FrameReport, PipelineConfig, SkyPipeline  # noqa: E402
from astragraph.synthetic import demo_sky_clip  # noqa: E402
from astragraph.world_model import SkyWorldModel, WorldModelConfig, load_ephemeris  # noqa: E402
from tonight import tonight_summary  # noqa: E402

from api import schemas  # noqa: E402

CONFIG_PATH = ROOT / "config.yaml"
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
MAX_WIDTH = 1280
DEMO_WIDTH, DEMO_HEIGHT, DEMO_FRAMES = 960, 720, 120


@lru_cache(maxsize=1)
def timescale():  # noqa: ANN201 - skyfield Timescale
    return load.timescale(builtin=True)  # bundled data, works offline


def compass(azimuth: float) -> str:
    return COMPASS[int(((azimuth % 360) + 22.5) // 45) % 8]


def iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------ resources
@dataclass(frozen=True)
class Resources:
    db: ConstellationDB
    model: SkyWorldModel
    academy: AstronomyAcademy
    pipeline_config: PipelineConfig
    colors: dict[str, float]
    catalog_names: frozenset[str]


@lru_cache(maxsize=1)
def resources() -> Resources:
    config = load_config(CONFIG_PATH)
    db = ConstellationDB.from_config(CONFIG_PATH)
    db.load()
    section = config.get("world_model") or {}
    catalog = resolve_path(section.get("star_catalog", "data/bright_stars.csv"), relative_to=CONFIG_PATH)
    model = SkyWorldModel(catalog, config=WorldModelConfig.from_mapping(section), constellation_db=db)
    colors = json.loads((ROOT / "api" / "data" / "star_colors.json").read_text(encoding="utf-8"))
    return Resources(
        db=db,
        model=model,
        academy=AstronomyAcademy(db),
        pipeline_config=PipelineConfig.from_mapping(config),
        colors={str(k): float(v) for k, v in colors.items()},
        catalog_names=frozenset(s.name for s in model.catalog),
    )


def zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception as exc:  # zoneinfo raises several types
        raise ValueError(f"Unknown time zone: {tz_name!r}") from exc


def validate_location(lat: float, lon: float) -> None:
    if not -90 <= lat <= 90:
        raise ValueError("lat must be between -90 and 90")
    if not -180 <= lon <= 180:
        raise ValueError("lon must be between -180 and 180")


# ---------------------------------------------------------------------- frames
@dataclass
class Session:
    pipeline: SkyPipeline
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_used: float = field(default_factory=time.monotonic)


class SessionStore:
    """In-memory camera sessions (each keeps its own tracker state), with expiry."""

    def __init__(self, max_sessions: int, ttl_seconds: float) -> None:
        self.max_sessions = max_sessions
        self.ttl = ttl_seconds
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> Session:
        now = time.monotonic()
        with self._lock:
            for key in [k for k, s in self._sessions.items() if now - s.last_used > self.ttl]:
                del self._sessions[key]
            session = self._sessions.get(session_id)
            if session is None:
                if len(self._sessions) >= self.max_sessions:
                    oldest = min(self._sessions, key=lambda k: self._sessions[k].last_used)
                    del self._sessions[oldest]
                res = resources()
                session = Session(SkyPipeline(res.db, res.pipeline_config))
                self._sessions[session_id] = session
            session.last_used = now
            return session

    def __len__(self) -> int:
        return len(self._sessions)


SESSIONS = SessionStore(
    max_sessions=int(os.environ.get("ASTRAGRAPH_MAX_SESSIONS", "50")),
    ttl_seconds=float(os.environ.get("ASTRAGRAPH_SESSION_TTL", "600")),
)


def decode_image(data: bytes) -> NDArray[np.uint8]:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode the image; send a JPEG or PNG")
    return image


def downscale(frame: NDArray[np.uint8], max_width: int = MAX_WIDTH) -> tuple[NDArray[np.uint8], float]:
    """Peak-preserving downscale (max filter first) so faint stars survive."""
    if frame.shape[1] <= max_width:
        return frame, 1.0
    scale = max_width / frame.shape[1]
    k = max(1, int(math.ceil(1.0 / scale)))
    if k > 1:
        frame = cv2.dilate(frame, np.ones((k, k), dtype=np.uint8))
    size = (max_width, int(round(frame.shape[0] * scale)))
    return cv2.resize(frame, size, interpolation=cv2.INTER_AREA), scale


def frame_response(report: FrameReport, pipeline: SkyPipeline, scale: float,
                   width: int, height: int, elapsed_ms: float) -> schemas.FrameResponse:
    """Convert a pipeline report to the API shape, in the sent image's pixels."""
    inv = 1.0 / scale
    satellites = {s.track_id for s in report.satellites}
    anomalies = set(report.anomalies)
    tracks = {t.id: t for t in report.tracks}

    stars = [
        schemas.FrameStar(id=t.id, x=t.x * inv, y=t.y * inv,
                          r=(4.0 + max(0.0, t.brightness - 180.0) / 25.0) * inv,
                          brightness=t.brightness)
        for t in report.tracks
        if t.visible and t.id not in satellites and t.id not in anomalies
    ]

    constellations, ghosts = [], []
    for match in report.constellations:
        lines = [(a[0] * inv, a[1] * inv, b[0] * inv, b[1] * inv) for a, b in match.line_segments]
        xs = [v for line in lines for v in (line[0], line[2])]
        ys = [v for line in lines for v in (line[1], line[3])]
        constellations.append(schemas.FrameConstellation(
            name=match.constellation or "",
            confidence=round(match.confidence, 3),
            matched=match.matched_nodes,
            total=match.total_nodes,
            lines=lines,
            label=((min(xs) + max(xs)) / 2 if xs else 0.0, min(ys) if ys else 0.0),
            stars=[schemas.FrameConstellationStar(id=i, name=n) for i, n in sorted(match.mapping.items())],
            partial=bool(match.ghost_positions),
        ))
        for name, (gx, gy) in match.ghost_positions.items():
            ghosts.append(schemas.FrameGhost(name=name, x=gx * inv, y=gy * inv, r=8.0 * inv))

    sat_out = []
    for sat in report.satellites:
        track = tracks.get(sat.track_id)
        trail = [(x * inv, y * inv) for x, y in (track.trajectory[-20:] if track else [])]
        vx, vy = pipeline.temporal.sky_velocity(track) if track else (0.0, 0.0)
        deg = sat.degrees_per_second is not None
        sat_out.append(schemas.FrameSatellite(
            id=sat.track_id, x=sat.x * inv, y=sat.y * inv, vx=vx * inv, vy=vy * inv,
            speed=round(sat.degrees_per_second if deg else sat.pixels_per_second * inv, 3),
            speed_unit="deg/s" if deg else "px/s",
            direction=sat.heading,  # type: ignore[arg-type]
            trail=trail,
        ))

    anomaly_out = [
        schemas.FrameAnomaly(id=i, x=tracks[i].x * inv, y=tracks[i].y * inv,
                             label="Not in catalog — possibly a planet")
        for i in report.anomalies if i in tracks
    ]
    events = [schemas.FrameEvent(type=e.type.value, id=int(e.args.get("id", -1))) for e in report.events]
    return schemas.FrameResponse(
        stars=stars, constellations=constellations, ghosts=ghosts, satellites=sat_out,
        anomalies=anomaly_out, events=events,
        meta=schemas.FrameMeta(width=width, height=height, frame_index=report.frame_idx,
                               processing_ms=round(elapsed_ms, 1)),
    )


def process_frame(session_id: str, data: bytes) -> schemas.FrameResponse:
    started = time.perf_counter()
    image = decode_image(data)
    height, width = image.shape[:2]
    small, scale = downscale(image)
    session = SESSIONS.get(session_id)
    with session.lock:  # frames of one session are processed in order
        report = session.pipeline.process(small)
        return frame_response(report, session.pipeline, scale, width, height,
                              (time.perf_counter() - started) * 1000)


# -------------------------------------------------------------------------- sky
def moon_model(moment: datetime, lat: float, lon: float) -> schemas.Moon:
    info = resources().model.moon_info(moment, lat, lon)
    return schemas.Moon(
        phase_name=info["phase_name"],
        phase_degrees=round(info["phase_degrees"], 2),
        illumination=round(info["illuminated"], 4),
        waxing=info["phase_degrees"] < 180.0,
        altitude=round(info["altitude"], 2),
    )


def sky(lat: float, lon: float, tz_name: str, offset_hours: float,
        at: datetime | None = None) -> schemas.SkyResponse:
    validate_location(lat, lon)
    tz = zone(tz_name)
    res = resources()
    moment = (at or datetime.now(timezone.utc)) + timedelta(hours=offset_hours)
    limit = res.model.config.min_altitude

    stars = [
        schemas.SkyStar(name=s.name, az=round(s.azimuth, 3), alt=round(s.altitude, 3),
                        magnitude=s.magnitude, ci=res.colors.get(s.name))
        for s in res.model.get_all_stars(moment, lat, lon) if s.altitude > -2
    ]
    constellations = []
    for name in res.db.list_constellations():
        graph = res.db[name]
        nodes = list(graph.nodes)
        positions = res.model.altaz_many([graph.nodes[n]["ra"] for n in nodes],
                                         [graph.nodes[n]["dec"] for n in nodes], moment, lat, lon)
        az, alt = res.model.get_constellation_position(name, moment, lat, lon)
        constellations.append(schemas.SkyConstellation(
            name=name,
            abbreviation=str(graph.graph.get("abbreviation", "")),
            az=round(az, 3), alt=round(alt, 3), direction=compass(az),  # type: ignore[arg-type]
            visible=alt > limit,
            stars=[schemas.SkyStar(name=n, az=round(a, 3), alt=round(h, 3),
                                   magnitude=float(graph.nodes[n]["magnitude"]), ci=res.colors.get(n))
                   for n, (a, h) in zip(nodes, positions)],
            lines=[(str(a), str(b)) for a, b in graph.edges],
        ))
    return schemas.SkyResponse(
        time_utc=iso(moment) or "",
        time_local=moment.astimezone(tz).isoformat(timespec="seconds"),
        tz=tz.key, lat=lat, lon=lon,
        sun_altitude=round(res.model.sun_altitude(moment, lat, lon), 3),
        darkness=res.model.sky_darkness(moment, lat, lon),  # type: ignore[arg-type]
        moon=moon_model(moment, lat, lon),
        stars=stars,
        constellations=constellations,
    )


def tonight(lat: float, lon: float, tz_name: str, at: datetime | None = None) -> schemas.TonightResponse:
    validate_location(lat, lon)
    tz = zone(tz_name)
    res = resources()
    now = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    night = tonight_summary(res.model, res.db, lat, lon, tz, now=now)

    darkness: schemas.DarknessDark | schemas.DarknessLight | schemas.DarknessNever
    if night.never_dark:
        darkness = schemas.DarknessNever()
    elif night.dark_now and night.dawn is not None:
        darkness = schemas.DarknessDark(minutes_until_dawn=max(0, int((night.dawn - now).total_seconds() // 60)))
    elif night.dusk is not None:
        darkness = schemas.DarknessLight(minutes_until_dark=max(0, int((night.dusk - now).total_seconds() // 60)))
    else:
        darkness = schemas.DarknessNever()
    best = night.best
    return schemas.TonightResponse(
        darkness=darkness,
        dusk_utc=iso(night.dusk), dawn_utc=iso(night.dawn),
        moon=moon_model(night.viewing_time, lat, lon),
        best=None if best is None else schemas.TonightBest(
            name=best.name, altitude=round(best.altitude, 1), azimuth=round(best.azimuth, 1),
            direction=best.direction),  # type: ignore[arg-type]
        brightest_stars=list(night.bright_stars),
        up_tonight=[schemas.TonightUp(name=c.name, direction=c.direction)  # type: ignore[arg-type]
                    for c in night.constellations],
    )


# --------------------------------------------------------------- constellations
def chart_stars(name: str) -> list[schemas.ChartStar]:
    res = resources()
    graph = res.db[name]
    out = []
    for star in graph.nodes:
        facts = res.academy.get_star_facts(star)
        out.append(schemas.ChartStar(
            name=star,
            designation=str(graph.nodes[star].get("designation", "")),
            ra=float(graph.nodes[star]["ra"]), dec=float(graph.nodes[star]["dec"]),
            magnitude=float(graph.nodes[star]["magnitude"]),
            ci=res.colors.get(star),
            distance_ly=facts.get("distance_ly"),
            fact=facts.get("fact"),
        ))
    return out


def constellation_list() -> list[schemas.ConstellationSummary]:
    res = resources()
    return [
        schemas.ConstellationSummary(
            name=name,
            abbreviation=str(res.db[name].graph.get("abbreviation", "")),
            stars=chart_stars(name),
            lines=[(str(a), str(b)) for a, b in res.db[name].edges],
        )
        for name in res.db.list_constellations()
    ]


def find_constellation(name: str) -> str:
    res = resources()
    for known in res.db.list_constellations():
        if known.lower() == name.lower():
            return known
    raise KeyError(name)


def rise_transit_set(name: str, lat: float, lon: float, tz: ZoneInfo,
                     now: datetime) -> schemas.RiseTransitSet:
    """Tonight's rise, highest point (transit) and set for a constellation's centre."""
    res = resources()
    graph = res.db[name]
    ra, dec = mean_sky_position([graph.nodes[n]["ra"] for n in graph.nodes],
                                [graph.nodes[n]["dec"] for n in graph.nodes])
    day: date = now.astimezone(tz).date()
    rise, set_ = res.model.get_constellation_rise_set(name, day, lat, lon, tz=tz)
    if rise is not None and (set_ is None or set_ < rise):
        set_ = res.model.get_constellation_rise_set(name, day + timedelta(days=1), lat, lon, tz=tz)[1]

    eph = load_ephemeris()
    observer = eph["earth"] + wgs84.latlon(lat, lon)
    ts = timescale()
    start = rise or datetime.combine(day, datetime.min.time(), tzinfo=tz)
    end = set_ or (start + timedelta(days=1))
    times = almanac.find_transits(observer, Star(ra_hours=ra / 15.0, dec_degrees=dec),
                                  ts.from_datetime(start.astimezone(timezone.utc)),
                                  ts.from_datetime(end.astimezone(timezone.utc)))
    transit = times[0].utc_datetime().replace(microsecond=0) if len(times) else None
    transit_alt = res.model.altaz(ra, dec, transit, lat, lon)[1] if transit else None
    always_up = rise is None and set_ is None and res.model.altaz(ra, dec, now, lat, lon)[1] > 0
    return schemas.RiseTransitSet(
        rise_utc=iso(rise), transit_utc=iso(transit), set_utc=iso(set_),
        transit_altitude=None if transit_alt is None else round(transit_alt, 2),
        circumpolar=always_up,
        never_rises=rise is None and set_ is None and not always_up,
    )


def constellation_detail(name: str, lat: float, lon: float, tz_name: str,
                         at: datetime | None = None) -> schemas.ConstellationDetail:
    validate_location(lat, lon)
    tz = zone(tz_name)
    res = resources()
    canonical = find_constellation(name)
    info = res.academy.get_constellation_info(canonical)
    now = at or datetime.now(timezone.utc)
    az, alt = res.model.get_constellation_position(canonical, now, lat, lon)
    best = res.model.best_viewing_month(canonical, lat, lon, tz=tz)
    return schemas.ConstellationDetail(
        name=canonical,
        abbreviation=info["abbreviation"],
        stars=chart_stars(canonical),
        lines=[(str(a), str(b)) for a, b in res.db[canonical].edges],
        mythology=info["mythology"],
        best_season=info["best_season"],
        fun_fact=info["fun_fact"],
        best_month=None if best is None else schemas.BestMonth(month=best[0], altitude=round(best[1], 1)),
        now=schemas.NowPosition(az=round(az, 2), alt=round(alt, 2), direction=compass(az),  # type: ignore[arg-type]
                                visible=alt > res.model.config.min_altitude),
        tonight=rise_transit_set(canonical, lat, lon, tz, now),
    )


# ------------------------------------------------------------------------ quiz
def new_quiz(mode: str, constellation: str | None, seed: int | None = None) -> schemas.QuizNew:
    res = resources()
    name = find_constellation(constellation) if constellation else random.choice(res.db.list_constellations())
    seed = random.randrange(1, 10**9) if seed is None else seed
    quiz = res.academy.generate_quiz(name, distractors=3 if mode == "hard" else 0, seed=seed)
    return schemas.QuizNew(
        id=f"{name}:{mode}:{seed}",
        constellation=name,
        mode=mode,  # type: ignore[arg-type]
        # The distractor flag is deliberately not sent: it would give the answer away.
        stars=[schemas.QuizStar(name=s.name, x=round(s.x, 4), y=round(s.y, 4), magnitude=s.magnitude,
                                ci=res.colors.get(s.name)) for s in quiz.stars],
        line_count=len(quiz.correct_edges),
    )


def grade_quiz(quiz_id: str, edges: list[tuple[str, str]]) -> schemas.QuizGrade:
    try:
        name, mode, seed = quiz_id.rsplit(":", 2)
        int(seed)
    except ValueError as exc:
        raise ValueError("Malformed quiz id") from exc
    if mode not in ("easy", "hard"):
        raise ValueError("Malformed quiz id")
    canonical = find_constellation(name)
    correct = normalize_edges(resources().db[canonical].edges)
    user = normalize_edges([e for e in edges if e[0] != e[1]])
    score = check_quiz_answer(user, correct)
    return schemas.QuizGrade(
        constellation=canonical,
        score=round(score, 4),
        perfect=user == correct,
        correct=sorted(user & correct),
        missing=sorted(correct - user),
        extra=sorted(user - correct),
        isomorphic_hint=bool(user) and user != correct and same_shape(user, correct),
    )


# ------------------------------------------------------------------------ demo
class DemoFrames:
    """Serves demo-sky frames as JPEGs, rendering sequentially (cheap for playback)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._streams: dict[str, tuple[int, Iterator[NDArray[np.uint8]]]] = {}

    def _clip(self, name: str) -> Iterator[NDArray[np.uint8]]:
        fps = resources().pipeline_config.fps
        return demo_sky_clip(resources().db[name], DEMO_FRAMES, width=DEMO_WIDTH,
                             height=DEMO_HEIGHT, fps=fps)

    def jpeg(self, name: str, index: int, quality: int = 85) -> bytes:
        canonical = find_constellation(name)
        index %= DEMO_FRAMES
        with self._lock:
            position, stream = self._streams.get(canonical, (-1, iter(())))
            if index != position + 1:  # not the next frame: restart and skip ahead
                stream = islice(self._clip(canonical), index, None)
            frame = next(stream, None)
            if frame is None:
                stream = self._clip(canonical)
                frame = next(stream)
            self._streams[canonical] = (index, stream)
        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return buffer.tobytes()


DEMO = DemoFrames()
