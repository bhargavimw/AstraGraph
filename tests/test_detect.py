"""Tests for the OpenCV star detector."""

from __future__ import annotations

import numpy as np
import pytest

from astragraph.detect import DetectorConfig, StarDetection, StarDetector
from astragraph.synthetic import (
    SyntheticStar,
    draw_streak,
    render_star_field,
)

WIDTH, HEIGHT = 640, 480


def random_star_field(
    count: int, seed: int, *, min_separation: float = 8.0
) -> list[SyntheticStar]:
    """Bright, well-separated random stars away from the image border."""
    rng = np.random.default_rng(seed)
    stars: list[SyntheticStar] = []
    while len(stars) < count:
        x, y = rng.uniform(20, WIDTH - 20), rng.uniform(20, HEIGHT - 20)
        if all(np.hypot(s.x - x, s.y - y) >= min_separation for s in stars):
            stars.append(
                SyntheticStar(x, y, rng.uniform(190, 255), rng.uniform(1.0, 2.2))
            )
    return stars


def recall(stars: list[SyntheticStar], detections: list[StarDetection]) -> float:
    """Fraction of true stars with a detection within 1.5 px."""
    if not detections:
        return 0.0
    found = np.array([[d.x, d.y] for d in detections])
    hits = sum(
        np.min(np.hypot(found[:, 0] - s.x, found[:, 1] - s.y)) <= 1.5 for s in stars
    )
    return hits / len(stars)


@pytest.fixture
def detector() -> StarDetector:
    return StarDetector(DetectorConfig())


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_detector_finds_over_90_percent_of_bright_stars(
    detector: StarDetector, seed: int
) -> None:
    stars = random_star_field(80, seed)
    image = render_star_field(stars, WIDTH, HEIGHT, noise_std=5.0, seed=seed)
    detections = detector.detect(image)
    assert recall(stars, detections) > 0.9
    # Noise must not create many phantom stars either.
    assert len(detections) <= len(stars) * 1.05


def test_detection_positions_are_subpixel_accurate(detector: StarDetector) -> None:
    star = SyntheticStar(100.3, 80.7, 240.0, 1.6)
    detections = detector.detect(render_star_field([star], 200, 160))
    assert len(detections) == 1
    assert detections[0].x == pytest.approx(100.3, abs=0.15)
    assert detections[0].y == pytest.approx(80.7, abs=0.15)


def test_detections_are_ordered_brightest_first(detector: StarDetector) -> None:
    stars = [
        SyntheticStar(50, 50, 200.0),
        SyntheticStar(120, 60, 250.0),
        SyntheticStar(80, 120, 225.0),
    ]
    detections = detector.detect(render_star_field(stars, 200, 200))
    assert [d.id for d in detections] == [0, 1, 2]
    assert [round(d.x) for d in detections] == [120, 80, 50]


def test_elongated_streak_is_rejected(detector: StarDetector) -> None:
    star = SyntheticStar(60, 60, 240.0)
    image = render_star_field([star], 320, 240)
    image = draw_streak(image, (100, 180), (260, 120))  # aircraft trail
    detections = detector.detect(image)
    assert len(detections) == 1
    assert detections[0].x == pytest.approx(60, abs=0.5)


def test_short_trail_just_above_aspect_limit_is_rejected(
    detector: StarDetector,
) -> None:
    image = render_star_field([], 200, 200)
    image = draw_streak(image, (90, 100), (110, 100), thickness=1.5)
    assert detector.detect(image) == []


def test_faint_blobs_below_brightness_threshold_are_rejected(
    detector: StarDetector,
) -> None:
    stars = [SyntheticStar(50, 50, 240.0), SyntheticStar(120, 120, 140.0)]
    detections = detector.detect(render_star_field(stars, 200, 200))
    assert len(detections) == 1
    assert detections[0].brightness >= 180


def test_blob_touching_border_is_rejected(detector: StarDetector) -> None:
    stars = [SyntheticStar(1.0, 100, 250.0), SyntheticStar(100, 100, 250.0)]
    detections = detector.detect(render_star_field(stars, 200, 200))
    assert len(detections) == 1
    assert detections[0].x == pytest.approx(100, abs=0.5)


def test_single_hot_pixel_is_rejected(detector: StarDetector) -> None:
    image = render_star_field([], 100, 100)
    image[50, 50] = 255
    assert detector.detect(image) == []


def test_color_frames_are_supported(detector: StarDetector) -> None:
    gray = render_star_field([SyntheticStar(60, 60, 240.0)], 120, 120)
    bgr = np.dstack([gray, gray, gray])
    assert len(detector.detect(bgr)) == 1


def test_empty_sky_returns_no_detections(detector: StarDetector) -> None:
    assert detector.detect(render_star_field([], 64, 64, noise_std=3.0)) == []
