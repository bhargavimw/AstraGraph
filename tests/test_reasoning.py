"""Tests for the rule engine, constellation matcher, pan planner and pipeline."""

from __future__ import annotations

import math

import numpy as np
import pytest

from astragraph.constellation_db import ConstellationDB
from astragraph.geometry import Similarity
from astragraph.matcher import ConstellationMatcher, MatcherConfig
from astragraph.pipeline import PipelineConfig, SkyPipeline, compass_heading
from astragraph.reason import (
    Rule,
    SkyReasoner,
    default_rules,
    reason,
)
from astragraph.spatial_plan import Occlusion, describe_pan, find_clear_view
from astragraph.synthetic import (
    SyntheticStar,
    constellation_layout,
    constellation_stars,
    render_star_field,
)


@pytest.fixture(scope="module")
def db() -> ConstellationDB:
    database = ConstellationDB.from_config("config.yaml")
    database.load()
    return database


@pytest.fixture(scope="module")
def matcher() -> ConstellationMatcher:
    return ConstellationMatcher(MatcherConfig())


def layout_points(
    db: ConstellationDB, name: str, transform: Similarity
) -> dict[int, tuple[float, float]]:
    layout = constellation_layout(db[name], transform)
    return {i: pos for i, pos in enumerate(layout.values())}


# ---------------------------------------------------------------- rule engine
SCENE = [
    ("cluster_size", "cluster:0", 5),
    ("matches_pattern", "cluster:0", "Ursa Major"),
    ("match_confidence", "cluster:0", 5 / 7),
    ("member_of", "track:1", "cluster:0"),
    ("cluster_size", "cluster:1", 3),
    ("matches_pattern", "cluster:1", "Lyra"),
    ("trajectory_linear", "track:9", True),
    ("velocity", "track:9", 4.2),
    ("trajectory_linear", "track:8", True),
    ("velocity", "track:8", 0.2),
    ("brightness", "track:4", 250.0),
    ("not_in_catalog", "track:4", True),
    ("brightness", "track:5", 200.0),
    ("not_in_catalog", "track:5", True),
]


def test_rule_engine_reaches_fixpoint_and_is_idempotent() -> None:
    rules = default_rules()
    first = reason(SCENE, rules)
    assert first, "expected some conclusions"
    everything = SCENE + [c.fact for c in first]
    assert reason(everything, rules) == []  # nothing new: a fixpoint
    assert reason(SCENE, rules) == first  # deterministic


def test_rule_engine_terminates_on_recursive_rules() -> None:
    # Transitive closure of a cyclic relation must still terminate.
    rules = [
        Rule("base", (("orbits", "?a", "?b"),), ("bound_to", "?a", "?b")),
        Rule(
            "trans",
            (("bound_to", "?a", "?b"), ("bound_to", "?b", "?c")),
            ("bound_to", "?a", "?c"),
        ),
    ]
    facts = [("orbits", "Moon", "Earth"), ("orbits", "Earth", "Sun"), ("orbits", "Sun", "Moon")]
    derived = {c.fact for c in reason(facts, rules)}
    assert ("bound_to", "Moon", "Sun") in derived
    assert len(derived) == 9  # every ordered pair over the 3-cycle, incl. self-loops


def test_forward_chaining_derives_multi_step_conclusions() -> None:
    conclusions = SkyReasoner().reason(SCENE)
    facts = {c.fact for c in conclusions}
    assert ("identified_as", "cluster:0", "Ursa Major") in facts
    assert ("full_view", "cluster:0", "Ursa Major") in facts
    assert ("in_constellation", "track:1", "Ursa Major") in facts
    chained = next(c for c in conclusions if c.fact[0] == "in_constellation")
    assert chained.iteration == 2
    assert ("identified_as", "cluster:0", "Ursa Major") in chained.support


def test_small_cluster_is_not_identified() -> None:
    facts = {c.fact for c in SkyReasoner().reason(SCENE)}
    assert not any(f[0] == "identified_as" and f[1] == "cluster:1" for f in facts)


