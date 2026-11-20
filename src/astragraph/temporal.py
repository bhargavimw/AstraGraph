"""Temporal scene graph: events, clusters and moving-object detection.

Each frame, :class:`TemporalGraphBuilder` turns tracked stars into a graph
``G_t`` (nodes = tracks, edges = ``near(A, B)``), diffs it against ``G_{t-1}``
and extracts events:

* ``APPEARS`` – a track has been visible for ``debounce_frames`` consecutive
  frames (so a single noisy detection never produces an event).
* ``DISAPPEARS`` – an announced track has been missing for
  ``max_disappeared`` frames (the occlusion grace period: a star behind a
  passing cloud for a moment is not reported as gone).
* ``MOVES`` – a track has drifted more than ``move_threshold`` pixels from its
  anchor, relative to the whole sky, for ``debounce_frames`` frames.
* ``LINEAR_TRAJECTORY`` – the track's sky-relative path is a straight line and
  its speed exceeds ``satellite_velocity_threshold`` px/frame for
  ``debounce_frames`` frames: a satellite (or meteor) candidate.

Camera motion is compensated: the median displacement of all tracks between
frames is treated as ego-motion, so panning the phone does not make every
star "move" or look like a satellite.

Stars are grouped into clusters with a union-find (disjoint-set) structure
implemented from scratch: ``near`` is reflexive and symmetric, and its
transitive closure is an equivalence relation whose classes are the clusters.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import networkx as nx
import numpy as np

from astragraph.track import Point, TrackedStar


class EventType(str, Enum):
    APPEARS = "APPEARS"
    DISAPPEARS = "DISAPPEARS"
    MOVES = "MOVES"
    LINEAR_TRAJECTORY = "LINEAR_TRAJECTORY"


@dataclass(frozen=True)
class Event:
    """Something that happened at frame ``t``; ``args`` holds event details."""

    t: int
    type: EventType
    args: Mapping[str, Any] = field(default_factory=dict)


class UnionFind:
    """Disjoint-set forest with path compression and union by rank."""

    def __init__(self, items: Iterable[Hashable] = ()) -> None:
        self._parent: dict[Hashable, Hashable] = {}
        self._rank: dict[Hashable, int] = {}
        for item in items:
            self.add(item)

    def add(self, item: Hashable) -> None:
        if item not in self._parent:
            self._parent[item] = item
            self._rank[item] = 0

    def find(self, item: Hashable) -> Hashable:
        """Return the representative of ``item``'s set (adds unknown items)."""
        self.add(item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:  # path compression
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: Hashable, b: Hashable) -> bool:
        """Merge the sets of ``a`` and ``b``; return False if already joined."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1
        return True

    def connected(self, a: Hashable, b: Hashable) -> bool:
        return self.find(a) == self.find(b)

    def groups(self) -> list[list[Hashable]]:
        """All sets, each sorted, ordered by size (largest first) then content."""
        buckets: dict[Hashable, list[Hashable]] = {}
        for item in self._parent:
            buckets.setdefault(self.find(item), []).append(item)
        groups = [sorted(g, key=repr) for g in buckets.values()]
        return sorted(groups, key=lambda g: (-len(g), repr(g[0])))


def cluster_points(
    points: Mapping[Hashable, Point], threshold: float
) -> list[list[Hashable]]:
    """Group points whose ``near`` chains link them (distance < ``threshold``)."""
    uf = UnionFind(points)
    keys = list(points)
    for i, a in enumerate(keys):
        ax, ay = points[a]
        for b in keys[i + 1 :]:
            bx, by = points[b]
            if math.hypot(ax - bx, ay - by) < threshold:
                uf.union(a, b)
    return uf.groups()


def linear_fit_residual(points: Sequence[Point]) -> float:
    """RMS perpendicular distance of points from their best-fit line (PCA)."""
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    if len(pts) < 3:
        return 0.0
    centred = pts - pts.mean(axis=0)
    # Smallest singular value / sqrt(n) = RMS distance to the principal axis.
    singular = np.linalg.svd(centred, compute_uv=False)
    return float(singular[-1] / math.sqrt(len(pts)))


def is_linear_trajectory(
    points: Sequence[Point], *, tolerance: float, min_points: int
) -> bool:
    """True when there are enough points and they lie on a straight line."""
    return len(points) >= min_points and linear_fit_residual(points) <= tolerance


def steady_speed(points: Sequence[Point], frame_indices: Sequence[int]) -> float:
    """Median per-frame speed along a path.

    Unlike the mean speed, the median ignores a single jump (a star nudged by
    hand shake), so only objects that move *every* frame score highly.
    """
    if len(points) < 2:
        return 0.0
    speeds = []
    for (x0, y0), (x1, y1), f0, f1 in zip(
        points, points[1:], frame_indices, frame_indices[1:]
    ):
        if f1 > f0:
            speeds.append(math.hypot(x1 - x0, y1 - y0) / (f1 - f0))
    return float(np.median(speeds)) if speeds else 0.0


@dataclass(frozen=True)
class GraphDiff:
    """Change between two consecutive scene graphs."""

    added_nodes: frozenset[int]
    removed_nodes: frozenset[int]
    added_edges: frozenset[frozenset[int]]
    removed_edges: frozenset[frozenset[int]]

    @property
    def empty(self) -> bool:
        return not (
            self.added_nodes or self.removed_nodes or self.added_edges or self.removed_edges
        )


def graph_diff(previous: nx.Graph, current: nx.Graph) -> GraphDiff:
    """Node and edge set differences from ``previous`` to ``current``."""
    prev_edges = {frozenset(e) for e in previous.edges}
    cur_edges = {frozenset(e) for e in current.edges}
    return GraphDiff(
        added_nodes=frozenset(set(current.nodes) - set(previous.nodes)),
        removed_nodes=frozenset(set(previous.nodes) - set(current.nodes)),
        added_edges=frozenset(cur_edges - prev_edges),
        removed_edges=frozenset(prev_edges - cur_edges),
    )


@dataclass(frozen=True)
class TemporalConfig:
    """Event-extraction parameters (``tracking``/``temporal`` in config.yaml)."""

    max_disappeared: int = 5
    debounce_frames: int = 3
    cluster_distance: float = 150.0
    move_threshold: float = 5.0
    satellite_velocity_threshold: float = 1.0
    linear_tolerance: float = 0.75
    min_trajectory_points: int = 6
    compensate_camera_motion: bool = True

    @classmethod
    def from_mapping(cls, *sections: Mapping[str, Any] | None) -> "TemporalConfig":
        """Build from one or more config sections (later sections win)."""
        merged: dict[str, Any] = {}
        for section in sections:
            merged.update(section or {})
        known = {f: merged[f] for f in cls.__dataclass_fields__ if f in merged}
        return cls(**known)


@dataclass
class _TrackState:
    present_streak: int = 0
    announced: bool = False
    anchor: Point | None = None
    move_streak: int = 0
    linear_streak: int = 0
    satellite: bool = False
    last_position: Point = (0.0, 0.0)


class TemporalGraphBuilder:
    """Maintain the temporal scene graph and emit debounced events."""

    def __init__(self, config: TemporalConfig | None = None) -> None:
        self.config = config or TemporalConfig()
        self._states: dict[int, _TrackState] = {}
        self._graph = nx.Graph()
        self._last_diff = graph_diff(nx.Graph(), nx.Graph())
        self._clusters: list[list[int]] = []
        self._offsets: dict[int, Point] = {}
        self._offset: Point = (0.0, 0.0)
        self._previous_positions: dict[int, Point] = {}
        self.log: list[Event] = []

    # ------------------------------------------------------------------ views
    @property
    def graph(self) -> nx.Graph:
        """Current scene graph: nodes carry ``x, y, brightness, visible``."""
        return self._graph

    @property
    def last_diff(self) -> GraphDiff:
        return self._last_diff

    @property
    def clusters(self) -> list[list[int]]:
        """Union-find clusters of non-satellite tracks, largest first."""
        return self._clusters

    @property
    def satellites(self) -> frozenset[int]:
        return frozenset(i for i, s in self._states.items() if s.satellite)

    @property
    def camera_offset(self) -> Point:
        """Accumulated camera (ego) motion in pixels since the first frame."""
        return self._offset

    def relative_trajectory(self, track: TrackedStar) -> list[Point]:
        """Track positions with camera motion removed (sky-fixed frame)."""
        out: list[Point] = []
        for (x, y), f in zip(track.trajectory, track.frame_indices):
            ox, oy = self._offsets.get(f, self._offset)
            out.append((x - ox, y - oy))
        return out

    def sky_velocity(self, track: TrackedStar) -> Point:
        """Velocity in px/frame relative to the star field."""
        rel = self.relative_trajectory(track)
        if len(rel) < 2:
            return (0.0, 0.0)
        span = track.frame_indices[-1] - track.frame_indices[0]
        if span <= 0:
            return (0.0, 0.0)
        return ((rel[-1][0] - rel[0][0]) / span, (rel[-1][1] - rel[0][1]) / span)

    # ----------------------------------------------------------------- update
    def _update_camera_offset(self, visible: Sequence[TrackedStar], frame_idx: int) -> None:
        if self.config.compensate_camera_motion:
            shifts = [
                (t.x - self._previous_positions[t.id][0], t.y - self._previous_positions[t.id][1])
                for t in visible
                if t.id in self._previous_positions
                and not self._states.get(t.id, _TrackState()).satellite
            ]
            if shifts:
                dx, dy = np.median(np.asarray(shifts), axis=0)
                self._offset = (self._offset[0] + float(dx), self._offset[1] + float(dy))
        self._offsets[frame_idx] = self._offset
        # Bound memory: forget offsets older than any trajectory we might hold.
        for old in [f for f in self._offsets if f < frame_idx - 1000]:
            del self._offsets[old]
        self._previous_positions = {t.id: (t.x, t.y) for t in visible}

    def update(self, tracked_stars: Sequence[TrackedStar], frame_idx: int) -> list[Event]:
        """Ingest this frame's tracks; return the events emitted at ``frame_idx``."""
        cfg = self.config
        events: list[Event] = []
        visible = [t for t in tracked_stars if t.visible]
        self._update_camera_offset(visible, frame_idx)
        ox, oy = self._offset

        seen_ids = set()
        for track in tracked_stars:
            seen_ids.add(track.id)
            state = self._states.setdefault(track.id, _TrackState())
            state.last_position = (track.x, track.y)

            if not track.visible:
                state.present_streak = 0
                state.move_streak = 0
                if state.announced and track.missed >= cfg.max_disappeared:
                    events.append(self._disappears(frame_idx, track.id, state))
                continue

            state.present_streak += 1
            rel = (track.x - ox, track.y - oy)
            if not state.announced and state.present_streak >= cfg.debounce_frames:
                state.announced = True
                state.anchor = rel
                events.append(
                    Event(frame_idx, EventType.APPEARS,
                          {"id": track.id, "x": track.x, "y": track.y,
                           "brightness": track.brightness})
                )
            if not state.announced:
                continue

            events.extend(self._motion_events(track, state, rel, frame_idx))

        # Tracks the tracker already dropped: report any still-announced ones.
        for track_id in [i for i in self._states if i not in seen_ids]:
            state = self._states[track_id]
            if state.announced:
                events.append(self._disappears(frame_idx, track_id, state))
            del self._states[track_id]

        self._rebuild_graph(tracked_stars)
        self.log.extend(events)
        return events

    def _disappears(self, frame_idx: int, track_id: int, state: _TrackState) -> Event:
        state.announced = False
        state.anchor = None
        x, y = state.last_position
        return Event(frame_idx, EventType.DISAPPEARS, {"id": track_id, "x": x, "y": y})

    def _motion_events(
        self, track: TrackedStar, state: _TrackState, rel: Point, frame_idx: int
    ) -> list[Event]:
        cfg = self.config
        events: list[Event] = []

        if not state.satellite:
            # Recent window only: a satellite moves steadily, frame after frame.
            window = cfg.min_trajectory_points
            rel_traj = self.relative_trajectory(track)[-window:]
            frames = track.frame_indices[-window:]
            vx, vy = self.sky_velocity(track)
            speed = steady_speed(rel_traj, frames)
            linear = is_linear_trajectory(
                rel_traj, tolerance=cfg.linear_tolerance,
                min_points=cfg.min_trajectory_points,
            )
            if linear and speed > cfg.satellite_velocity_threshold:
                state.linear_streak += 1
            else:
                state.linear_streak = 0
            if state.linear_streak >= cfg.debounce_frames:
                state.satellite = True
                events.append(
                    Event(frame_idx, EventType.LINEAR_TRAJECTORY,
                          {"id": track.id, "vx": vx, "vy": vy, "speed": speed,
                           "x": track.x, "y": track.y,
                           "residual": linear_fit_residual(rel_traj)})
                )

        if state.satellite or state.anchor is None:
            return events

        dx, dy = rel[0] - state.anchor[0], rel[1] - state.anchor[1]
        if math.hypot(dx, dy) > cfg.move_threshold:
            state.move_streak += 1
        else:
            state.move_streak = 0
        if state.move_streak >= cfg.debounce_frames:
            events.append(
                Event(frame_idx, EventType.MOVES,
                      {"id": track.id, "dx": dx, "dy": dy, "x": track.x, "y": track.y})
            )
            state.anchor = rel
            state.move_streak = 0
        return events

    def _rebuild_graph(self, tracked_stars: Sequence[TrackedStar]) -> None:
        cfg = self.config
        graph = nx.Graph()
        positions: dict[int, Point] = {}
        for t in tracked_stars:
            state = self._states.get(t.id)
            satellite = bool(state and state.satellite)
            graph.add_node(t.id, x=t.x, y=t.y, brightness=t.brightness,
                           visible=t.visible, satellite=satellite)
            if not satellite:
                positions[t.id] = (t.x, t.y)

        ids = list(positions)
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                d = math.dist(positions[a], positions[b])
                if d < cfg.cluster_distance:
                    graph.add_edge(a, b, distance=d)

        self._last_diff = graph_diff(self._graph, graph)
        self._graph = graph
        self._clusters = [
            [int(i) for i in group]
            for group in cluster_points(positions, cfg.cluster_distance)
        ]
