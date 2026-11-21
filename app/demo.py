"""AstraGraph — Streamlit app.

Run with:
    streamlit run app/demo.py

Modes (sidebar):
    Home         – welcome page with tonight's sky for your location.
    Live Camera  – detect stars and identify constellations in a webcam
                   stream, an uploaded photo/video, or a built-in demo sky.
    Time Travel  – slide up to 12 hours either way and see the predicted sky.
    Learn        – constellation facts, current position and rise/set times.
    Academy      – connect-the-dots quizzes and constellation info cards.
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time as clock
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, available_timezones

import cv2
import matplotlib.pyplot as plt
import numpy as np

# Load pandas fully on the main thread *before* any chart is drawn. Plotly
# imports pandas lazily the first time it validates chart data; when Streamlit
# renders two charts at once on separate threads, one of them can see a
# half-imported pandas and crash with "partially initialized module 'pandas'
# has no attribute 'Series' (most likely due to a circular import)". This was
# seen on Windows. Importing plotly's validators here as well finishes all of
# that work up front.
import pandas  # noqa: F401
import plotly.graph_objects  # noqa: F401
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "app"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from astragraph.academy import AstronomyAcademy, Quiz, QuizResult, normalize_edge  # noqa: E402
from astragraph.constellation_db import ConstellationDB, load_config, resolve_path  # noqa: E402
from astragraph.pipeline import FrameReport, PipelineConfig, SkyPipeline  # noqa: E402
from astragraph.synthetic import demo_sky_clip  # noqa: E402
from astragraph.viz import plot_constellation  # noqa: E402
from astragraph.world_model import SkyWorldModel, WorldModelConfig  # noqa: E402
from sky_chart import animated_sky_chart  # noqa: E402
from theme import (  # noqa: E402
    CHART_BG, CHART_PANEL, STARBURST_HTML, apply_theme, html, sidebar_logo, subtitle,
)
from tonight import tonight_summary  # noqa: E402
from utils import FPSCounter, annotate_frame, downscale  # noqa: E402

CONFIG_PATH = ROOT / "config.yaml"
MAX_WIDTH = 1280  # wider frames are downscaled (peak-preserving) for speed
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
GOLD_HEX = "#ffbe28"
MODES = ["Home", "Live Camera", "Time Travel", "Learn", "Academy"]
COMMON_TIMEZONES = [
    "UTC", "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "Europe/London", "Europe/Paris", "Asia/Kolkata",
    "Asia/Tokyo", "Australia/Sydney",
]


# --------------------------------------------------------------- resources
@st.cache_resource(show_spinner="Loading star catalog and ephemeris…")
def load_resources() -> tuple[ConstellationDB, SkyWorldModel, dict]:
    config = load_config(CONFIG_PATH)
    db = ConstellationDB.from_config(CONFIG_PATH)
    db.load()
    section = config.get("world_model") or {}
    catalog = resolve_path(section.get("star_catalog", "data/bright_stars.csv"),
                           relative_to=CONFIG_PATH)
    model = SkyWorldModel(catalog, config=WorldModelConfig.from_mapping(section),
                          constellation_db=db)
    return db, model, config


def compass(azimuth: float) -> str:
    return COMPASS[int(((azimuth % 360) + 22.5) // 45) % 8]


def fmt_time(moment: datetime | None, tz: ZoneInfo) -> str:
    return "—" if moment is None else moment.astimezone(tz).strftime("%a %d %b, %H:%M %Z")


def rise_then_set(lookup, day: date) -> tuple[datetime | None, datetime | None]:
    """Rising on ``day`` and the first setting after it (possibly the next day)."""
    rise, set_ = lookup(day)
    if rise is not None and (set_ is None or set_ < rise):
        set_ = lookup(day + timedelta(days=1))[1]
    return rise, set_


# ------------------------------------------------------------------ sidebar
def sidebar(config: dict) -> tuple[str, float, float, ZoneInfo]:
    sidebar_logo()
    mode = st.sidebar.radio(
        "Mode", MODES, key="mode",
        help="Home shows tonight's sky; Live Camera finds constellations in images; "
             "Time Travel predicts the sky; Learn explains each constellation; "
             "Academy has quizzes and constellation stories.",
    )
    section = config.get("world_model") or {}
    with st.sidebar.expander("📍 Your location", expanded=mode not in ("Live Camera",)):
        lat = st.number_input("Latitude (°N)", -90.0, 90.0,
                              float(section.get("default_lat", 40.7128)), step=0.5,
                              format="%.4f")
        lon = st.number_input("Longitude (°E)", -180.0, 180.0,
                              float(section.get("default_lon", -74.0060)), step=0.5,
                              format="%.4f")
        default_tz = section.get("timezone", "UTC")
        options = COMMON_TIMEZONES + sorted(available_timezones() - set(COMMON_TIMEZONES))
        tz_name = st.selectbox("Time zone", options,
                               index=options.index(default_tz) if default_tz in options else 0)
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Positions: Skyfield + JPL DE421. Stars: HYG database (CC BY-SA 4.0). "
        "All processing runs locally — no images leave your machine."
    )
    return mode, lat, lon, ZoneInfo(tz_name)


# -------------------------------------------------------------- live camera
def report_summary(report: FrameReport) -> None:
    cols = st.columns(4)
    cols[0].metric("Stars detected", len(report.detections))
    cols[1].metric("Constellations", len(report.constellations))
    cols[2].metric("Satellites", len(report.satellites))
    cols[3].metric("Anomalies", len(report.anomalies))
    for match in report.constellations:
        line = f"**{match.constellation}** — confidence {match.confidence:.0%}"
        if match.ghost_positions:
            line += f" · hidden stars inferred: {', '.join(sorted(match.ghost_positions))}"
        st.success(line)
    for sat in report.satellites:
        st.warning(sat.describe())
    if report.anomalies:
        st.info(f"{len(report.anomalies)} bright object(s) not in the catalog — "
                "possibly a planet.")


def process_frames(frames, pipeline: SkyPipeline, placeholder, stride: int = 1):
    """Run the pipeline over frames, updating an image placeholder live."""
    fps = FPSCounter()
    report, last = None, None
    for idx, frame in enumerate(frames):
        frame, _ = downscale(frame, MAX_WIDTH)
        report = pipeline.process(frame, idx)
        last = frame
        rate = fps.tick()
        if idx % stride == 0:
            placeholder.image(cv2.cvtColor(annotate_frame(frame, report, rate),
                                           cv2.COLOR_BGR2RGB), width="stretch")
    if report is not None and last is not None:
        placeholder.image(cv2.cvtColor(annotate_frame(last, report, fps.fps),
                                       cv2.COLOR_BGR2RGB), width="stretch")
    return report


class SkyVideoProcessor:
    """Runs the AstraGraph pipeline on each webcam frame (streamlit-webrtc)."""

    def __init__(self, db: ConstellationDB, pipeline_config: PipelineConfig) -> None:
        self.pipeline = SkyPipeline(db, pipeline_config)
        self.fps = FPSCounter()
        self.lock = threading.Lock()
        self.last_report: FrameReport | None = None

    def process(self, image: np.ndarray) -> np.ndarray:
        """Annotate one BGR frame; never raises (errors are drawn on the frame)."""
        try:
            small, _ = downscale(image, MAX_WIDTH)  # ~60+ FPS even from 1080p
            report = self.pipeline.process(small)
            output = annotate_frame(small, report, self.fps.tick())
            with self.lock:
                self.last_report = report
            return output
        except Exception as exc:  # never kill the stream on one bad frame
            output = image.copy()
            cv2.putText(output, f"Processing error: {exc}"[:80], (12, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 60, 255), 2)
            return output

    def recv(self, frame):  # av.VideoFrame -> av.VideoFrame
        import av

        output = self.process(frame.to_ndarray(format="bgr24"))
        return av.VideoFrame.from_ndarray(output, format="bgr24")


def webcam_section(db: ConstellationDB, pipeline_config: PipelineConfig) -> None:
    try:
        from streamlit_webrtc import WebRtcMode, webrtc_streamer
    except ImportError:
        st.error("Webcam mode needs `streamlit-webrtc`: `pip install streamlit-webrtc`.")
        return

    st.caption("Allow camera access when your browser asks. Works best outdoors, "
               "on a dark night, with the phone or laptop held still.")
    context = webrtc_streamer(
        key="astragraph-live",
        mode=WebRtcMode.SENDRECV,
        video_processor_factory=lambda: SkyVideoProcessor(db, pipeline_config),
        media_stream_constraints={"video": True, "audio": False},
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
        async_processing=True,
    )
    if context.state.playing and context.video_processor:
        with context.video_processor.lock:
            report = context.video_processor.last_report
        if report is not None:
            report_summary(report)
    elif not context.state.playing:
        st.info("Press **START** to open the camera. No camera? Try the demo sky "
                "or upload a photo instead.")


def live_camera(db: ConstellationDB, config: dict) -> None:
    st.header("🔭 Live Camera — SkyFinder")
    subtitle("Point at the sky and AstraGraph draws the constellation: "
             "<b style='color:#50dc50'>green</b> circles are stars, "
             "<b style='color:#ffbe28'>gold</b> lines the constellation, "
             "<b style='color:#3cdcff'>cyan</b> rings stars hidden by clouds (inferred), "
             "<b style='color:#ff5a5a'>red</b> satellites.")
    pipeline_config = PipelineConfig.from_mapping(config)
    source = st.radio("Source", ["Demo sky", "Webcam", "Upload photo or video"],
                      horizontal=True)

    if source == "Webcam":
        webcam_section(db, pipeline_config)
        return

    if source == "Demo sky":
        col1, col2 = st.columns([2, 1])
        name = col1.selectbox("Constellation in the demo sky", db.list_constellations(),
                              index=db.list_constellations().index("Orion"))
        frames = col2.slider("Frames", 20, 120, 60, step=10)
        st.caption("A rendered sky with hand-shake drift, a passing satellite, a "
                   "planet, and a cloud that hides stars halfway through.")
        if st.button("▶ Run demo", type="primary"):
            placeholder = st.empty()
            with st.spinner("Processing frames…"):
                report = process_frames(
                    demo_sky_clip(db[name], frames, fps=pipeline_config.fps),
                    SkyPipeline(db, pipeline_config), placeholder, stride=2,
                )
            if report:
                report_summary(report)
        return

    upload = st.file_uploader("Night-sky photo or video",
                              type=["png", "jpg", "jpeg", "mp4", "mov", "avi"])
    if upload is None:
        st.info("Upload a long-exposure photo or a short video of the night sky.")
        return
    placeholder = st.empty()
    pipeline = SkyPipeline(db, pipeline_config)
    suffix = Path(upload.name).suffix.lower()
    try:
        if suffix in {".png", ".jpg", ".jpeg"}:
            data = np.frombuffer(upload.getvalue(), dtype=np.uint8)
            image = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if image is None:
                st.error("Could not read that image. Try a PNG or JPEG file.")
                return
            repeats = pipeline_config.temporal.debounce_frames + 1
            with st.spinner("Detecting stars…"):
                report = process_frames([image] * repeats, pipeline, placeholder)
        else:
            with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
                handle.write(upload.getvalue())
                handle.flush()
                capture = cv2.VideoCapture(handle.name)
                if not capture.isOpened():
                    st.error("Could not open that video file.")
                    return

                def frames():
                    for _ in range(600):  # cap at ~20 s of 30 fps video
                        ok, frame = capture.read()
                        if not ok:
                            return
                        yield frame

                with st.spinner("Processing video…"):
                    report = process_frames(frames(), pipeline, placeholder, stride=3)
                capture.release()
    except Exception as exc:
        st.error(f"Something went wrong while processing the file: {exc}")
        return
    if report is None:
        st.warning("No frames found in that file.")
    else:
        report_summary(report)


# -------------------------------------------------------------- time travel
@st.cache_data(show_spinner=False, max_entries=16)
def cached_sky_chart(start_iso: str, lat: float, lon: float, tz_name: str,
                     initial_hours: float, highlight: str):
    """Animated chart for a start time/place (cached: building it takes ~1.5 s)."""
    db, model, _ = load_resources()
    return animated_sky_chart(model, db, datetime.fromisoformat(start_iso), lat, lon,
                              ZoneInfo(tz_name), initial_hours=initial_hours,
                              highlight=highlight)


def time_travel(db: ConstellationDB, model: SkyWorldModel,
                lat: float, lon: float, tz: ZoneInfo) -> None:
    st.header("⏳ Time Travel")
    subtitle("Slide through time to see where the constellations will be. "
             "Positions are computed from real orbital mechanics, not guessed.")
    col1, col2, col3 = st.columns(3)
    now_local = datetime.now(tz)
    day = col1.date_input("Start date", now_local.date())
    start_time = col2.time_input("Start time", now_local.time().replace(second=0, microsecond=0))
    target = col3.selectbox("Follow constellation", db.list_constellations(),
                            index=db.list_constellations().index("Orion"))
    hours = st.slider("Hours from start", -12.0, 12.0, 0.0, step=0.5)

    start = datetime.combine(day, start_time, tzinfo=tz)
    moment = start + timedelta(hours=hours)
    limit = model.config.min_altitude

    try:
        with st.spinner("Computing the sky…"):
            az, alt = model.get_constellation_position(target, moment, lat, lon)
            fig = cached_sky_chart(start.isoformat(), lat, lon, tz.key, hours, target)
    except Exception as exc:
        st.error(f"Could not compute the sky for that time: {exc}")
        return

    when = ("Right now" if hours == 0 else
            f"In {hours:g} hours" if hours > 0 else f"{abs(hours):g} hours ago")
    verb = "is" if hours == 0 else "will be" if hours > 0 else "was"
    message = (f"{when}, {target} {verb} at azimuth {az:.0f}° ({compass(az)}), "
               f"altitude {alt:.0f}°")
    darkness = model.sky_darkness(moment, lat, lon)
    if darkness == "day":
        st.warning("☀️ The Sun is up at this time — stars and constellations are "
                   "above the horizon but hidden by daylight.")
    elif darkness == "twilight":
        st.info("🌆 Twilight — only the brightest stars are visible.")
    if alt > limit:
        st.success(message + ".")
    elif alt > 0:
        st.warning(message + " — low on the horizon.")
    else:
        st.info(message + " — below the horizon.")

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False},
                        key="sky_chart")
        st.caption(f"Opens at {fmt_time(moment, tz)}. Press ▶ Play to watch the whole day "
                   "turn, drag the time bar, and hover any star for its name. Centre = "
                   "straight up, edge = horizon; east is on the left because the chart "
                   "is seen looking up.")
    with right:
        st.subheader("Where are they?")
        rows = []
        for name in db.list_constellations():
            c_az, c_alt = model.get_constellation_position(name, moment, lat, lon)
            rows.append({
                "Constellation": name,
                "Direction": compass(c_az),
                "Azimuth": f"{c_az:.0f}°",
                "Altitude": f"{c_alt:.0f}°",
                "Visible": "✅" if c_alt > limit else ("🌅 low" if c_alt > 0 else "—"),
            })
        st.dataframe(rows, hide_index=True, width="stretch")


def show_sky_status(model: SkyWorldModel, name: str, lat: float, lon: float,
                    tz: ZoneInfo) -> None:
    """Best viewing month, current position and tonight's rise/set."""
    now = datetime.now(timezone.utc)
    try:
        with st.spinner("Computing positions…"):
            best = model.best_viewing_month(name, lat, lon, tz=tz)
            az, alt = model.get_constellation_position(name, now, lat, lon)
            rise, set_ = rise_then_set(
                lambda d: model.get_constellation_rise_set(name, d, lat, lon, tz=tz),
                now.astimezone(tz).date(),
            )
            darkness = model.sky_darkness(now, lat, lon)
    except Exception as exc:
        st.error(f"Could not compute positions for this location: {exc}")
        return

    st.subheader("Best time to view")
    if best is None:
        st.write(f"{name} never rises high enough to see well from this latitude.")
    else:
        st.write(f"Around **9 pm in {MONTHS[best[0] - 1]}**, when it reaches "
                 f"about {best[1]:.0f}° above the horizon.")

    st.subheader("Right now")
    if darkness == "day":
        st.caption("☀️ It is daytime here, so the sky is too bright to see stars.")
    if alt > model.config.min_altitude:
        st.success(f"{name} is currently visible at azimuth {az:.0f}° "
                   f"({compass(az)}), altitude {alt:.0f}°.")
    elif alt > 0:
        st.warning(f"{name} is low on the horizon: azimuth {az:.0f}° "
                   f"({compass(az)}), altitude {alt:.0f}°.")
    else:
        st.info(f"{name} is below the horizon right now (altitude {alt:.0f}°).")

    st.subheader("Tonight")
    if rise is None and set_ is None:
        st.write("Does not rise or set today: "
                 + ("it stays above the horizon all night."
                    if alt > 0 else "it stays below the horizon."))
    else:
        st.write(f"🌄 Rises: **{fmt_time(rise, tz)}**")
        st.write(f"🌇 Sets: **{fmt_time(set_, tz)}**")