def test_partial_view_renders_ghosts() -> None:
    facts = [
        ("cluster_size", "cluster:0", 4),
        ("matches_pattern", "cluster:0", "Ursa Major"),
        ("match_confidence", "cluster:0", 4 / 7),
        ("hidden_star", "cluster:0", "Alkaid"),
    ]
    derived = {c.fact for c in SkyReasoner().reason(facts)}
    assert ("partial_view", "cluster:0", "Ursa Major") in derived
    assert ("render_ghost", "Alkaid", "Ursa Major") in derived


def test_satellite_correctly_flagged() -> None:
    derived = SkyReasoner.query(SkyReasoner().reason(SCENE), "is_satellite")
    assert derived == [("is_satellite", "track:9", True)]


def test_anomaly_detected() -> None:
    derived = SkyReasoner.query(SkyReasoner().reason(SCENE), "is_anomaly")
    assert derived == [("is_anomaly", "track:4", True)]


def test_rules_must_be_range_restricted() -> None:
    with pytest.raises(ValueError, match="range-restricted"):
        Rule("bad", (("p", "?x", "?y"),), ("q", "?x", "?z"))
    with pytest.raises(ValueError, match="unbound"):
        Rule("bad_test", (("p", "?x", "?y"), ("gt", "?z", 1)), ("q", "?x", "?y"))


# ------------------------------------------------------------------- matcher
@pytest.mark.parametrize(
    "name",
    ["Orion", "Ursa Major", "Ursa Minor", "Cassiopeia", "Leo", "Scorpius", "Cygnus", "Lyra"],
)
def test_every_constellation_identified_from_full_view(
    db: ConstellationDB, matcher: ConstellationMatcher, name: str
) -> None:
    points = layout_points(db, name, Similarity(22.0, 0.4, (400.0, 300.0)))
    result = matcher.match(points, db)
    assert result.constellation == name
    assert result.confidence == 1.0
    assert result.ghost_positions == {}


def test_constellation_identified_from_partial_view(
    db: ConstellationDB, matcher: ConstellationMatcher
) -> None:
    transform = Similarity(25.0, -0.8, (320.0, 240.0))
    layout = constellation_layout(db["Ursa Major"], transform)
    visible = ["Dubhe", "Merak", "Phecda", "Megrez"]  # the bowl; handle hidden
    points = {i: layout[name] for i, name in enumerate(visible)}

    result = matcher.match(points, db)
    assert result.constellation == "Ursa Major"
    assert result.matched_nodes == 4
    assert result.confidence == pytest.approx(4 / 7)
    assert set(result.ghost_positions) == {"Alioth", "Mizar", "Alkaid"}
    for star, (gx, gy) in result.ghost_positions.items():  # X-Ray ghosts
        tx, ty = layout[star]
        assert math.hypot(gx - tx, gy - ty) < 1.0


@pytest.mark.parametrize("rotation", [0.0, 1.2, 2.9, -2.0])
@pytest.mark.parametrize("scale", [8.0, 20.0, 45.0])
def test_isomorphism_is_rotation_and_scale_invariant(
    db: ConstellationDB, matcher: ConstellationMatcher, rotation: float, scale: float
) -> None:
    points = layout_points(db, "Orion", Similarity(scale, rotation, (500.0, 400.0)))
    result = matcher.match(points, db)
    assert result.constellation == "Orion"
    assert result.transform is not None
    assert result.transform.scale == pytest.approx(scale, rel=1e-6)
    expected = (rotation + math.pi) % (2 * math.pi) - math.pi
    assert result.transform.rotation == pytest.approx(expected, abs=1e-6)


def test_mirror_image_is_not_matched(
    db: ConstellationDB, matcher: ConstellationMatcher
) -> None:
    points = layout_points(db, "Cassiopeia", Similarity(25.0, 0.3, (300.0, 300.0)))
    mirrored = {i: (600.0 - x, y) for i, (x, y) in points.items()}
    assert matcher.match(points, db).constellation == "Cassiopeia"
    assert matcher.match(mirrored, db).constellation is None


