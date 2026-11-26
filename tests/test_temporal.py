"""Tests for tracking, union-find clustering and temporal event extraction."""

from __future__ import annotations

import math

import pytest

from astragraph.detect import StarDetection
from astragraph.temporal import (
    Event,
    EventType,
    TemporalConfig,
    TemporalGraphBuilder,
    UnionFind,
    cluster_points,
    is_linear_trajectory,
    linear_fit_residual,
)
from astragraph.track import StarTracker, TrackerConfig, associate


def dets(points: list[tuple[float, float]], brightness: float = 220.0) -> list[StarDetection]:
    return [StarDetection(i, x, y, brightness, 9.0) for i, (x, y) in enumerate(points)]


def run(
    frames: list[list[tuple[float, float]]],
    *,
    tracker: StarTracker | None = None,
    config: TemporalConfig | None = None,
) -> tuple[TemporalGraphBuilder, list[Event]]:
    tracker = tracker or StarTracker(TrackerConfig(max_distance=15, max_disappeared=5))
    builder = TemporalGraphBuilder(config or TemporalConfig())
    events: list[Event] = []
    for idx, points in enumerate(frames):
        tracks = tracker.track(None, dets(points), idx)
        events.extend(builder.update(tracks, idx))
    return builder, events


def of_type(events: list[Event], kind: EventType) -> list[Event]:
    return [e for e in events if e.type == kind]


# --------------------------------------------------------------- union-find
def test_union_find_merges_and_compresses() -> None:
    uf = UnionFind(range(6))
    assert uf.union(0, 1)
    assert uf.union(1, 2)
    assert not uf.union(0, 2)  # already joined
    assert uf.union(4, 5)
    assert uf.connected(0, 2)
    assert not uf.connected(2, 4)
    assert uf.groups() == [[0, 1, 2], [4, 5], [3]]


def test_union_find_relation_is_an_equivalence() -> None:
    uf = UnionFind("abcde")
    uf.union("a", "b")
    uf.union("c", "b")
    for x in "abcde":
        assert uf.connected(x, x)  # reflexive
    assert uf.connected("a", "c") and uf.connected("c", "a")  # symmetric
    assert uf.connected("a", "b") and uf.connected("b", "c")
    assert uf.connected("a", "c")  # transitive


def test_cluster_points_groups_nearby_stars() -> None:
    points = {
        1: (0.0, 0.0), 2: (8.0, 0.0), 3: (16.0, 0.0),  # chain: 1~2~3
        4: (100.0, 100.0), 5: (105.0, 100.0),
        6: (300.0, 0.0),
    }
    clusters = cluster_points(points, threshold=10.0)
    assert clusters == [[1, 2, 3], [4, 5], [6]]


def test_cluster_threshold_is_strict() -> None:
    assert cluster_points({1: (0, 0), 2: (10, 0)}, threshold=10.0) == [[1], [2]]


# ------------------------------------------------------------------ tracker
def test_associate_prefers_closest_pairs() -> None:
    pairs = associate([(0, 0), (10, 0)], [(9, 0), (1, 0), (50, 50)], max_distance=5)
    assert pairs == [(0, 1), (1, 0)]


def test_tracker_keeps_stable_ids_with_jitter() -> None:
    tracker = StarTracker()
    base = [(50.0, 50.0), (120.0, 80.0), (200.0, 40.0)]
    first = tracker.track(None, dets(base), 0)
    ids = {(round(t.x), round(t.y)): t.id for t in first}
    for k in range(1, 6):
        jitter = [(x + 0.8 * math.sin(k), y - 0.6 * math.cos(k)) for x, y in base]
        tracks = tracker.track(None, dets(list(reversed(jitter))), k)
        assert len(tracks) == 3
        for t in tracks:
            assert ids[(round(t.trajectory[0][0]), round(t.trajectory[0][1]))] == t.id
            assert t.frame_count == k + 1
            assert len(t.trajectory) == k + 1


def test_tracker_follows_accelerating_object_with_velocity_prediction() -> None:
    # Speed ramps 4 -> 13 px/frame, beyond max_distance=6, but each step only
    # deviates 1 px from the constant-velocity prediction.
    tracker = StarTracker(TrackerConfig(max_distance=6))
    x = 10.0
    for k in range(10):
        tracks = tracker.track(None, dets([(x, 50.0)]), k)
        x += 4.0 + k
    assert [t.id for t in tracks] == [0]
    assert tracks[0].frame_count == 10


def test_predicted_position_extrapolates_velocity() -> None:
    tracker = StarTracker()
    tracker.track(None, dets([(10.0, 20.0)]), 0)
    (track,) = tracker.track(None, dets([(13.0, 24.0)]), 1)
    assert track.predicted_position(3) == pytest.approx((19.0, 32.0))
    assert track.velocity() == pytest.approx((3.0, 4.0))


def test_tracker_keeps_id_through_short_occlusion() -> None:
    tracker = StarTracker(TrackerConfig(max_disappeared=3))
    tracker.track(None, dets([(50, 50)]), 0)
    for k in (1, 2):
        tracks = tracker.track(None, [], k)
        assert tracks[0].missed == k
    tracks = tracker.track(None, dets([(50.5, 50)]), 3)
    assert [t.id for t in tracks] == [0] and tracks[0].visible


def test_tracker_drops_track_after_grace_period() -> None:
    tracker = StarTracker(TrackerConfig(max_disappeared=2))
    tracker.track(None, dets([(50, 50)]), 0)
    tracker.track(None, [], 1)
    tracker.track(None, [], 2)
    assert tracker.track(None, [], 3) == []


