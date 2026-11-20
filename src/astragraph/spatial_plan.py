"""Camera guidance: which way to pan to get a clear view of a target.

The sky above the horizon is divided into cells of ``grid_step`` degrees in
azimuth and altitude. Cells are nodes of a visibility graph; neighbouring
cells (8-connectivity, wrapping around north) are joined by edges weighted
with their great-circle separation, so distances shrink correctly near the
zenith. A cell is *occluded* when its centre lies inside any occlusion box
(a building, a tree, the Moon's glare).

:func:`find_clear_view` runs Dijkstra from the target's cell and returns the
offset to the nearest clear cell from which the target is still inside the
camera's field of view. Panning across an obstruction costs nothing extra —
it is only where the camera finally points that must be clear.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import networkx as nx

Cell = tuple[int, int]


@dataclass(frozen=True)
class Occlusion:
    """An azimuth/altitude box in degrees. ``az_min > az_max`` wraps through north."""

    az_min: float
    az_max: float
    alt_min: float
    alt_max: float

    def contains(self, az: float, alt: float) -> bool:
        if not self.alt_min <= alt <= self.alt_max:
            return False
        az, lo, hi = az % 360.0, self.az_min % 360.0, self.az_max % 360.0
        return lo <= az <= hi if lo <= hi else az >= lo or az <= hi


def angular_separation(az1: float, alt1: float, az2: float, alt2: float) -> float:
    """Great-circle distance in degrees between two horizontal positions."""
    a1, h1, a2, h2 = map(math.radians, (az1, alt1, az2, alt2))
    cos_d = math.sin(h1) * math.sin(h2) + math.cos(h1) * math.cos(h2) * math.cos(a1 - a2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_d))))


def wrap_azimuth_offset(delta: float) -> float:
    """Map an azimuth difference to ``[-180, 180)`` (negative = pan left/west of north)."""
    return (delta + 180.0) % 360.0 - 180.0


def _as_occlusions(
    occlusions: Iterable[Occlusion | Sequence[float]],
) -> list[Occlusion]:
    return [o if isinstance(o, Occlusion) else Occlusion(*o) for o in occlusions]


def build_visibility_graph(
    occlusions: Iterable[Occlusion | Sequence[float]],
    grid_step: float = 5.0,
) -> nx.Graph:
    """Grid graph of sky cells with ``az``, ``alt`` and ``occluded`` attributes."""
    boxes = _as_occlusions(occlusions)
    n_az = int(round(360.0 / grid_step))
    n_alt = int(math.ceil(90.0 / grid_step))
    graph = nx.Graph()
    for i in range(n_az):
        for j in range(n_alt):
            az = (i + 0.5) * grid_step
            alt = min((j + 0.5) * grid_step, 90.0)
            graph.add_node(
                (i, j), az=az, alt=alt, occluded=any(b.contains(az, alt) for b in boxes)
            )
    for i in range(n_az):
        for j in range(n_alt):
            for di, dj in ((1, 0), (0, 1), (1, 1), (1, -1)):
                ni, nj = (i + di) % n_az, j + dj
                if 0 <= nj < n_alt:
                    a, b = graph.nodes[(i, j)], graph.nodes[(ni, nj)]
                    graph.add_edge(
                        (i, j), (ni, nj),
                        weight=angular_separation(a["az"], a["alt"], b["az"], b["alt"]),
                    )
    return graph


def find_clear_view(
    occlusions: Iterable[Occlusion | Sequence[float]],
    target: tuple[float, float],
    *,
    grid_step: float = 5.0,
    fov: float = 50.0,
    graph: nx.Graph | None = None,
) -> tuple[float, float] | None:
    """Suggest a camera pan that avoids occlusions while keeping ``target`` in view.

    Args:
        occlusions: Boxes ``(az_min, az_max, alt_min, alt_max)`` in degrees.
        target: ``(azimuth, altitude)`` of what the user wants to see.
        grid_step: Cell size in degrees.
        fov: Camera field of view in degrees; the chosen direction must keep
            the target within ``fov / 2``.
        graph: Pre-built visibility graph (to reuse across calls).

    Returns:
        ``(azimuth_offset, altitude_offset)`` in degrees from the target to
        the suggested pointing direction (``(0.0, 0.0)`` when the target is
        already clear), or ``None`` if no clear direction keeps it in view.

    Raises:
        ValueError: If the target is below the horizon.
    """
    target_az, target_alt = target[0] % 360.0, float(target[1])
    if not 0.0 <= target_alt <= 90.0:
        raise ValueError(f"Target altitude must be in [0, 90], got {target_alt}")
    boxes = _as_occlusions(occlusions)
    if not any(b.contains(target_az, target_alt) for b in boxes):
        return (0.0, 0.0)

    graph = graph if graph is not None else build_visibility_graph(boxes, grid_step)
    n_az = int(round(360.0 / grid_step))
    n_alt = int(math.ceil(90.0 / grid_step))
    source: Cell = (
        int(target_az // grid_step) % n_az,
        min(int(target_alt // grid_step), n_alt - 1),
    )

    distances = nx.single_source_dijkstra_path_length(
        graph, source, cutoff=fov / 2.0 + grid_step, weight="weight"
    )
    best: tuple[float, float, Cell] | None = None
    for cell, path_cost in distances.items():
        node = graph.nodes[cell]
        if node["occluded"]:
            continue
        if angular_separation(target_az, target_alt, node["az"], node["alt"]) > fov / 2.0:
            continue
        key = (path_cost, -node["alt"], cell)  # prefer higher altitude on ties
        if best is None or key < best:
            best = key
    if best is None:
        return None
    node = graph.nodes[best[2]]
    return (wrap_azimuth_offset(node["az"] - target_az), node["alt"] - target_alt)


def describe_pan(offset: tuple[float, float] | None) -> str:
    """Human-readable guidance for an offset from :func:`find_clear_view`."""
    if offset is None:
        return "No clear view of the target nearby."
    d_az, d_alt = offset
    if abs(d_az) < 1e-9 and abs(d_alt) < 1e-9:
        return "Target is in clear view."
    parts = []
    if abs(d_az) >= 1e-9:
        parts.append(f"pan {'right' if d_az > 0 else 'left'} {abs(d_az):.0f}°")
    if abs(d_alt) >= 1e-9:
        parts.append(f"tilt {'up' if d_alt > 0 else 'down'} {abs(d_alt):.0f}°")
    return "To avoid the obstruction, " + " and ".join(parts) + "."