def test_outlier_stars_are_ignored_and_reported(
    db: ConstellationDB, matcher: ConstellationMatcher
) -> None:
    points = layout_points(db, "Leo", Similarity(25.0, 0.9, (320.0, 240.0)))
    points[98] = (600.0, 400.0)
    points[99] = (10.0, 10.0)
    result = matcher.match(points, db)
    assert result.constellation == "Leo"
    assert result.outliers == (98, 99)


def test_random_points_do_not_match(
    db: ConstellationDB, matcher: ConstellationMatcher
) -> None:
    rng = np.random.default_rng(7)
    false_matches = 0
    for _ in range(20):
        points = {i: tuple(rng.uniform(0, 600, 2)) for i in range(7)}
        false_matches += matcher.match(points, db).matched
    assert false_matches <= 1


def test_too_few_stars_returns_no_match(
    db: ConstellationDB, matcher: ConstellationMatcher
) -> None:
    points = layout_points(db, "Lyra", Similarity(25.0, 0.0, (300.0, 300.0)))
    assert not matcher.match(dict(list(points.items())[:3]), db).matched


# --------------------------------------------------------------- pan planner
def test_clear_target_needs_no_pan() -> None:
    assert find_clear_view([Occlusion(0, 30, 0, 20)], (180.0, 45.0)) == (0.0, 0.0)


def test_pan_moves_off_a_building() -> None:
    building = Occlusion(170, 200, 0, 40)
    offset = find_clear_view([building], (185.0, 30.0))
    assert offset is not None
    d_az, d_alt = offset
    assert not building.contains(185.0 + d_az, 30.0 + d_alt)
    assert math.hypot(d_az, d_alt) <= 25.0
    assert describe_pan(offset).startswith("To avoid the obstruction")


def test_pan_wraps_around_north() -> None:
    tree = Occlusion(350, 20, 0, 60)  # spans azimuth 0
    offset = find_clear_view([tree], (5.0, 20.0), fov=60.0)
    assert offset is not None
    az = (5.0 + offset[0]) % 360.0
    assert not tree.contains(az, 20.0 + offset[1])
    assert -180.0 <= offset[0] < 180.0


def test_fully_blocked_sky_returns_none() -> None:
    assert find_clear_view([Occlusion(0, 360, 0, 90)], (90.0, 45.0)) is None


# ------------------------------------------------------------------ pipeline
def test_compass_heading() -> None:
    assert compass_heading(0.0, 1.0) == "N"
    assert compass_heading(1.0, 1.0) == "NE"
    assert compass_heading(-1.0, 0.0) == "W"


def test_pipeline_identifies_constellation_and_satellite(db: ConstellationDB) -> None:
    config = PipelineConfig.from_file("config.yaml")
    pipeline = SkyPipeline(db, config)
    transform = Similarity(28.0, 0.25, (480.0, 360.0))
    base = constellation_stars(db["Orion"], transform)
    planet = SyntheticStar(560.0, 300.0, 252.0, 2.0)  # bright, not in catalog

    report = None
    for k in range(25):
        satellite = SyntheticStar(120.0 + 6.0 * k, 650.0 - 4.0 * k, 235.0, 1.4)
        frame = render_star_field(base + [planet, satellite], 960, 720, noise_std=3.0, seed=k)
        report = pipeline.process(frame, k)

    assert report is not None
    names = [m.constellation for m in report.constellations]
    assert names == ["Orion"]
    assert report.constellations[0].confidence == 1.0
    assert len(report.satellites) == 1
    sat = report.satellites[0]
    assert sat.degrees_per_second == pytest.approx(
        math.hypot(6.0, 4.0) / 28.0 * config.fps, rel=0.05
    )
    assert sat.heading is not None
    assert len(report.anomalies) == 1
    planet_track = next(t for t in report.tracks if t.id == report.anomalies[0])
    assert planet_track.x == pytest.approx(560.0, abs=1.0)