# ------------------------------------------------------------------- events
def test_appears_logged_after_debounce() -> None:
    frames = [[(50, 50)]] * 5
    builder, events = run(frames, config=TemporalConfig(debounce_frames=3))
    appears = of_type(events, EventType.APPEARS)
    assert len(appears) == 1
    assert appears[0].t == 2  # third consecutive frame
    assert appears[0].args["id"] == 0
    assert builder.log == events


def test_disappears_logged_after_grace_period() -> None:
    frames = [[(50, 50), (150, 60)]] * 4 + [[(150, 60)]] * 8
    _, events = run(frames, config=TemporalConfig(max_disappeared=5, debounce_frames=3))
    gone = of_type(events, EventType.DISAPPEARS)
    assert len(gone) == 1
    assert gone[0].args["id"] == 0
    assert gone[0].t == 3 + 5  # last seen at frame 3, missing for 5 frames
    assert gone[0].args["x"] == pytest.approx(50)


def test_short_occlusion_does_not_emit_disappears() -> None:
    frames = [[(50, 50)]] * 4 + [[]] * 2 + [[(50, 50)]] * 4
    _, events = run(frames)
    assert of_type(events, EventType.DISAPPEARS) == []
    assert len(of_type(events, EventType.APPEARS)) == 1


def test_debounce_prevents_flickering_events() -> None:
    # A noisy source visible every other frame never becomes a stable star.
    frames = [[(50, 50), (120, 120)] if k % 2 == 0 else [(50, 50)] for k in range(20)]
    _, events = run(frames, config=TemporalConfig(debounce_frames=3, max_disappeared=5))
    flicker = [e for e in events if e.args.get("id") == 1]
    assert flicker == []
    assert [e.args["id"] for e in of_type(events, EventType.APPEARS)] == [0]


def test_moves_event_for_drifting_star_only() -> None:
    frames = [[(50.0, 50.0), (150.0 + (0.0 if k < 5 else 10.0), 50.0), (250.0, 90.0)]
              for k in range(10)]
    _, events = run(frames, config=TemporalConfig(move_threshold=5, debounce_frames=3))
    moves = of_type(events, EventType.MOVES)
    assert len(moves) == 1
    assert moves[0].args["id"] == 1
    assert moves[0].args["dx"] == pytest.approx(10, abs=1.0)


# --------------------------------------------------------- linear motion
def test_linear_fit_residual() -> None:
    line = [(float(k), 2.0 * k + 1.0) for k in range(10)]
    assert linear_fit_residual(line) == pytest.approx(0.0, abs=1e-9)
    zigzag = [(float(k), 3.0 * (k % 2)) for k in range(10)]
    assert linear_fit_residual(zigzag) > 1.0
    assert is_linear_trajectory(line, tolerance=0.5, min_points=6)
    assert not is_linear_trajectory(line[:4], tolerance=0.5, min_points=6)


def test_fast_linear_object_flagged_as_satellite() -> None:
    stars = [(40.0, 40.0), (200.0, 60.0), (120.0, 200.0)]
    frames = [stars + [(20.0 + 3.0 * k, 150.0 - 2.0 * k)] for k in range(20)]
    builder, events = run(frames)
    sats = of_type(events, EventType.LINEAR_TRAJECTORY)
    assert len(sats) == 1  # flagged exactly once
    assert sats[0].args["id"] == 3
    assert sats[0].args["vx"] == pytest.approx(3.0, abs=0.1)
    assert sats[0].args["vy"] == pytest.approx(-2.0, abs=0.1)
    assert builder.satellites == {3}
    # Satellites are excluded from the star clusters.
    assert all(3 not in cluster for cluster in builder.clusters)


def test_camera_pan_is_not_mistaken_for_satellites() -> None:
    stars = [(40.0, 40.0), (200.0, 60.0), (120.0, 200.0), (300.0, 150.0)]
    frames = [[(x + 2.5 * k, y + 1.0 * k) for x, y in stars] for k in range(20)]
    builder, events = run(frames)
    assert of_type(events, EventType.LINEAR_TRAJECTORY) == []
    assert of_type(events, EventType.MOVES) == []
    assert builder.camera_offset == pytest.approx((2.5 * 19, 1.0 * 19), abs=1e-6)


def test_single_jump_is_not_a_satellite() -> None:
    frames = [[(50.0, 50.0), (150.0 + (0.0 if k < 5 else 10.0), 50.0), (250.0, 90.0)]
              for k in range(15)]
    _, events = run(frames)
    assert of_type(events, EventType.LINEAR_TRAJECTORY) == []


def test_slow_object_is_not_a_satellite() -> None:
    stars = [(40.0, 40.0), (200.0, 60.0), (120.0, 200.0)]
    frames = [stars + [(100.0 + 0.3 * k, 100.0)] for k in range(20)]
    _, events = run(frames, config=TemporalConfig(satellite_velocity_threshold=1.0))
    assert of_type(events, EventType.LINEAR_TRAJECTORY) == []


def test_graph_diff_tracks_new_nodes_and_edges() -> None:
    builder = TemporalGraphBuilder(TemporalConfig(cluster_distance=50))
    tracker = StarTracker()
    builder.update(tracker.track(None, dets([(0, 0)]), 0), 0)
    builder.update(tracker.track(None, dets([(0, 0), (30, 0)]), 1), 1)
    diff = builder.last_diff
    assert diff.added_nodes == {1}
    assert diff.added_edges == {frozenset({0, 1})}
    assert builder.clusters == [[0, 1]]
