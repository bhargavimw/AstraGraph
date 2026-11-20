"""End-to-end sky pipeline: detector → tracker → temporal graph → matcher → reasoner.

:class:`SkyPipeline` processes one frame at a time and returns a
:class:`FrameReport` with everything an overlay or a log needs: detections,
tracks, temporal events, constellation matches (with ghost stars), derived
facts, satellites (with sky direction and angular speed when a constellation
gives the plate scale) and anomalies.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from astragraph.constellation_db import ConstellationDB, load_config
from astragraph.detect import DetectorConfig, StarDetection, StarDetector
from astragraph.matcher import ConstellationMatcher, MatchResult, MatcherConfig
from astragraph.reason import Conclusion, Fact, ReasonerConfig, SkyReasoner
from astragraph.temporal import (
    Event,
    TemporalConfig,
    TemporalGraphBuilder,
    is_linear_trajectory,
    steady_speed,
)
from astragraph.track import StarTracker, TrackedStar, TrackerConfig

COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


@dataclass(frozen=True)
class PipelineConfig:
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)
    matcher: MatcherConfig = field(default_factory=MatcherConfig)
    reasoner: ReasonerConfig = field(default_factory=ReasonerConfig)
    fps: float = 30.0

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "PipelineConfig":
        tracking = config.get("tracking") or {}
        reasoning = config.get("reasoning") or {}
        temporal = config.get("temporal") or {}
        matcher = config.get("matcher") or {}
        return cls(
            detector=DetectorConfig.from_mapping(config.get("detector")),
            tracker=TrackerConfig.from_mapping(tracking),
            temporal=TemporalConfig.from_mapping(tracking, reasoning, temporal),
            matcher=MatcherConfig.from_mapping(reasoning, matcher),
            reasoner=ReasonerConfig.from_mapping(reasoning),
            fps=float((config.get("video") or {}).get("fps", 30.0)),
        )

    @classmethod
    def from_file(cls, path: str | Path = "config.yaml") -> "PipelineConfig":
        return cls.from_mapping(load_config(path))


@dataclass(frozen=True)
class SatelliteReport:
    """A moving object flagged as a satellite candidate."""

    track_id: int
    x: float
    y: float
    pixels_per_second: float
    degrees_per_second: float | None
    heading: str | None

    def describe(self) -> str:
        if self.degrees_per_second is not None and self.heading is not None:
            return (
                f"Satellite detected: moving {self.heading} at "
                f"{self.degrees_per_second:.1f}°/sec"
            )
        return f"Satellite detected: moving at {self.pixels_per_second:.0f} px/sec"


@dataclass(frozen=True)
class FrameReport:
    frame_idx: int
    detections: tuple[StarDetection, ...]
    tracks: tuple[TrackedStar, ...]
    events: tuple[Event, ...]
    matches: Mapping[str, MatchResult]
    conclusions: tuple[Conclusion, ...]
    satellites: tuple[SatelliteReport, ...]
    anomalies: tuple[int, ...]

    @property
    def constellations(self) -> list[MatchResult]:
        """Matches the reasoner confirmed as identified, best first."""
        names = {c.fact[2] for c in self.conclusions if c.fact[0] == "identified_as"}
        found = [m for m in self.matches.values() if m.constellation in names]
        return sorted(found, key=lambda m: -m.confidence)


def compass_heading(east: float, north: float) -> str:
    """8-point compass direction of a vector given in east/north components."""
    angle = math.degrees(math.atan2(east, north)) % 360.0
    return COMPASS[int((angle + 22.5) // 45.0) % 8]


def sky_motion(
    velocity_px: tuple[float, float], match: MatchResult
) -> tuple[float, str] | None:
    """Convert an image velocity (px/frame) to (deg/frame, compass heading).

    Uses the match's template→image similarity: the inverse maps image
    vectors into the template plane, whose axes are (west, south) in degrees.
    """
    if match.transform is None:
        return None
    plane = match.transform.inverse().apply_vector(np.array(velocity_px))[0]
    east, north = -float(plane[0]), -float(plane[1])
    return math.hypot(east, north), compass_heading(east, north)


def build_facts(
    tracks: Sequence[TrackedStar],
    clusters: Sequence[Sequence[int]],
    matches: Mapping[str, MatchResult],
    builder: TemporalGraphBuilder,
) -> list[Fact]:
    """Translate the scene into ``(predicate, subject, object)`` facts."""
    cfg = builder.config
    facts: list[Fact] = []
    for track in tracks:
        if not track.visible:
            continue
        subject = f"track:{track.id}"
        window = cfg.min_trajectory_points
        rel = builder.relative_trajectory(track)[-window:]
        frames = track.frame_indices[-window:]
        facts.append(("brightness", subject, float(track.brightness)))
        facts.append(("velocity", subject, steady_speed(rel, frames)))
        facts.append(
            ("trajectory_linear", subject,
             is_linear_trajectory(rel, tolerance=cfg.linear_tolerance,
                                  min_points=cfg.min_trajectory_points))
        )
    for k, members in enumerate(clusters):
        cluster = f"cluster:{k}"
        facts.append(("cluster_size", cluster, len(members)))
        for track_id in members:
            facts.append(("member_of", f"track:{track_id}", cluster))
        match = matches.get(cluster)
        if match is None or not match.matched:
            continue
        facts.append(("matches_pattern", cluster, match.constellation))
        facts.append(("match_confidence", cluster, match.confidence))
        for star in match.ghost_positions:
            facts.append(("hidden_star", cluster, star))
        for track_id in match.outliers:
            facts.append(("not_in_catalog", f"track:{track_id}", True))
    return facts


class SkyPipeline:
    """Stateful per-frame processing for a video stream or image sequence."""

    def __init__(
        self,
        constellation_db: ConstellationDB,
        config: PipelineConfig | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.db = constellation_db
        self.detector = StarDetector(self.config.detector)
        self.tracker = StarTracker(self.config.tracker)
        self.temporal = TemporalGraphBuilder(self.config.temporal)
        self.matcher = ConstellationMatcher(self.config.matcher)
        self.reasoner = SkyReasoner(self.config.reasoner)
        self._match_cache: dict[frozenset[int], MatchResult] = {}
        self._frame_idx = -1

    def _match_clusters(
        self, clusters: Sequence[Sequence[int]], positions: Mapping[int, tuple[float, float]]
    ) -> dict[str, MatchResult]:
        matches: dict[str, MatchResult] = {}
        cache: dict[frozenset[int], MatchResult] = {}
        for k, members in enumerate(clusters):
            if len(members) < self.config.matcher.min_matched:
                continue
            key = frozenset(members)
            cluster_points = {i: positions[i] for i in members}
            previous = self._match_cache.get(key)
            result = None
            if previous is not None and previous.matched:
                result = self.matcher.refit(cluster_points, previous, self.db)
            if result is None:
                result = self.matcher.match(cluster_points, self.db)
            cache[key] = result
            matches[f"cluster:{k}"] = result
        self._match_cache = cache
        return matches

    def process(self, frame: NDArray[np.uint8], frame_idx: int | None = None) -> FrameReport:
        """Run every stage on one frame."""
        self._frame_idx = self._frame_idx + 1 if frame_idx is None else frame_idx
        idx = self._frame_idx

        detections = self.detector.detect(frame)
        tracks = self.tracker.track(frame, detections, idx)
        events = self.temporal.update(tracks, idx)
        clusters = self.temporal.clusters
        positions = {t.id: (t.x, t.y) for t in tracks}
        matches = self._match_clusters(clusters, positions)

        facts = build_facts(tracks, clusters, matches, self.temporal)
        conclusions = self.reasoner.reason(facts)
        satellite_ids = {
            int(str(f[1]).split(":")[1])
            for f in SkyReasoner.query(conclusions, "is_satellite")
        } | set(self.temporal.satellites)
        anomaly_ids = sorted(
            int(str(f[1]).split(":")[1]) for f in SkyReasoner.query(conclusions, "is_anomaly")
        )

        best = next(
            (m for m in sorted(matches.values(), key=lambda m: -m.confidence) if m.matched),
            None,
        )
        by_id = {t.id: t for t in tracks}
        satellites = []
        for track_id in sorted(satellite_ids):
            track = by_id.get(track_id)
            if track is None or not track.visible:
                continue
            vx, vy = self.temporal.sky_velocity(track)
            motion = sky_motion((vx, vy), best) if best else None
            satellites.append(
                SatelliteReport(
                    track_id=track_id,
                    x=track.x,
                    y=track.y,
                    pixels_per_second=math.hypot(vx, vy) * self.config.fps,
                    degrees_per_second=motion[0] * self.config.fps if motion else None,
                    heading=motion[1] if motion else None,
                )
            )
        return FrameReport(
            frame_idx=idx,
            detections=tuple(detections),
            tracks=tuple(tracks),
            events=tuple(events),
            matches=matches,
            conclusions=tuple(conclusions),
            satellites=tuple(satellites),
            anomalies=tuple(anomaly_ids),
        )
