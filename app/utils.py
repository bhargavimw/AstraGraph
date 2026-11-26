"""Drawing and projection helpers for the AstraGraph Streamlit app.

OpenCV overlays use BGR colours (OpenCV's channel order). Frames coming from
streamlit-webrtc are converted to BGR before drawing.
"""

from __future__ import annotations

import math
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from astragraph.detect import StarDetection  # noqa: E402
from astragraph.matcher import MatchResult  # noqa: E402
from astragraph.pipeline import FrameReport  # noqa: E402

Point = tuple[float, float]
Image = NDArray[np.uint8]

# BGR colours
GREEN = (80, 220, 80)
GOLD = (40, 190, 255)
CYAN = (255, 220, 60)
RED = (60, 60, 255)
MAGENTA = (255, 80, 255)
WHITE = (240, 240, 240)
SHADOW = (0, 0, 0)

FONT = cv2.FONT_HERSHEY_SIMPLEX


def ensure_bgr(frame: Image) -> Image:
    """Return a 3-channel BGR copy of ``frame`` (gray and BGRA accepted)."""
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return frame.copy()


def _pt(point: Point) -> tuple[int, int]:
    return int(round(point[0])), int(round(point[1]))


def put_label(
    frame: Image, text: str, origin: Point, color: tuple[int, int, int],
    scale: float = 0.55, thickness: int = 1,
) -> None:
    """Text with a dark outline so it stays readable over bright sky glow."""
    x, y = _pt(origin)
    cv2.putText(frame, text, (x, y), FONT, scale, SHADOW, thickness + 2, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), FONT, scale, color, thickness, cv2.LINE_AA)


def draw_stars(
    frame: Image, stars: Iterable[StarDetection | Point], *,
    color: tuple[int, int, int] = GREEN, radius: int = 7,
) -> None:
    """Green circles around detected stars."""
    for star in stars:
        center = (star.x, star.y) if isinstance(star, StarDetection) else star
        cv2.circle(frame, _pt(center), radius, color, 1, cv2.LINE_AA)


def draw_constellation(frame: Image, match: MatchResult) -> None:
    """Gold stick-figure lines, cyan ghost rings and the constellation label."""
    if not match.matched:
        return
    for start, end in match.line_segments:
        cv2.line(frame, _pt(start), _pt(end), GOLD, 2, cv2.LINE_AA)
    for name, position in match.ghost_positions.items():
        cv2.circle(frame, _pt(position), 9, CYAN, 1, cv2.LINE_AA)
        put_label(frame, name, (position[0] + 12, position[1] + 4), CYAN, 0.45)
    points = [p for segment in match.line_segments for p in segment]
    if points:
        left = min(p[0] for p in points)
        top = min(p[1] for p in points)
        put_label(
            frame, f"{match.constellation} ({match.confidence:.0%})",
            (left, max(top - 14, 22)), GOLD, 0.75, 2,
        )


def draw_fps(frame: Image, fps: float) -> None:
    """FPS counter in the top-right corner."""
    text = f"{fps:4.1f} FPS"
    (w, _), _ = cv2.getTextSize(text, FONT, 0.6, 2)
    put_label(frame, text, (frame.shape[1] - w - 12, 26), WHITE, 0.6, 2)


def draw_message(frame: Image, text: str) -> None:
    """Centered status message at the bottom (e.g. "No stars detected")."""
    (w, _), _ = cv2.getTextSize(text, FONT, 0.7, 2)
    put_label(frame, text, ((frame.shape[1] - w) / 2, frame.shape[0] - 20), WHITE, 0.7, 2)


def annotate_frame(frame: Image, report: FrameReport, fps: float | None = None) -> Image:
    """Full overlay for one processed frame; returns a new BGR image."""
    canvas = ensure_bgr(frame)
    satellites = {s.track_id for s in report.satellites}
    anomalies = set(report.anomalies)

    for match in report.constellations:
        draw_constellation(canvas, match)

    plain = []
    for track in report.tracks:
        if not track.visible:
            continue
        if track.id in satellites:
            pts = np.array(track.trajectory, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(canvas, [pts], False, RED, 2, cv2.LINE_AA)
            cv2.circle(canvas, _pt((track.x, track.y)), 8, RED, 2, cv2.LINE_AA)
            put_label(canvas, "satellite", (track.x + 10, track.y - 10), RED, 0.5)
        elif track.id in anomalies:
            cv2.circle(canvas, _pt((track.x, track.y)), 10, MAGENTA, 2, cv2.LINE_AA)
            put_label(canvas, "not in catalog", (track.x + 12, track.y + 4), MAGENTA, 0.5)
        else:
            plain.append((track.x, track.y))
    draw_stars(canvas, plain)

    if not report.detections:
        draw_message(canvas, "No stars detected - point at a dark, clear sky")
    elif not report.constellations:
        draw_message(canvas, f"{len(report.detections)} stars - no constellation yet")
    if fps is not None:
        draw_fps(canvas, fps)
    return canvas


class FPSCounter:
    """Exponential moving average of frames per second."""

    def __init__(self, smoothing: float = 0.9) -> None:
        self.smoothing = smoothing
        self._last: float | None = None
        self.fps = 0.0

    def tick(self, now: float | None = None) -> float:
        now = time.perf_counter() if now is None else now
        if self._last is not None:
            dt = now - self._last
            if dt > 0:
                instant = 1.0 / dt
                self.fps = instant if self.fps == 0 else (
                    self.smoothing * self.fps + (1 - self.smoothing) * instant
                )
        self._last = now
        return self.fps


def horizontal_to_screen(
    azimuth: float, altitude: float, width: int, height: int, *, margin: int = 10
) -> Point | None:
    """Map (azimuth, altitude) to pixels on a planisphere-style sky chart.

    Zenith at the centre, horizon on the rim, north up and east on the left
    (as seen looking up). Returns ``None`` for objects below the horizon.
    """
    if altitude < 0:
        return None
    radius = min(width, height) / 2 - margin
    r = (90.0 - altitude) / 90.0 * radius
    a = math.radians(azimuth)
    return (width / 2 - r * math.sin(a), height / 2 - r * math.cos(a))


def screen_positions(
    points: Sequence[tuple[float, float]], width: int, height: int
) -> list[Point | None]:
    """Vector form of :func:`horizontal_to_screen` for (az, alt) pairs."""
    return [horizontal_to_screen(az, alt, width, height) for az, alt in points]


def downscale(frame: Image, max_width: int = 960) -> tuple[Image, float]:
    """Shrink wide frames for speed; returns the frame and the scale applied.

    Stars are only a few pixels wide, so plain area averaging would blend
    them with the dark sky and push their peaks below the detection
    threshold. A max filter sized to the reduction factor runs first, so each
    output pixel keeps the brightest value of the pixels it replaces.
    """
    if frame.shape[1] <= max_width:
        return frame, 1.0
    scale = max_width / frame.shape[1]
    size = (max_width, int(round(frame.shape[0] * scale)))
    k = max(1, int(np.ceil(1.0 / scale)))
    if k > 1:
        frame = cv2.dilate(frame, np.ones((k, k), dtype=np.uint8))
    return cv2.resize(frame, size, interpolation=cv2.INTER_AREA), scale
