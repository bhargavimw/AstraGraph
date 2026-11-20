"""Constellation identification by geometric subgraph matching.

Algorithm (:meth:`ConstellationMatcher.match`):

a) Build a graph from the observed cluster: nodes are stars, edges connect
   pairs closer than ``edge_threshold`` pixels (all pairs when unset), each
   edge carrying its length ``d``.
b) Normalise for rotation and scale. Lengths alone are rotation-invariant;
   scale is fixed by hypothesis: the two farthest observed stars ``(a, b)``
   are assumed to be some template pair ``(p, q)``, giving the scale factor
   ``s = d_template(p, q) / d_observed(a, b)``. This works for partial views,
   unlike normalising by the observed extent, which changes when stars are
   hidden.
c) For each constellation and each scale hypothesis, test subgraph
   monomorphism with :class:`networkx.algorithms.isomorphism.GraphMatcher`:
   every observed edge must map to a template edge with
   ``|d_template - s * d_observed| <= tolerance``.
d) Each candidate mapping is verified with a least-squares similarity fit
   (rotation + scale + translation, no reflection). This rejects mirror-image
   matches, which have identical edge lengths but are not the real shape.
e) The best mapping (most matched stars, then lowest fit error) is returned
   with ``confidence = matched_nodes / total_nodes``.

Partial views are supported: a match needs only ``min_matched`` stars (4 by
default), and up to ``max_outliers`` unrelated stars in the cluster are
ignored. Because the fit gives the full template→image transform, hidden
template stars are projected as "ghosts" for the X-Ray overlay.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import networkx as nx
import numpy as np
from networkx.algorithms.isomorphism import GraphMatcher

from astragraph.geometry import (
    FloatArray,
    Similarity,
    fit_similarity,
    pairwise_distances,
    sky_to_plane,
)

Point = tuple[float, float]


class _HasPosition(Protocol):
    id: int
    x: float
    y: float


@dataclass(frozen=True)
class MatcherConfig:
    """Matcher parameters (``reasoning``/``matcher`` blocks of config.yaml)."""

    distance_tolerance: float = 0.05
    fit_tolerance: float = 0.03
    min_cluster_size: int = 4
    max_outliers: int = 2
    max_cluster_size: int = 16
    match_confidence_threshold: float = 0.6
    edge_threshold: float | None = None

    @property
    def min_matched(self) -> int:
        return self.min_cluster_size

    @classmethod
    def from_mapping(cls, *sections: Mapping[str, Any] | None) -> "MatcherConfig":
        merged: dict[str, Any] = {}
        for section in sections:
            merged.update(section or {})
        known = {f: merged[f] for f in cls.__dataclass_fields__ if f in merged}
        return cls(**known)


@dataclass(frozen=True)
class ConstellationTemplate:
    """A constellation's stars projected to image-oriented plane coordinates (degrees)."""

    name: str
    star_names: tuple[str, ...]
    plane: FloatArray
    lines: tuple[tuple[str, str], ...]
    magnitudes: tuple[float, ...]

    @classmethod
    def from_graph(cls, graph: nx.Graph, name: str | None = None) -> "ConstellationTemplate":
        names = tuple(graph.nodes)
        plane = sky_to_plane(
            [graph.nodes[n]["ra"] for n in names], [graph.nodes[n]["dec"] for n in names]
        )
        return cls(
            name=name or str(graph.graph.get("name", "unknown")),
            star_names=names,
            plane=plane,
            lines=tuple((str(a), str(b)) for a, b in graph.edges),
            magnitudes=tuple(float(graph.nodes[n].get("magnitude", 0.0)) for n in names),
        )

    @property
    def size(self) -> int:
        return len(self.star_names)

    @property
    def extent(self) -> float:
        """Largest angular separation between two template stars (degrees)."""
        return float(pairwise_distances(self.plane).max())

    def index(self, star_name: str) -> int:
        return self.star_names.index(star_name)