# -------------------------------------------------------------------- learn
def learn(db: ConstellationDB, model: SkyWorldModel,
          lat: float, lon: float, tz: ZoneInfo) -> None:
    st.header("📚 Learn")
    subtitle("Meet the constellations: their brightest stars, the best month to look "
             "and where they are in your sky tonight.")
    name = st.selectbox("Choose a constellation", db.list_constellations(),
                        index=db.list_constellations().index("Orion"), key="learn_name")
    graph = db[name]

    left, right = st.columns([3, 2])
    with left:
        fig, _ = plot_constellation(graph, name)
        st.pyplot(fig, width="stretch")
        plt.close(fig)
    with right:
        st.subheader("Key stars")
        brightest = sorted(graph.nodes, key=lambda n: graph.nodes[n]["magnitude"])
        st.dataframe(
            [{"Star": n, "Designation": graph.nodes[n].get("designation", ""),
              "Magnitude": graph.nodes[n]["magnitude"]} for n in brightest[:5]],
            hide_index=True, width="stretch",
        )
        st.caption("Lower magnitude = brighter. Each step of 1 is ~2.5× in brightness.")

        show_sky_status(model, name, lat, lon, tz)


# ------------------------------------------------------------------ academy
QUIZ_COLORS = {"star": "#f5f8ff", "distractor": "#f5f8ff", "line": GOLD_HEX,
               "pending": "#3cdcff", "correct": "#4cd964", "extra": "#ff5a5a",
               "missing": "#ffbe28"}


