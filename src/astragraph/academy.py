"""AstroAcademy: constellation facts and "connect the dots" quizzes.

A quiz shows a constellation's stars at their true relative positions (plus
optional distractor stars from the catalog) and asks the learner to draw the
traditional stick figure. Answers are graphs, so grading is graph theory:

* :func:`check_quiz_answer` returns the Jaccard similarity of the edge sets,
  ``|user ∩ correct| / |user ∪ correct|`` — missing lines and extra lines
  both cost points; a perfect drawing scores 1.0.
* :func:`same_shape` checks graph isomorphism: whether the learner drew the
  right *shape* even if they connected different stars (a useful hint).
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np

from astragraph.constellation_db import ConstellationDB
from astragraph.geometry import gnomonic_project, mean_sky_position

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INFO_PATH = ROOT / "data" / "constellation_info.json"

Edge = tuple[str, str]


def normalize_edge(a: str, b: str) -> Edge:
    """Undirected edge as a sorted pair, so (A, B) and (B, A) are equal."""
    if a == b:
        raise ValueError(f"An edge needs two different stars, got {a!r} twice")
    return (a, b) if a < b else (b, a)


def normalize_edges(edges: Iterable[Iterable[str]]) -> frozenset[Edge]:
    out = set()
    for edge in edges:
        a, b = tuple(edge)
        out.add(normalize_edge(a, b))
    return frozenset(out)


def check_quiz_answer(
    user_edges: Iterable[Iterable[str]], correct_edges: Iterable[Iterable[str]]
) -> float:
    """Accuracy in ``[0, 1]``: Jaccard similarity of the two edge sets."""
    user = normalize_edges(user_edges)
    correct = normalize_edges(correct_edges)
    union = user | correct
    if not union:
        return 1.0
    return len(user & correct) / len(union)


def same_shape(
    user_edges: Iterable[Iterable[str]], correct_edges: Iterable[Iterable[str]]
) -> bool:
    """Whether the drawn figure is isomorphic to the correct one (labels ignored)."""
    user = nx.Graph(list(normalize_edges(user_edges)))
    correct = nx.Graph(list(normalize_edges(correct_edges)))
    return nx.is_isomorphic(user, correct)


@dataclass(frozen=True)
class QuizStar:
    """A star shown in a quiz, in plot coordinates (x right, y up, east left)."""

    name: str
    x: float
    y: float
    magnitude: float
    distractor: bool = False


@dataclass(frozen=True)
class QuizResult:
    score: float
    correct: frozenset[Edge]
    missing: frozenset[Edge]
    extra: frozenset[Edge]
    same_shape: bool

    @property
    def perfect(self) -> bool:
        return not self.missing and not self.extra


@dataclass
class Quiz:
    """A connect-the-dots puzzle. ``user_edges`` collects the learner's lines."""

    constellation: str
    stars: tuple[QuizStar, ...]
    correct_edges: frozenset[Edge]
    user_edges: set[Edge] = field(default_factory=set)

    def star(self, name: str) -> QuizStar:
        for star in self.stars:
            if star.name == name:
                return star
        raise KeyError(f"No star {name!r} in this quiz")

    def toggle_edge(self, a: str, b: str) -> bool:
        """Add the line A–B, or remove it if present. Returns True if added."""
        self.star(a), self.star(b)  # validate names
        edge = normalize_edge(a, b)
        if edge in self.user_edges:
            self.user_edges.remove(edge)
            return False
        self.user_edges.add(edge)
        return True

    def grade(self) -> QuizResult:
        user = frozenset(self.user_edges)
        return QuizResult(
            score=check_quiz_answer(user, self.correct_edges),
            correct=user & self.correct_edges,
            missing=self.correct_edges - user,
            extra=user - self.correct_edges,
            same_shape=same_shape(user, self.correct_edges) if user else False,
        )


def _load_catalog_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(line for line in handle if not line.startswith("#")))


