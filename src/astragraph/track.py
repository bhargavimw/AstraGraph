"""Frame-to-frame star tracking with stable IDs.

A centroid tracker with constant-velocity prediction:

* Each live track predicts where it will be in the next frame from its last
  two positions (stars stay put; satellites keep moving).
* Detections are assigned to tracks greedily by smallest predicted distance,
  never exceeding ``max_distance`` pixels (a pure function, :func:`associate`).
* Unmatched detections start new tracks; tracks unmatched for more than
  ``max_disappeared`` consecutive frames are dropped. Within that grace period
  a star hidden by a passing cloud keeps its ID when it reappears.

ByteTrack (ultralytics) is not used: star detections have no appearance
features or class scores, so plain motion-based association is enough here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from astragraph.detect import StarDetection

Point = tuple[float, float]


@dataclass(frozen=True)
class TrackedStar:
    """A star (or moving object) followed across frames.

    Attributes:
        id: Stable track ID, unique for the lifetime of the tracker.
        x, y: Last observed position.
        brightness: Last observed peak brightness.
        frame_count: Number of frames in which the track was detected.
        trajectory: Observed ``(x, y)`` positions, oldest first.
        missed: Consecutive frames without a matching detection (0 = seen now).
        frame_indices: Frame index of each trajectory point.
    """

    id: int
    x: float
    y: float
    brightness: float
    frame_count: int
    trajectory: tuple[Point, ...]
    missed: int = 0
    frame_indices: tuple[int, ...] = field(default=())

    @property
    def visible(self) -> bool:
        """Whether the track was matched to a detection in the latest frame."""
        return self.missed == 0

    def velocity(self) -> Point:
        """Mean velocity in pixels/frame over the trajectory (0 if too short)."""
        if len(self.trajectory) < 2 or len(self.frame_indices) < 2:
            return (0.0, 0.0)
        span = self.frame_indices[-1] - self.frame_indices[0]
        if span <= 0:
            return (0.0, 0.0)
        (x0, y0), (x1, y1) = self.trajectory[0], self.trajectory[-1]
        return ((x1 - x0) / span, (y1 - y0) / span)

    def predicted_position(self, frame_idx: int) -> Point:
        """Constant-velocity prediction from the last two observations."""
        if len(self.trajectory) < 2:
            return (self.x, self.y)
        (x0, y0), (x1, y1) = self.trajectory[-2], self.trajectory[-1]
        f0, f1 = self.frame_indices[-2], self.frame_indices[-1]
        if f1 == f0:
            return (x1, y1)
        vx, vy = (x1 - x0) / (f1 - f0), (y1 - y0) / (f1 - f0)
        dt = frame_idx - f1
        return (x1 + vx * dt, y1 + vy * dt)


@dataclass(frozen=True)
class TrackerConfig:
    """Tracker parameters (mirrors the ``tracking`` block of config.yaml)."""

    max_distance: float = 15.0
    max_disappeared: int = 5
    max_trajectory: int = 120

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "TrackerConfig":
        values = values or {}
        known = {f: values[f] for f in cls.__dataclass_fields__ if f in values}
        return cls(**known)


def associate(
    predictions: Sequence[Point],
    detections: Sequence[Point],
    max_distance: float,
) -> list[tuple[int, int]]:
    """Greedy one-to-one assignment of detections to predicted positions.

    Pairs are taken in order of increasing distance, so the closest pairs win
    conflicts. Returns ``(prediction_index, detection_index)`` pairs whose
    distance does not exceed ``max_distance``. Pure and deterministic.
    """
    if not predictions or not detections:
        return []
    pred = np.asarray(predictions, dtype=float).reshape(-1, 2)
    det = np.asarray(detections, dtype=float).reshape(-1, 2)
    dist = np.linalg.norm(pred[:, None, :] - det[None, :, :], axis=-1)

    order = np.argsort(dist, axis=None, kind="stable")
    used_pred: set[int] = set()
    used_det: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for flat in order:
        i, j = divmod(int(flat), det.shape[0])
        if dist[i, j] > max_distance:
            break
        if i in used_pred or j in used_det:
            continue
        used_pred.add(i)
        used_det.add(j)
        pairs.append((i, j))
    return sorted(pairs)


class StarTracker:
    """Assign stable IDs to detections across a sequence of frames."""

    def __init__(self, config: TrackerConfig | None = None) -> None:
        self.config = config or TrackerConfig()
        self._tracks: dict[int, TrackedStar] = {}
        self._next_id = 0
        self._frame_idx = -1

    @property
    def tracks(self) -> list[TrackedStar]:
        """All live tracks (visible or within the disappearance grace period)."""
        return sorted(self._tracks.values(), key=lambda t: t.id)

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 0
        self._frame_idx = -1

    def track(
        self,
        frame: object | None,
        detections: Sequence[StarDetection],
        frame_idx: int | None = None,
    ) -> list[TrackedStar]:
        """Update tracks with this frame's detections.

        Args:
            frame: The image (unused by the centroid tracker; accepted so the
                signature matches appearance-based trackers).
            detections: Output of :meth:`StarDetector.detect` for this frame.
            frame_idx: Frame number; defaults to the previous index + 1.

        Returns:
            Every live track, sorted by ID. Tracks seen this frame have
            ``missed == 0``; occluded ones keep their last position.
        """
        del frame
        self._frame_idx = self._frame_idx + 1 if frame_idx is None else frame_idx
        idx = self._frame_idx

        live = self.tracks
        predictions = [t.predicted_position(idx) for t in live]
        points = [(d.x, d.y) for d in detections]
        pairs = associate(predictions, points, self.config.max_distance)

        matched_tracks = {i for i, _ in pairs}
        matched_dets = {j for _, j in pairs}
        limit = self.config.max_trajectory
        updated: dict[int, TrackedStar] = {}

        for i, j in pairs:
            t, d = live[i], detections[j]
            updated[t.id] = replace(
                t,
                x=d.x,
                y=d.y,
                brightness=d.brightness,
                frame_count=t.frame_count + 1,
                trajectory=(t.trajectory + ((d.x, d.y),))[-limit:],
                frame_indices=(t.frame_indices + (idx,))[-limit:],
                missed=0,
            )

        for i, t in enumerate(live):
            if i in matched_tracks:
                continue
            if t.missed + 1 <= self.config.max_disappeared:
                updated[t.id] = replace(t, missed=t.missed + 1)

        for j, d in enumerate(detections):
            if j in matched_dets:
                continue
            new = TrackedStar(
                id=self._next_id,
                x=d.x,
                y=d.y,
                brightness=d.brightness,
                frame_count=1,
                trajectory=((d.x, d.y),),
                frame_indices=(idx,),
            )
            updated[new.id] = new
            self._next_id += 1

        self._tracks = updated
        return self.tracks