@st.cache_resource
def load_academy() -> AstronomyAcademy:
    db, _, _ = load_resources()
    return AstronomyAcademy(db)


def quiz_figure(quiz: Quiz, pending: str | None, result: QuizResult | None,
                hints: bool = False):
    """Plotly chart of the quiz: stars as clickable points, lines as drawn."""
    import plotly.graph_objects as go

    fig = go.Figure()
    pos = {s.name: (s.x, s.y) for s in quiz.stars}

    def add_lines(edges, color: str, dash: str = "solid", width: float = 3,
                  label: str | None = None) -> None:
        xs, ys = [], []
        for a, b in sorted(edges):
            xs += [pos[a][0], pos[b][0], None]
            ys += [pos[a][1], pos[b][1], None]
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip",
                                     line=dict(color=color, width=width, dash=dash),
                                     name=label or "", showlegend=label is not None))

    if result is None and hints:  # instant feedback while drawing
        add_lines(quiz.user_edges & quiz.correct_edges, QUIZ_COLORS["correct"])
        add_lines(quiz.user_edges - quiz.correct_edges, QUIZ_COLORS["extra"])
    elif result is None:
        add_lines(quiz.user_edges, QUIZ_COLORS["line"])
    else:
        add_lines(result.correct, QUIZ_COLORS["correct"], label="correct")
        add_lines(result.extra, QUIZ_COLORS["extra"], label="not a line")
        if not result.perfect:
            add_lines(result.missing, QUIZ_COLORS["missing"], "dash", 2, label="missing")

    stars = list(quiz.stars)
    fig.add_trace(go.Scatter(
        x=[s.x for s in stars], y=[s.y for s in stars], mode="markers+text",
        text=[s.name for s in stars], textposition="top center",
        textfont=dict(color="#c9d6f2", size=11),
        customdata=[s.name for s in stars],
        hovertemplate="%{customdata}<extra></extra>",
        marker=dict(size=[max(8.0, 22 - 4.5 * s.magnitude) for s in stars],
                    color=QUIZ_COLORS["star"], line=dict(width=0)),
        showlegend=False,
    ))
    if pending:
        x, y = pos[pending]
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers", hoverinfo="skip",
                                 marker=dict(size=30, color="rgba(0,0,0,0)",
                                             line=dict(color=QUIZ_COLORS["pending"], width=3)),
                                 showlegend=False))
    fig.update_layout(
        paper_bgcolor=CHART_BG, plot_bgcolor=CHART_PANEL, height=560,
        margin=dict(l=10, r=10, t=10, b=10), dragmode=False, clickmode="event+select",
        legend=dict(font=dict(color="#c9d6f2"), orientation="h", y=-0.02),
        xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x"),
    )
    return fig


