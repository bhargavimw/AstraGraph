"""Tests for the AstroAcademy learning module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from astragraph.academy import (
    AstronomyAcademy,
    Quiz,
    check_quiz_answer,
    normalize_edge,
    same_shape,
)
from astragraph.constellation_db import ConstellationDB

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def db() -> ConstellationDB:
    database = ConstellationDB.from_config("config.yaml")
    database.load()
    return database


@pytest.fixture(scope="module")
def academy(db: ConstellationDB) -> AstronomyAcademy:
    return AstronomyAcademy(db)


# ------------------------------------------------------------- data file
def test_info_file_covers_every_constellation(db: ConstellationDB) -> None:
    data = json.loads((ROOT / "data" / "constellation_info.json").read_text())
    entries = data["constellations"]
    assert sorted(entries) == db.list_constellations()
    for name, entry in entries.items():
        sentences = [s for s in entry["mythology"].split(". ") if s.strip()]
        assert 2 <= len(sentences) <= 4, name  # 2-3 sentences of mythology
        assert 3 <= len(entry["key_stars"]) <= 5, name
        for star in entry["key_stars"]:
            assert star["name"] in db[name], (name, star["name"])
            assert len(star["fact"]) > 20
        assert entry["best_season"]
        assert len(entry["fun_fact"]) > 40


# ------------------------------------------------------------------- info
def test_get_constellation_info(academy: AstronomyAcademy) -> None:
    info = academy.get_constellation_info("Orion")
    assert info["best_season"] == "Winter"
    assert "hunter" in info["mythology"]
    names = [s["name"] for s in info["key_stars"]]
    assert names[:2] == ["Betelgeuse", "Rigel"]
    rigel = info["key_stars"][1]
    assert rigel["magnitude"] == pytest.approx(0.13)
    assert 700 < rigel["distance_ly"] < 1000  # ~860 light-years
    assert info["star_count"] == 8 and info["line_count"] == 9


def test_unknown_constellation_raises(academy: AstronomyAcademy) -> None:
    with pytest.raises(KeyError, match="Available"):
        academy.get_constellation_info("Draco")


def test_star_facts_combine_database_catalog_and_text(academy: AstronomyAcademy) -> None:
    vega = academy.get_star_facts("Vega")
    assert vega["constellation"] == "Lyra"
    assert vega["designation"] == "Alpha Lyrae"
    assert vega["distance_ly"] == 25
    assert vega["brightness_rank"] == 5  # matches "fifth-brightest" in the fact text
    assert "photographed" in vega["fact"]
    assert vega["brightness_vs_polaris"] > 5


def test_star_facts_for_catalog_only_star(academy: AstronomyAcademy) -> None:
    sirius = academy.get_star_facts("Sirius")
    assert sirius["brightness_rank"] == 1
    assert sirius["distance_ly"] in (8, 9)  # 8.6 light-years
    assert "constellation" not in sirius  # not one of the 8 database figures
    with pytest.raises(KeyError):
        academy.get_star_facts("Krypton")


# ------------------------------------------------------------------- quiz
def test_generate_quiz_contains_constellation_stars(
    academy: AstronomyAcademy, db: ConstellationDB
) -> None:
    quiz = academy.generate_quiz("Ursa Major", seed=3)
    assert isinstance(quiz, Quiz)
    assert quiz.constellation == "Ursa Major"
    assert {s.name for s in quiz.stars} == set(db["Ursa Major"].nodes)
    assert len(quiz.correct_edges) == db["Ursa Major"].number_of_edges()
    assert quiz.user_edges == set()


def test_quiz_geometry_matches_sky_orientation(academy: AstronomyAcademy) -> None:
    quiz = academy.generate_quiz("Orion")
    betelgeuse, rigel = quiz.star("Betelgeuse"), quiz.star("Rigel")
    assert betelgeuse.y > rigel.y  # Betelgeuse (north) above Rigel
    assert betelgeuse.x < rigel.x  # Betelgeuse (east) on the left


def test_quiz_distractors_are_real_stars_outside_the_figure(
    academy: AstronomyAcademy, db: ConstellationDB
) -> None:
    quiz = academy.generate_quiz("Orion", distractors=3, seed=1)
    extra = [s for s in quiz.stars if s.distractor]
    assert 1 <= len(extra) <= 3
    for star in extra:
        assert star.name not in db["Orion"]
    assert all(not s.distractor for s in quiz.stars if s.name in db["Orion"])


def test_perfect_answer_scores_one(academy: AstronomyAcademy) -> None:
    quiz = academy.generate_quiz("Cassiopeia")
    for a, b in quiz.correct_edges:
        quiz.toggle_edge(b, a)  # direction does not matter
    result = quiz.grade()
    assert result.score == 1.0 and result.perfect and result.same_shape


def test_partial_and_wrong_answers_are_scored(academy: AstronomyAcademy) -> None:
    quiz = academy.generate_quiz("Lyra")  # 7 lines
    correct = sorted(quiz.correct_edges)
    for edge in correct[:4]:
        quiz.toggle_edge(*edge)
    quiz.toggle_edge("Vega", "Sulafat")  # not a Lyra line
    result = quiz.grade()
    assert result.score == pytest.approx(4 / 8)  # 4 right / (7 correct + 1 extra)
    assert len(result.missing) == 3
    assert result.extra == {normalize_edge("Vega", "Sulafat")}
    assert not result.perfect


def test_toggle_edge_removes_existing_line(academy: AstronomyAcademy) -> None:
    quiz = academy.generate_quiz("Lyra")
    assert quiz.toggle_edge("Vega", "Sheliak") is True
    assert quiz.toggle_edge("Sheliak", "Vega") is False
    assert quiz.user_edges == set()
    with pytest.raises(KeyError):
        quiz.toggle_edge("Vega", "Betelgeuse")  # not in this quiz
    with pytest.raises(ValueError):
        quiz.toggle_edge("Vega", "Vega")


def test_check_quiz_answer_edge_cases() -> None:
    correct = [("A", "B"), ("B", "C")]
    assert check_quiz_answer([], correct) == 0.0
    assert check_quiz_answer([("C", "B"), ("B", "A")], correct) == 1.0
    assert check_quiz_answer([("A", "B"), ("A", "C")], correct) == pytest.approx(1 / 3)
    assert check_quiz_answer([], []) == 1.0


def test_same_shape_detects_isomorphic_drawings() -> None:
    correct = [("A", "B"), ("B", "C"), ("C", "D")]  # a path of 4 stars
    relabelled = [("D", "A"), ("A", "C"), ("C", "B")]  # also a 4-path
    star = [("A", "B"), ("A", "C"), ("A", "D")]  # a star shape
    assert same_shape(relabelled, correct)
    assert check_quiz_answer(relabelled, correct) < 1.0
    assert not same_shape(star, correct)