class AstronomyAcademy:
    """Facts, star profiles and quizzes for the constellation database."""

    def __init__(
        self,
        db: ConstellationDB,
        info_path: str | Path = DEFAULT_INFO_PATH,
        catalog_path: str | Path | None = None,
    ) -> None:
        self.db = db
        payload = json.loads(Path(info_path).read_text(encoding="utf-8"))
        info = payload.get("constellations")
        if not isinstance(info, Mapping):
            raise ValueError(f"{info_path} must contain a 'constellations' object")
        self._info: dict[str, dict[str, Any]] = dict(info)
        self.metadata: dict[str, Any] = dict(payload.get("metadata", {}))
        catalog = Path(catalog_path) if catalog_path else ROOT / "data" / "bright_stars.csv"
        self._catalog = _load_catalog_rows(catalog) if catalog.exists() else []
        self._catalog_by_name = {r["name"].lower(): r for r in self._catalog}

    # ----------------------------------------------------------- info
    def list_constellations(self) -> list[str]:
        return sorted(set(self._info) & set(self.db.list_constellations()))

    def get_constellation_info(self, name: str) -> dict[str, Any]:
        """Mythology, key stars (with facts), best season and a fun fact."""
        if name not in self._info:
            known = ", ".join(self.list_constellations())
            raise KeyError(f"No Academy entry for {name!r}. Available: {known}")
        entry = self._info[name]
        graph = self.db.get_constellation(name)
        key_stars = []
        for star in entry.get("key_stars", []):
            details = self.get_star_facts(star["name"])
            key_stars.append({**details, "fact": star["fact"]})
        return {
            "name": name,
            "abbreviation": graph.graph.get("abbreviation", ""),
            "mythology": entry["mythology"],
            "key_stars": key_stars,
            "best_season": entry["best_season"],
            "fun_fact": entry["fun_fact"],
            "star_count": graph.number_of_nodes(),
            "line_count": graph.number_of_edges(),
        }

    def get_star_facts(self, star_name: str) -> dict[str, Any]:
        """Profile of a star: constellation, designation, brightness, distance, fact."""
        found: tuple[str, dict[str, Any]] | None = None
        for constellation in self.db.list_constellations():
            graph = self.db.get_constellation(constellation)
            if star_name in graph:
                found = (constellation, dict(graph.nodes[star_name]))
                break
        row = self._catalog_by_name.get(star_name.lower())
        if found is None and row is None:
            raise KeyError(f"Unknown star {star_name!r}")

        facts: dict[str, Any] = {"name": star_name}
        if found:
            constellation, attrs = found
            facts.update(
                constellation=constellation,
                designation=attrs.get("designation", ""),
                magnitude=float(attrs["magnitude"]),
                ra=float(attrs["ra"]),
                dec=float(attrs["dec"]),
            )
            for star in self._info.get(constellation, {}).get("key_stars", []):
                if star["name"] == star_name:
                    facts["fact"] = star["fact"]
        if row:
            parallax = float(row["parallax_mas"])
            facts.setdefault("magnitude", float(row["magnitude"]))
            facts.setdefault("ra", float(row["ra_hours"]) * 15.0)
            facts.setdefault("dec", float(row["dec_degrees"]))
            facts["catalog_constellation"] = row["constellation"]
            if parallax > 0:
                facts["distance_ly"] = round(3261.56 / parallax)
            facts["brightness_rank"] = self._catalog.index(row) + 1
        mag = facts.get("magnitude")
        if mag is not None:
            facts["brightness_vs_polaris"] = round(10 ** (-0.4 * (mag - 1.98)), 2)
        return facts

    # ----------------------------------------------------------- quiz
    def generate_quiz(
        self, constellation_name: str, *, distractors: int = 0, seed: int | None = None
    ) -> Quiz:
        """Connect-the-dots puzzle for a constellation.

        Stars are placed by tangent-plane projection (east to the left, north
        up, matching the real sky). ``distractors`` adds up to that many real
        catalog stars from the surrounding sky that are *not* in the figure
        (fewer if the catalog has no other bright stars in that area).
        """
        graph = self.db.get_constellation(constellation_name)
        names = list(graph.nodes)
        ras = [graph.nodes[n]["ra"] for n in names]
        decs = [graph.nodes[n]["dec"] for n in names]
        ra0, dec0 = mean_sky_position(ras, decs)
        xi, eta = gnomonic_project(ras, decs, ra0, dec0)
        stars = [
            QuizStar(n, float(-x), float(y), float(graph.nodes[n]["magnitude"]))
            for n, x, y in zip(names, xi, eta)
        ]
        if distractors > 0:
            stars += self._distractors(stars, ra0, dec0, distractors, seed)
        rng = random.Random(seed)
        rng.shuffle(stars)  # order must not give the answer away
        return Quiz(
            constellation=constellation_name,
            stars=tuple(stars),
            correct_edges=normalize_edges(graph.edges),
        )

    def _distractors(
        self, stars: list[QuizStar], ra0: float, dec0: float, count: int, seed: int | None
    ) -> list[QuizStar]:
        xs = [s.x for s in stars]
        ys = [s.y for s in stars]
        pad = 0.15 * max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
        box = (min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad)
        taken = {s.name.lower() for s in stars}
        candidates = []
        for row in self._catalog:
            if row["name"].lower() in taken:
                continue
            ra, dec = float(row["ra_hours"]) * 15.0, float(row["dec_degrees"])
            if math.degrees(math.acos(max(-1.0, min(1.0,
                math.sin(math.radians(dec)) * math.sin(math.radians(dec0))
                + math.cos(math.radians(dec)) * math.cos(math.radians(dec0))
                * math.cos(math.radians(ra - ra0)))))) > 60:
                continue
            xi, eta = gnomonic_project([ra], [dec], ra0, dec0)
            x, y = float(-xi[0]), float(eta[0])
            if not (box[0] <= x <= box[1] and box[2] <= y <= box[3]):
                continue
            if min(math.hypot(x - s.x, y - s.y) for s in stars) < 0.5:
                continue  # same star under another name, or too close to tell apart
            candidates.append(QuizStar(row["name"], x, y, float(row["magnitude"]), True))
        candidates.sort(key=lambda s: s.magnitude)
        pool = candidates[: max(count * 3, count)]
        rng = np.random.default_rng(seed)
        picks = rng.choice(len(pool), size=min(count, len(pool)), replace=False) if pool else []
        return [pool[int(i)] for i in picks]