def _quiz_state(academy: AstronomyAcademy, name: str, distractors: int) -> dict:
    """Session state for the current quiz; a new quiz when the settings change."""
    key = (name, distractors)
    state = st.session_state.get("quiz")
    if state is None or state["key"] != key:
        state = {"key": key, "quiz": academy.generate_quiz(name, distractors=distractors),
                 "pending": None, "result": None, "nonce": 0, "history": []}
        st.session_state["quiz"] = state
    return state


def _connect(state: dict, a: str, b: str, hints: bool = False) -> None:
    if a == b:
        return
    quiz: Quiz = state["quiz"]
    added = quiz.toggle_edge(a, b)
    state["history"].append((a, b, added))
    state["result"] = None
    if hints and added:  # shown on the next run (a toast just before st.rerun is lost)
        if normalize_edge(a, b) in quiz.correct_edges:
            state["toast"] = f"✨ {a} – {b} is a real line of {quiz.constellation}!"
        else:
            state["toast"] = f"🤔 {a} – {b} isn't part of {quiz.constellation}."


def stars_for(score: float) -> str:
    """1–3 star rating for a quiz score."""
    filled = 3 if score >= 1.0 else 2 if score >= 0.6 else 1 if score > 0 else 0
    return "★" * filled + "☆" * (3 - filled)


