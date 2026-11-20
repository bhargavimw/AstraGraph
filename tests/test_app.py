"""Tests for the Streamlit app: helpers, the webcam frame processor and each mode."""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import utils  # noqa: E402

from astragraph.constellation_db import ConstellationDB  # noqa: E402
from astragraph.pipeline import PipelineConfig, SkyPipeline  # noqa: E402
from astragraph.synthetic import demo_sky_clip  # noqa: E402

streamlit = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


@pytest.fixture(scope="module")
def db() -> ConstellationDB:
    database = ConstellationDB.from_config("config.yaml")
    database.load()
    return database


@pytest.fixture(scope="module")
def demo_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("astragraph_app", ROOT / "app" / "demo.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)  # main() is guarded, so nothing renders
    return module


# ------------------------------------------------------------------- utils
def test_horizontal_to_screen_orientation() -> None:
    w = h = 200
    assert utils.horizontal_to_screen(0.0, 90.0, w, h) == pytest.approx((100.0, 100.0))
    north = utils.horizontal_to_screen(0.0, 0.0, w, h)
    east = utils.horizontal_to_screen(90.0, 0.0, w, h)
    assert north[1] < 100 and north[0] == pytest.approx(100.0)  # top
    assert east[0] < 100 and east[1] == pytest.approx(100.0)  # left, as seen looking up
    assert utils.horizontal_to_screen(10.0, -5.0, w, h) is None


def test_fps_counter_smooths_rate() -> None:
    counter = utils.FPSCounter(smoothing=0.5)
    counter.tick(0.0)
    assert counter.tick(0.1) == pytest.approx(10.0)
    assert counter.tick(0.15) == pytest.approx(15.0)  # 0.5*10 + 0.5*20


def test_annotate_frame_draws_overlays(db: ConstellationDB) -> None:
    pipeline = SkyPipeline(db, PipelineConfig.from_file("config.yaml"))
    report = None
    frame = None
    for k, frame in enumerate(demo_sky_clip(db["Orion"], 12, width=640, height=480)):
        report = pipeline.process(frame, k)
    assert report is not None and frame is not None
    out = utils.annotate_frame(frame, report, fps=24.0)
    assert out.shape == (480, 640, 3)
    gold = np.all(out == np.array(utils.GOLD, dtype=np.uint8), axis=-1)
    assert gold.sum() > 200  # constellation lines were drawn


def test_annotate_frame_reports_empty_sky(db: ConstellationDB) -> None:
    pipeline = SkyPipeline(db, PipelineConfig.from_file("config.yaml"))
    black = np.zeros((240, 320), dtype=np.uint8)
    out = utils.annotate_frame(black, pipeline.process(black, 0))
    assert out.shape == (240, 320, 3) and out.max() > 0  # message text drawn


def test_downscale_preserves_faint_star_peaks() -> None:
    from astragraph.detect import StarDetector
    from astragraph.synthetic import SyntheticStar, render_star_field

    stars = [SyntheticStar(200.0 + 150 * i, 300.0, 200.0, 1.2) for i in range(10)]
    frame = render_star_field(stars, 1920, 1080)
    small, _ = utils.downscale(frame, 1280)
    assert len(StarDetector().detect(small)) == len(stars)


def test_downscale_keeps_aspect_ratio() -> None:
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    small, scale = utils.downscale(frame, 960)
    assert small.shape == (540, 960, 3) and scale == pytest.approx(0.5)
    same, scale = utils.downscale(np.zeros((100, 100), dtype=np.uint8), 960)
    assert same.shape == (100, 100) and scale == 1.0


# ------------------------------------------------- webcam frame processor
def test_video_processor_identifies_constellation_fast(db, demo_module) -> None:
    processor = demo_module.SkyVideoProcessor(db, PipelineConfig.from_file("config.yaml"))
    frames = [np.dstack([f] * 3) for f in demo_sky_clip(db["Orion"], 30, width=1920, height=1080)]
    started = time.perf_counter()
    for frame in frames:
        out = processor.process(frame)
    elapsed = time.perf_counter() - started
    assert out.shape[1] == 1280  # 1080p input is downscaled for speed
    report = processor.last_report
    assert report is not None
    assert [m.constellation for m in report.constellations] == ["Orion"]
    assert len(frames) / elapsed > 10  # live-mode target: 10+ FPS


def test_video_processor_recv_round_trips_av_frames(db, demo_module) -> None:
    av = pytest.importorskip("av")
    processor = demo_module.SkyVideoProcessor(db, PipelineConfig.from_file("config.yaml"))
    gray = next(iter(demo_sky_clip(db["Lyra"], 1, width=640, height=480)))
    frame = av.VideoFrame.from_ndarray(np.dstack([gray] * 3), format="bgr24")
    out = processor.recv(frame)
    assert isinstance(out, av.VideoFrame)
    assert (out.width, out.height) == (640, 480)


def test_video_processor_survives_pipeline_errors(db, demo_module, monkeypatch) -> None:
    processor = demo_module.SkyVideoProcessor(db, PipelineConfig.from_file("config.yaml"))

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(processor.pipeline, "process", boom)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    out = processor.process(frame)  # must not raise
    assert out.shape == frame.shape and out.max() > 0  # error text drawn


def test_sky_chart_renders(db, demo_module) -> None:
    from astragraph.world_model import SkyWorldModel

    model = SkyWorldModel(constellation_db=db)
    fig = demo_module.sky_chart(model, db, datetime(2024, 1, 15, 2, tzinfo=timezone.utc),
                                40.7128, -74.006, highlight="Orion")
    assert fig.axes and fig.axes[0].name == "polar"


# ------------------------------------------------------------ whole app
def run_app(mode: str | None = None, *, timeout: float = 60) -> AppTest:
    app = AppTest.from_file(str(ROOT / "app" / "demo.py"), default_timeout=timeout)
    app.run()
    if mode is not None:
        app.sidebar.radio[0].set_value(mode).run()
    return app


def test_app_starts_in_live_camera_mode_without_errors() -> None:
    app = run_app()
    assert not app.exception
    assert not app.error
    assert any("Live Camera" in h.value for h in app.header)


def test_live_camera_demo_sky_identifies_constellation() -> None:
    app = run_app()
    app.slider[0].set_value(30).run()
    app.button[0].click().run()
    assert not app.exception and not app.error
    assert any("Orion" in s.value for s in app.success)


def test_time_travel_mode_shows_prediction_message() -> None:
    app = run_app("Time Travel")
    assert not app.exception and not app.error
    app.slider[0].set_value(3.0).run()
    messages = [m.value for m in (*app.success, *app.warning, *app.info)]
    assert any(msg.startswith("In 3 hours, Orion will be at azimuth") for msg in messages)


def test_learn_mode_shows_position_and_best_time() -> None:
    app = run_app("Learn")
    assert not app.exception and not app.error
    assert any("Best time to view" in s.value for s in app.subheader)
    text = " ".join(m.value for m in app.markdown)
    assert "9 pm in January" in text
    app.selectbox(key="learn_name").set_value("Scorpius").run()
    assert not app.exception
    assert "9 pm in" in " ".join(m.value for m in app.markdown)


def _button(app: AppTest, label: str):
    return next(b for b in app.button if label in b.label)


def test_academy_quiz_dropdown_flow_scores_answer() -> None:
    app = run_app("Academy")
    assert not app.exception and not app.error
    assert any("AstroAcademy" in h.value for h in app.header)
    app.selectbox(key="quiz_name").set_value("Lyra").run()

    # Draw one correct Lyra line and one wrong one with the dropdown fallback.
    for a, b in (("Vega", "Zeta Lyrae"), ("Vega", "Sulafat")):
        app.selectbox(key="quiz_from").set_value(a)
        app.selectbox(key="quiz_to").set_value(b)
        _button(app, "Connect").click().run()
    assert app.metric[0].value == "2"

    _button(app, "Submit").click().run()
    assert not app.exception
    warnings = " ".join(w.value for w in app.warning)
    assert "Score: **12%**" in warnings  # 1 right / (7 correct + 1 extra) = 12.5%
    assert "1 correct, 6 missing, 1 extra" in warnings


def test_academy_undo_and_clear() -> None:
    app = run_app("Academy")
    app.selectbox(key="quiz_name").set_value("Cassiopeia").run()
    app.selectbox(key="quiz_from").set_value("Caph")
    app.selectbox(key="quiz_to").set_value("Schedar")
    _button(app, "Connect").click().run()
    assert app.metric[0].value == "1"
    _button(app, "Undo").click().run()
    assert app.metric[0].value == "0"
    _button(app, "Connect").click().run()
    _button(app, "Clear").click().run()
    assert app.metric[0].value == "0"


def test_academy_perfect_quiz_celebrates() -> None:
    from astragraph.academy import normalize_edges

    database = ConstellationDB.from_config("config.yaml")
    database.load()
    app = run_app("Academy")
    app.selectbox(key="quiz_name").set_value("Cassiopeia").run()
    for a, b in normalize_edges(database["Cassiopeia"].edges):
        app.selectbox(key="quiz_from").set_value(a)
        app.selectbox(key="quiz_to").set_value(b)
        _button(app, "Connect").click().run()
    _button(app, "Submit").click().run()
    assert any("Perfect" in s.value for s in app.success)


def test_academy_info_tab_shows_card() -> None:
    app = run_app("Academy")
    app.selectbox(key="info_name").set_value("Scorpius").run()
    assert not app.exception and not app.error
    text = " ".join(m.value for m in app.markdown)
    assert "Mythology" in text and "Key stars" in text and "Antares" in text
    assert any("Ophiuchus" in i.value for i in app.info)  # Scorpius fun fact