@dataclass(frozen=True)
class MatchResult:
    """Outcome of matching a star cluster against the constellation database.

    Attributes:
        constellation: Best matching constellation, or ``None``.
        confidence: ``matched_nodes / total_nodes`` of that constellation.
        matched_nodes: Observed stars mapped onto template stars.
        total_nodes: Stars in the constellation template.
        mapping: Observed star ID → template star name.
        transform: Similarity from template plane (degrees) to image pixels.
        fit_error: RMS residual of the fit as a fraction of the template size.
        ghost_positions: Image positions of template stars not observed.
        line_segments: Constellation lines in image coordinates, for drawing.
        outliers: Observed IDs in the cluster that are not part of the match.
    """

    constellation: str | None
    confidence: float = 0.0
    matched_nodes: int = 0
    total_nodes: int = 0
    mapping: Mapping[int, str] = field(default_factory=dict)
    transform: Similarity | None = None
    fit_error: float = math.inf
    ghost_positions: Mapping[str, Point] = field(default_factory=dict)
    line_segments: tuple[tuple[Point, Point], ...] = ()
    outliers: tuple[int, ...] = ()

    @property
    def matched(self) -> bool:
        return self.constellation is not None

    @property
    def degrees_per_pixel(self) -> float | None:
        """Plate scale implied by the match (angular size of one pixel)."""
        return 1.0 / self.transform.scale if self.transform else None

    def is_confident(self, threshold: float) -> bool:
        return self.matched and self.confidence >= threshold


NO_MATCH = MatchResult(constellation=None)


def _positions(star_cluster: Mapping[int, Point] | Iterable[_HasPosition]) -> dict[int, Point]:
    if isinstance(star_cluster, Mapping):
        return {int(k): (float(v[0]), float(v[1])) for k, v in star_cluster.items()}
    return {int(s.id): (float(s.x), float(s.y)) for s in star_cluster}


def _templates(
    constellation_db: Any,
) -> list[ConstellationTemplate]:
    """Accept a ConstellationDB, a name→graph mapping, or templates."""
    if isinstance(constellation_db, Mapping):
        items = constellation_db.items()
    elif hasattr(constellation_db, "list_constellations"):
        items = ((n, constellation_db.get_constellation(n))
                 for n in constellation_db.list_constellations())
    else:
        return [t for t in constellation_db if isinstance(t, ConstellationTemplate)]
    out = []
    for name, value in items:
        out.append(value if isinstance(value, ConstellationTemplate)
                   else ConstellationTemplate.from_graph(value, name))
    return out


def _distance_graph(points: FloatArray, labels: Sequence[Any], threshold: float | None) -> nx.Graph:
    dist = pairwise_distances(points)
    graph = nx.Graph()
    graph.add_nodes_from(labels)
    for i, j in itertools.combinations(range(len(labels)), 2):
        if threshold is None or dist[i, j] < threshold:
            graph.add_edge(labels[i], labels[j], d=float(dist[i, j]))
    return graph


@dataclass(frozen=True)
class _Candidate:
    mapping: dict[int, int]  # observed id -> template index
    transform: Similarity
    fit_error: float