def record_score(name: str, score: float) -> None:
    scores: dict[str, float] = st.session_state.setdefault("quiz_scores", {})
    scores[name] = max(score, scores.get(name, 0.0))


def progress_panel(names: list[str]) -> None:
    """Running score across constellations."""
    scores: dict[str, float] = st.session_state.get("quiz_scores", {})
    mastered = sum(1 for n in names if scores.get(n, 0.0) >= 1.0)
    st.progress(mastered / len(names),
                text=f"🏆 Constellations mastered: {mastered} / {len(names)}")
    if scores:
        chips = "".join(
            f'<span class="ag-chip{" gold" if scores.get(n, 0) >= 1 else ""}">'
            f'{n} {stars_for(scores[n])}</span>'
            for n in names if n in scores
        )
        html(f'<div class="ag-chips" style="margin:-0.4rem 0 0.6rem 0">{chips}</div>')


def quiz_tab(academy: AstronomyAcademy) -> None:
    names = academy.list_constellations()
    col1, col2, col3 = st.columns([2, 2, 1])
    name = col1.selectbox("Constellation", names, index=names.index("Orion"), key="quiz_name")
    level = col2.radio("Difficulty", ["Easy", "Hard (3 extra stars)"], horizontal=True,
                       key="quiz_level")
    distractors = 0 if level == "Easy" else 3
    hints = st.toggle("💡 Instant feedback (colour each line as you draw it)", key="quiz_hints")
    progress_panel(names)
    state = _quiz_state(academy, name, distractors)
    if state.get("toast"):
        st.toast(state.pop("toast"))
    quiz: Quiz = state["quiz"]
    if col3.button("🔄 New quiz", width="stretch"):
        st.session_state.pop("quiz", None)
        st.rerun()

    st.markdown(f"### Draw **{name}**")
    st.caption("Click a star, then another star, to draw a line between them. "
               "Click the same pair again to remove it. East is on the left, as in the sky.")

    event = st.plotly_chart(
        quiz_figure(quiz, state["pending"], state["result"], hints),
        on_select="rerun", selection_mode="points",
        key=f"quiz_chart_{state['nonce']}", width="stretch",
        config={"displayModeBar": False},
    )
    points = (event.get("selection", {}) or {}).get("points", []) if event else []
    clicked = None
    for point in points:
        data = point.get("customdata")
        if data:
            clicked = data[0] if isinstance(data, (list, tuple)) else data
    if clicked:
        if state["pending"] is None:
            state["pending"] = clicked
        else:
            _connect(state, state["pending"], clicked, hints)
            state["pending"] = None
        state["nonce"] += 1  # fresh chart so the next click registers
        st.rerun()

    with st.expander("Prefer dropdowns? Connect stars here"):
        star_names = sorted(s.name for s in quiz.stars)
        c1, c2, c3 = st.columns([2, 2, 1])
        a = c1.selectbox("From", star_names, key="quiz_from")
        b = c2.selectbox("To", star_names, index=min(1, len(star_names) - 1), key="quiz_to")
        if c3.button("Connect", width="stretch", disabled=a == b):
            _connect(state, a, b, hints)
            st.rerun()

    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Lines drawn", len(quiz.user_edges))
    if b2.button("↩ Undo", width="stretch", disabled=not state["history"]):
        a, b, added = state["history"].pop()
        if added == (normalize_edge(a, b) in quiz.user_edges):
            quiz.toggle_edge(a, b)
        state["result"] = None
        st.rerun()
    if b3.button("🧹 Clear", width="stretch", disabled=not quiz.user_edges):
        quiz.user_edges.clear()
        state.update(pending=None, result=None, history=[])
        st.rerun()
    if b4.button("✅ Submit", type="primary", width="stretch",
                 disabled=not quiz.user_edges):
        state["result"] = quiz.grade()
        state["pending"] = None
        state["celebrate"] = state["result"].perfect
        record_score(name, state["result"].score)
        st.rerun()

    result: QuizResult | None = state["result"]
    if result is not None:
        if result.perfect:
            st.success(f"🎉 Perfect! You drew {name} exactly — score {result.score:.0%} "
                       f"{stars_for(result.score)}")
            if state.pop("celebrate", False):  # play the starburst once
                html(STARBURST_HTML)
                st.toast(f"🌟 {name} mastered!")
        else:
            st.warning(f"Score: **{result.score:.0%}** {stars_for(result.score)} — "
                       f"{len(result.correct)} correct, "
                       f"{len(result.missing)} missing, {len(result.extra)} extra.")
            if result.same_shape:
                st.info("Nice — your drawing has exactly the right *shape* (the graphs are "
                        "isomorphic), but some lines connect different stars.")
            st.caption("The chart now shows the correct answer: green lines are right, "
                       "red ones are not part of the figure, dashed gold ones were missing.")


