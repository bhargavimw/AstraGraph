"""Star detection: find bright point sources in a camera frame.

Pipeline (see :meth:`StarDetector.detect`):

1. Convert to grayscale and apply a small Gaussian blur to suppress sensor noise.
2. Find candidate blobs with :class:`cv2.SimpleBlobDetector`, tuned for small
   bright points on a dark background.
3. Measure each candidate on the thresholded connected component it belongs to
   and apply noise filters:

   * aspect ratio above ``max_aspect_ratio`` → rejected (aircraft/satellite trails),
   * peak brightness below ``min_brightness`` → rejected (noise, faint glow),
   * component touching the image border → rejected (partially visible source),
   * area below ``min_size`` pixels → rejected (hot pixels, single-pixel noise).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class StarDetection:
    """One detected point source.

    Attributes:
        id: Index within the frame, ordered from brightest (0) to faintest.
        x, y: Sub-pixel centroid in image coordinates.
        brightness: Peak 8-bit intensity of the source (0–255).
        size: Area in pixels of the source above the detection threshold.
    """

    id: int
    x: float
    y: float
    brightness: float
    size: float


@dataclass(frozen=True)
class DetectorConfig:
    """Tunable detector thresholds (mirrors the ``detector`` block of config.yaml)."""

    min_brightness: float = 180.0
    min_size: float = 3.0
    max_aspect_ratio: float = 2.0
    blur_kernel: int = 3
    max_size: float = 40.0
    min_dist_between_blobs: float = 3.0

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "DetectorConfig":
        values = values or {}
        known = {f: values[f] for f in cls.__dataclass_fields__ if f in values}
        return cls(**known)


@dataclass(frozen=True)
class _Component:
    aspect_ratio: float
    area: float
    peak: float
    touches_border: bool


def to_grayscale(frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Return a single-channel ``uint8`` image (BGR, BGRA and gray accepted)."""
    if frame.ndim == 2:
        gray = frame
    elif frame.ndim == 3 and frame.shape[2] == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    elif frame.ndim == 3 and frame.shape[2] == 4:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
    else:
        raise ValueError(f"Unsupported frame shape: {frame.shape}")
    if gray.dtype != np.uint8:
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return gray


def _measure_component(
    labels: NDArray[np.int32],
    stats: NDArray[np.int32],
    label: int,
    gray: NDArray[np.uint8],
) -> _Component:
    """Shape and brightness measurements for one connected component."""
    x, y, w, h, area = (int(v) for v in stats[label])
    height, width = labels.shape
    touches_border = x == 0 or y == 0 or x + w >= width or y + h >= height

    window = labels[y : y + h, x : x + w] == label
    ys, xs = np.nonzero(window)
    peak = float(gray[y : y + h, x : x + w][window].max())
    if len(xs) < 2:
        return _Component(1.0, float(area), peak, touches_border)

    # Principal axes from the second moments; +1/12 accounts for pixel extent.
    cov = np.cov(np.vstack([xs, ys]).astype(float), bias=True) + np.eye(2) / 12.0
    eigvals = np.linalg.eigvalsh(cov)
    aspect = math.sqrt(eigvals[1] / eigvals[0]) if eigvals[0] > 0 else math.inf
    return _Component(aspect, float(area), peak, touches_border)


class StarDetector:
    """Detect stars in a frame with OpenCV blob detection plus noise filters."""

    def __init__(self, config: DetectorConfig | None = None) -> None:
        self.config = config or DetectorConfig()
        self._blob_detector = cv2.SimpleBlobDetector_create(self._blob_params())

    def _blob_params(self) -> cv2.SimpleBlobDetector_Params:
        cfg = self.config
        params = cv2.SimpleBlobDetector_Params()
        params.filterByColor = True
        params.blobColor = 255  # bright blobs on a dark sky
        # Threshold sweep starts well below min_brightness so faint halos of
        # bright stars are still found; the brightness filter runs afterwards.
        params.minThreshold = max(cfg.min_brightness / 3.0, 10.0)
        params.maxThreshold = 255.0
        params.thresholdStep = 10.0
        params.minRepeatability = 2
        params.minDistBetweenBlobs = cfg.min_dist_between_blobs
        params.filterByArea = True
        params.minArea = 1.0
        params.maxArea = math.pi * (cfg.max_size / 2.0) ** 2
        # Shape filtering is done on measured moments instead (see module doc).
        params.filterByCircularity = False
        params.filterByConvexity = False
        params.filterByInertia = False
        return params

    def detect(self, frame: NDArray[np.uint8]) -> list[StarDetection]:
        """Detect stars in ``frame`` and return them brightest first."""
        cfg = self.config
        gray = to_grayscale(frame)
        k = max(int(cfg.blur_kernel) | 1, 1)  # kernel must be odd
        blurred = cv2.GaussianBlur(gray, (k, k), 0) if k > 1 else gray

        keypoints = self._blob_detector.detect(blurred)
        if not keypoints:
            return []

        # Components at half the brightness threshold define each source's extent.
        level = cfg.min_brightness / 2.0
        _, binary = cv2.threshold(blurred, level, 255, cv2.THRESH_BINARY)
        _, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

        candidates: list[tuple[float, float, float, float]] = []
        seen_labels: set[int] = set()
        for kp in keypoints:
            cx, cy = kp.pt
            label = int(labels[min(int(round(cy)), labels.shape[0] - 1),
                               min(int(round(cx)), labels.shape[1] - 1)])
            if label == 0 or label in seen_labels:
                continue
            component = _measure_component(labels, stats, label, gray)
            if component.touches_border:
                continue
            if component.aspect_ratio > cfg.max_aspect_ratio:
                continue
            if component.peak < cfg.min_brightness:
                continue
            if component.area < cfg.min_size:
                continue
            seen_labels.add(label)
            sx, sy = self._refine_centroid(blurred, labels, stats, label)
            candidates.append((sx, sy, component.peak, component.area))

        candidates.sort(key=lambda c: (-c[2], c[1], c[0]))
        return [
            StarDetection(i, x, y, brightness, size)
            for i, (x, y, brightness, size) in enumerate(candidates)
        ]

    @staticmethod
    def _refine_centroid(
        image: NDArray[np.uint8],
        labels: NDArray[np.int32],
        stats: NDArray[np.int32],
        label: int,
    ) -> tuple[float, float]:
        """Intensity-weighted centroid of a component (sub-pixel accuracy)."""
        x, y, w, h, _ = (int(v) for v in stats[label])
        mask = labels[y : y + h, x : x + w] == label
        weights = image[y : y + h, x : x + w].astype(float) * mask
        total = weights.sum()
        ys, xs = np.mgrid[y : y + h, x : x + w]
        return float((xs * weights).sum() / total), float((ys * weights).sum() / total)
