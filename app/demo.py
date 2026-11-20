"""AstraGraph — Streamlit app.

Run with:
    streamlit run app/demo.py

Modes (sidebar):
    Live Camera  – detect stars and identify constellations in a webcam
                   stream, an uploaded photo/video, or a built-in demo sky.
    Time Travel  – slide up to 12 hours either way and see the predicted sky.
    Learn        – constellation facts, current position and rise/set times.
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
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "app"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from astragraph.constellation_db import ConstellationDB, load_config, resolve_path  # noqa: E402
from astragraph.pipeline import FrameReport, PipelineConfig, SkyPipeline  # noqa: E402
from astragraph.synthetic import demo_sky_clip  # noqa: E402
from astragraph.viz import plot_constellation  # noqa: E402
from astragraph.world_model import SkyWorldModel, WorldModelConfig  # noqa: E402
from utils import FPSCounter, annotate_frame, downscale  # noqa: E402

CONFIG_PATH = ROOT / "config.yaml"
MAX_WIDTH = 1280  # wider frames are downscaled (peak-preserving) for speed
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
SKY_BG, PANEL_BG, GOLD_HEX, STAR_HEX, GRID_HEX = (
    "#070b17", "#0d1426", "#ffbe28", "#f5f8ff", "#2a3a5e"
)
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
    st.sidebar.title("✨ AstraGraph")
    st.sidebar.caption("Learn & explore the night sky")
    mode = st.sidebar.radio(
        "Mode", ["Live Camera", "Time Travel", "Learn"],
        help="Live Camera finds constellations in images; Time Travel predicts "
             "the sky; Learn explains each constellation.",
    )
    section = config.get("world_model") or {}
    with st.sidebar.expander("📍 Your location", expanded=mode != "Live Camera"):
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
    st.write("Point at the sky and AstraGraph draws the constellation: "
             "**green** circles are stars, **gold** lines the constellation, "
             "**cyan** rings stars hidden by clouds (inferred), **red** satellites.")
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
def sky_chart(model: SkyWorldModel, db: ConstellationDB, moment: datetime,
              lat: float, lon: float, highlight: str | None = None):
    """Polar sky chart: zenith centre, N up, E left (as seen looking up)."""
    fig = plt.figure(figsize=(7.2, 7.2), facecolor=SKY_BG)
    ax = fig.add_subplot(projection="polar", facecolor=PANEL_BG)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(1)  # counter-clockwise: east on the left
    ax.set_ylim(0, 90)
    ax.set_yticks([30, 60, 90])
    ax.set_yticklabels(["60°", "30°", "0°"], color=GRID_HEX, fontsize=7)
    ax.set_xticks(np.radians([0, 90, 180, 270]))
    ax.set_xticklabels(["N", "E", "S", "W"], color="#c9d6f2", fontsize=11)
    ax.grid(color=GRID_HEX, linewidth=0.6)
    ax.spines["polar"].set_color(GRID_HEX)

    stars = [s for s in model.get_all_stars(moment, lat, lon) if s.altitude > 0]
    if stars:
        ax.scatter(np.radians([s.azimuth for s in stars]), [90 - s.altitude for s in stars],
                   s=[max(2.0, 26 - 7 * s.magnitude) for s in stars],
                   c=STAR_HEX, linewidths=0, alpha=0.9, zorder=3)

    for name in db.list_constellations():
        graph = db[name]
        nodes = list(graph.nodes)
        positions = dict(zip(nodes, model.altaz_many(
            [graph.nodes[n]["ra"] for n in nodes], [graph.nodes[n]["dec"] for n in nodes],
            moment, lat, lon)))
        color = GOLD_HEX if name == highlight else "#7fa8ff"
        width = 2.0 if name == highlight else 1.0
        for a, b in graph.edges:
            (az1, alt1), (az2, alt2) = positions[a], positions[b]
            if alt1 > 0 and alt2 > 0:
                ax.plot(np.radians([az1, az2]), [90 - alt1, 90 - alt2],
                        color=color, linewidth=width, alpha=0.9, zorder=2)
        up = [(az, alt) for az, alt in positions.values() if alt > 0]
        if len(up) >= len(nodes) / 2:
            az = max(up, key=lambda p: p[1])
            ax.annotate(name, (np.radians(az[0]), 90 - az[1]), color=color,
                        fontsize=9 if name == highlight else 8, fontweight="bold",
                        xytext=(6, 6), textcoords="offset points", zorder=4)
    fig.tight_layout()
    return fig


def time_travel(db: ConstellationDB, model: SkyWorldModel,
                lat: float, lon: float, tz: ZoneInfo) -> None:
    st.header("⏳ Time Travel")
    st.write("Slide through time to see where the constellations will be. "
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
            fig = sky_chart(model, db, moment, lat, lon, highlight=target)
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
        st.pyplot(fig, width="stretch")
        plt.close(fig)
        st.caption(f"Sky at {fmt_time(moment, tz)}. Centre = straight up, edge = horizon. "
                   "East is on the left because the chart is seen looking up.")
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


# -------------------------------------------------------------------- learn
def learn(db: ConstellationDB, model: SkyWorldModel,
          lat: float, lon: float, tz: ZoneInfo) -> None:
    st.header("📚 Learn")
    name = st.selectbox("Choose a constellation", db.list_constellations(),
                        index=db.list_constellations().index("Orion"), key="learn_name")
    graph = db[name]
    now = datetime.now(timezone.utc)

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

        try:
            best = model.best_viewing_month(name, lat, lon, tz=tz)
            az, alt = model.get_constellation_position(name, now, lat, lon)
            rise, set_ = rise_then_set(
                lambda d: model.get_constellation_rise_set(name, d, lat, lon, tz=tz),
                now.astimezone(tz).date(),
            )
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
        if model.sky_darkness(now, lat, lon) == "day":
            st.caption("☀️ It is daytime here, so the sky is too bright to see stars.")
        if alt > model.config.min_altitude:
            st.success(f"{name} is currently visible at azimuth {az:.0f}° "
                       f"({compass(az)}), altitude {alt:.0f}°.")
        elif alt > 0:
            st.warning(f"{name} is low on the horizon: azimuth {az:.0f}° "
                       f"({compass(az)}), altitude {alt:.0f}°.")
        else:
            st.info(f"{name} is below the horizon right now "
                    f"(altitude {alt:.0f}°).")

        st.subheader("Tonight")
        if rise is None and set_ is None:
            st.write("Does not rise or set today: "
                     + ("it stays above the horizon all night."
                        if alt > 0 else "it stays below the horizon."))
        else:
            st.write(f"🌄 Rises: **{fmt_time(rise, tz)}**")
            st.write(f"🌇 Sets: **{fmt_time(set_, tz)}**")


# --------------------------------------------------------------------- main
def main() -> None:
    st.set_page_config(page_title="AstraGraph", page_icon="✨", layout="wide")
    try:
        db, model, config = load_resources()
    except Exception as exc:
        st.error(f"AstraGraph could not start: {exc}")
        st.stop()
    mode, lat, lon, tz = sidebar(config)
    started = clock.perf_counter()
    if mode == "Live Camera":
        live_camera(db, config)
    elif mode == "Time Travel":
        time_travel(db, model, lat, lon, tz)
    else:
        learn(db, model, lat, lon, tz)
    st.sidebar.caption(f"Rendered in {clock.perf_counter() - started:.2f} s")


if __name__ == "__main__":
    main()