def info_tab(academy: AstronomyAcademy, model: SkyWorldModel,
             lat: float, lon: float, tz: ZoneInfo) -> None:
    names = academy.list_constellations()
    name = st.selectbox("Constellation", names, index=names.index("Orion"), key="info_name")
    try:
        info = academy.get_constellation_info(name)
    except KeyError as exc:
        st.error(str(exc))
        return

    left, right = st.columns([3, 2])
    with left, st.container(border=True):
        st.markdown(f"## {info['name']} "
                    f"<span style='color:#8a97b8;font-size:0.6em'>{info['abbreviation']}</span>",
                    unsafe_allow_html=True)
        st.caption(f"{info['star_count']} stars · {info['line_count']} lines · "
                   f"best season: {info['best_season']}")
        st.markdown("#### 🏛️ Mythology")
        st.write(info["mythology"])
        st.markdown("#### ⭐ Key stars")
        for star in info["key_stars"]:
            details = [f"magnitude {star['magnitude']:.2f}"]
            if star.get("distance_ly"):
                details.append(f"~{star['distance_ly']:,} light-years")
            st.markdown(f"**{star['name']}** "
                        f"<span style='color:#8a97b8'>({', '.join(details)})</span>",
                        unsafe_allow_html=True)
            st.write(star["fact"])
        st.markdown("#### 💡 Fun fact")
        st.info(info["fun_fact"])
    with right:
        show_sky_status(model, name, lat, lon, tz)
        st.caption(academy.metadata.get("seasons_note", ""))