class ConstellationMatcher:
    """Identify constellations from clusters of detected stars."""

    def __init__(self, config: MatcherConfig | None = None) -> None:
        self.config = config or MatcherConfig()
        self._template_cache: dict[int, list[ConstellationTemplate]] = {}

    def templates(self, constellation_db: Any) -> list[ConstellationTemplate]:
        key = id(constellation_db)
        if key not in self._template_cache:
            self._template_cache[key] = _templates(constellation_db)
        return self._template_cache[key]

    def match(
        self,
        star_cluster: Mapping[int, Point] | Iterable[_HasPosition],
        constellation_db: Any,
    ) -> MatchResult:
        """Return the best constellation match for ``star_cluster`` (or ``NO_MATCH``)."""
        points = _positions(star_cluster)
        cfg = self.config
        if len(points) < cfg.min_matched or len(points) > cfg.max_cluster_size:
            return NO_MATCH

        best: tuple[tuple[int, float], ConstellationTemplate, _Candidate] | None = None
        for template in self.templates(constellation_db):
            candidate = self.match_template(points, template)
            if candidate is None:
                continue
            key = (-len(candidate.mapping), candidate.fit_error)
            if best is None or key < best[0]:
                best = (key, template, candidate)

        if best is None:
            return NO_MATCH
        _, template, candidate = best
        return self._result(points, template, candidate)

    # ----------------------------------------------------------- internals
    def match_template(
        self, points: Mapping[int, Point], template: ConstellationTemplate
    ) -> _Candidate | None:
        """Best mapping of ``points`` onto one template, dropping few outliers."""
        cfg = self.config
        ids = sorted(points)
        for drop in range(cfg.max_outliers + 1):
            keep = len(ids) - drop
            if keep < cfg.min_matched:
                break
            if keep > template.size:
                continue
            best: _Candidate | None = None
            for removed in itertools.combinations(ids, drop):
                subset = [i for i in ids if i not in removed]
                candidate = self._match_subset(points, subset, template)
                if candidate and (best is None or candidate.fit_error < best.fit_error):
                    best = candidate
            if best is not None:
                return best
        return None

    def _match_subset(
        self,
        points: Mapping[int, Point],
        subset: Sequence[int],
        template: ConstellationTemplate,
    ) -> _Candidate | None:
        cfg = self.config
        obs = np.array([points[i] for i in subset], dtype=float)
        obs_graph = _distance_graph(obs, list(subset), cfg.edge_threshold)
        if obs_graph.number_of_edges() == 0:
            return None

        tmpl_dist = pairwise_distances(template.plane)
        tmpl_graph = _distance_graph(template.plane, list(range(template.size)), None)
        tolerance = cfg.distance_tolerance * template.extent

        # Anchor pair: the longest observed edge.
        a, b, d_ab = max(
            ((u, v, data["d"]) for u, v, data in obs_graph.edges(data=True)),
            key=lambda e: e[2],
        )
        if d_ab <= 0:
            return None

        best: _Candidate | None = None
        for p, q in itertools.permutations(range(template.size), 2):
            scale = tmpl_dist[p, q] / d_ab
            for node, role in ((a, "A"), (b, "B")):
                obs_graph.nodes[node]["role"] = role
            for node in tmpl_graph.nodes:
                tmpl_graph.nodes[node]["role"] = "A" if node == p else "B" if node == q else None
            for node in obs_graph.nodes:
                obs_graph.nodes[node].setdefault("role", None)

            matcher = GraphMatcher(
                tmpl_graph,
                obs_graph,
                node_match=lambda n1, n2: n1.get("role") == n2.get("role"),
                edge_match=lambda e1, e2, s=scale: abs(e1["d"] - s * e2["d"]) <= tolerance,
            )
            for tmpl_to_obs in matcher.subgraph_monomorphisms_iter():
                mapping = {obs_id: t_idx for t_idx, obs_id in tmpl_to_obs.items()}
                candidate = self._verify(points, mapping, template)
                if candidate and (best is None or candidate.fit_error < best.fit_error):
                    best = candidate
            for node in obs_graph.nodes:
                obs_graph.nodes[node]["role"] = None
        return best

    def _verify(
        self,
        points: Mapping[int, Point],
        mapping: Mapping[int, int],
        template: ConstellationTemplate,
    ) -> _Candidate | None:
        obs_ids = sorted(mapping)
        src = template.plane[[mapping[i] for i in obs_ids]]
        dst = np.array([points[i] for i in obs_ids], dtype=float)
        try:
            transform = fit_similarity(src, dst)
        except ValueError:
            return None
        residual = transform.apply(src) - dst
        rms_px = float(np.sqrt(np.mean(np.sum(residual**2, axis=1))))
        fit_error = rms_px / (transform.scale * template.extent)
        if fit_error > self.config.fit_tolerance:
            return None  # e.g. a mirror image: same lengths, wrong handedness
        return _Candidate(dict(mapping), transform, fit_error)

    def _result(
        self,
        points: Mapping[int, Point],
        template: ConstellationTemplate,
        candidate: _Candidate,
    ) -> MatchResult:
        mapping = {obs: template.star_names[idx] for obs, idx in candidate.mapping.items()}
        projected = candidate.transform.apply(template.plane)
        observed_names = set(mapping.values())
        name_to_obs = {name: obs for obs, name in mapping.items()}

        def position(star: str) -> Point:
            if star in name_to_obs:
                return points[name_to_obs[star]]
            x, y = projected[template.index(star)]
            return (float(x), float(y))

        ghosts = {
            name: position(name) for name in template.star_names if name not in observed_names
        }
        segments = tuple((position(a), position(b)) for a, b in template.lines)
        return MatchResult(
            constellation=template.name,
            confidence=len(mapping) / template.size,
            matched_nodes=len(mapping),
            total_nodes=template.size,
            mapping=mapping,
            transform=candidate.transform,
            fit_error=candidate.fit_error,
            ghost_positions=ghosts,
            line_segments=segments,
            outliers=tuple(sorted(set(points) - set(mapping))),
        )