def academy_mode(model: SkyWorldModel, lat: float, lon: float, tz: ZoneInfo) -> None:
    st.header("🎓 AstroAcademy")
    subtitle("Build constellations star by star, then discover the myths and the "
             "science behind them.")
    try:
        academy = load_academy()
    except Exception as exc:
        st.error(f"Could not load the Academy content: {exc}")
        return
    quiz, info = st.tabs(["🧩 Quiz: build a constellation", "📖 Constellation info"])
    with quiz:
        quiz_tab(academy)
    with info:
        info_tab(academy, model, lat, lon, tz)


# --------------------------------------------------------------------- home
MODE_CARDS = [
    ("Live Camera", "🔭", "Point a camera at the sky and watch AstraGraph draw the "
                         "constellation, even through clouds."),
    ("Time Travel", "⏳", "Play the sky forward or back: an animated chart of the "
                         "next 24 hours."),
    ("Learn", "📚", "Charts, key stars, the best month to look and tonight's "
                   "rise and set times."),
    ("Academy", "🎓", "Connect the dots to build constellations and discover the "
                     "myths behind them."),
]


def go_to(mode: str) -> None:
    st.session_state["mode"] = mode


def tonight_card(model: SkyWorldModel, db: ConstellationDB, lat: float, lon: float,
                 tz: ZoneInfo) -> None:
    try:
        with st.spinner("Checking tonight's sky…"):
            night = tonight_summary(model, db, lat, lon, tz)
    except Exception as exc:
        st.error(f"Could not work out tonight's sky for this location: {exc}")
        return

    def local(moment: datetime | None) -> str:
        return "—" if moment is None else moment.astimezone(tz).strftime("%H:%M")

    if night.never_dark:
        dark_value, dark_sub = "Never fully dark", "Summer twilight lasts all night here"
    elif night.dark_now:
        dark_value, dark_sub = "Dark right now", f"until about {local(night.dawn)}"
    else:
        dark_value, dark_sub = f"From {local(night.dusk)}", f"until {local(night.dawn)}"
    if night.best:
        best = night.best
        best_value = best.name
        best_sub = (f"{best.altitude:.0f}° up in the {best.direction} "
                    f"at {local(night.viewing_time)}")
    else:
        best_value, best_sub = "None of the 8", "Try another hour or location"
    chips = "".join(
        f'<span class="ag-chip{" gold" if i == 0 else ""}">{c.name} · {c.direction}</span>'
        for i, c in enumerate(night.constellations)
    )
    stars = ", ".join(night.bright_stars) or "—"
    html(f"""
<div class="ag-tonight">
  <div class="head"><span class="t">🌌 Tonight's sky</span>
    <span class="where">{lat:.2f}°, {lon:.2f}° · {tz.key}</span></div>
  <div class="grid">
    <div class="ag-stat"><div class="k">Darkness</div><div class="v">{dark_value}</div>
      <div class="s">{dark_sub}</div></div>
    <div class="ag-stat"><div class="k">Moon</div>
      <div class="v">{night.moon_emoji} {night.moon_phase}</div>
      <div class="s">{night.moon_illuminated:.0%} lit · {night.moon_advice}</div></div>
    <div class="ag-stat"><div class="k">Look for</div><div class="v">⭐ {best_value}</div>
      <div class="s">{best_sub}</div></div>
    <div class="ag-stat"><div class="k">Brightest stars up</div>
      <div class="v" style="font-size:1rem">{stars}</div></div>
  </div>
  <div class="ag-chips">{chips}</div>
</div>
""")


def home(db: ConstellationDB, model: SkyWorldModel, lat: float, lon: float,
         tz: ZoneInfo) -> None:
    html("""
<div class="ag-hero">
  <div>
    <div class="kicker">AstraGraph · learn &amp; explore</div>
    <div class="title">Your window to the night sky</div>
    <div class="lead">Find constellations with your camera, travel through time to see
      tomorrow's sky, and learn the stories written in the stars. Everything runs
      on your own device.</div>
  </div>
  <div class="ag-orrery" aria-hidden="true">
    <div class="ring r3"></div><div class="ring r2"></div><div class="ring r1"></div>
    <div class="sun"></div>
  </div>
</div>
""")
    st.header("Welcome to AstraGraph")
    tonight_card(model, db, lat, lon, tz)
    st.markdown("### Explore")
    for column, (mode, icon, text) in zip(st.columns(4), MODE_CARDS):
        with column:
            html(f'<div class="ag-card"><div class="icon">{icon}</div>'
                 f'<div class="name">{mode}</div><div class="desc">{text}</div></div>')
            st.button(f"Open {mode} →", key=f"open_{mode}", on_click=go_to, args=(mode,),
                      width="stretch")
    st.caption("Tip: set your location and time zone in the sidebar so Tonight's sky "
               "matches where you are.")


# --------------------------------------------------------------------- main
def main() -> None:
    st.set_page_config(page_title="AstraGraph", page_icon="✨", layout="wide")
    apply_theme()
    try:
        db, model, config = load_resources()
    except Exception as exc:
        st.error(f"AstraGraph could not start: {exc}")
        st.stop()
    mode, lat, lon, tz = sidebar(config)
    started = clock.perf_counter()
    if mode == "Home":
        home(db, model, lat, lon, tz)
    elif mode == "Live Camera":
        live_camera(db, config)
    elif mode == "Time Travel":
        time_travel(db, model, lat, lon, tz)
    elif mode == "Learn":
        learn(db, model, lat, lon, tz)
    else:
        academy_mode(model, lat, lon, tz)
    st.sidebar.caption(f"Rendered in {clock.perf_counter() - started:.2f} s")


if __name__ == "__main__":
    main()
