"""Matplotlib rendering for constellation graphs.

Right ascension is plotted on the x-axis and increased to the left (standard
sky-chart convention). Declination is plotted on the y-axis. RA values that
straddle the 0-degree boundary are unwrapped so constellations near that
boundary keep their familiar shape.
"""

from __future__ import annotations

import math
from typing import Any

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from astragraph.constellation_db import ConstellationDB

BACKGROUND = "#080d1b"
PANEL_BACKGROUND = "#0d1426"
LINE_COLOR = "#7fa8ff"
STAR_COLOR = "#f5f8ff"
GLOW_COLOR = "#9cc2ff"
LABEL_COLOR = "#c9d6f2"
GRID_COLOR = "#2a3a5e"
TITLE_COLOR = "#eef3ff"


def _unwrap_ra(ra: np.ndarray) -> np.ndarray:
    """Unwrap right ascension across the 0-degree boundary."""
    if ra.size < 2 or float(np.ptp(ra)) <= 180.0:
        return ra.copy()
    shifted = np.where(ra < 180.0, ra + 360.0, ra)
    if float(np.ptp(shifted)) < float(np.ptp(ra)):
        return shifted
    return ra.copy()


def plot_constellation(
    graph: nx.Graph,
    title: str | None = None,
    *,
    ax: Axes | None = None,
    annotate_stars: bool = True,
) -> tuple[Figure, Axes]:
    """Render a constellation with RA on the x-axis (inverted) and Dec on y.

    Args:
        graph: Undirected constellation graph whose nodes expose ``ra``,
            ``dec`` and ``magnitude`` attributes.
        title: Panel title. Defaults to the graph's ``name`` metadata.
        ax: Optional Matplotlib axis for embedding in a multi-panel figure.
        annotate_stars: Whether to print star names next to their markers.

    Returns:
        The ``(figure, axes)`` pair containing the rendering.

    Raises:
        ValueError: If the graph is empty or a node is missing required data.
    """
    if graph.number_of_nodes() == 0:
        raise ValueError("Cannot plot an empty constellation graph")

    for node in graph.nodes:
        missing = [
            field
            for field in ("ra", "dec", "magnitude")
            if field not in graph.nodes[node]
        ]
        if missing:
            raise ValueError(
                f"Node {node!r} is missing required attributes: "
                + ", ".join(missing)
            )

    if ax is None:
        figure, ax = plt.subplots(figsize=(6.4, 5.2), facecolor=BACKGROUND)
    else:
        figure = ax.figure
        figure.set_facecolor(BACKGROUND)
    ax.set_facecolor(PANEL_BACKGROUND)

    nodes = list(graph.nodes)
    ra = _unwrap_ra(
        np.array([graph.nodes[node]["ra"] for node in nodes], dtype=float)
    )
    dec = np.array(
        [graph.nodes[node]["dec"] for node in nodes], dtype=float
    )
    magnitude = np.array(
        [graph.nodes[node]["magnitude"] for node in nodes], dtype=float
    )
    x_by_node = dict(zip(nodes, ra, strict=True))

    for source, target in graph.edges:
        ax.plot(
            [x_by_node[source], x_by_node[target]],
            [graph.nodes[source]["dec"], graph.nodes[target]["dec"]],
            color=LINE_COLOR,
            linewidth=1.6,
            alpha=0.85,
            solid_capstyle="round",
            zorder=2,
        )

    base = float(np.min(magnitude)) if magnitude.size else 0.0
    sizes = 220.0 * np.power(10.0, -0.4 * (magnitude - base))
    sizes = np.clip(sizes, 28.0, 260.0)
    ax.scatter(
        ra,
        dec,
        s=sizes * 2.8,
        color=GLOW_COLOR,
        alpha=0.16,
        linewidths=0,
        zorder=3,
    )
    ax.scatter(
        ra,
        dec,
        s=sizes,
        color=STAR_COLOR,
        edgecolors="#dbe7ff",
        linewidths=0.7,
        zorder=4,
    )

    if annotate_stars:
        for node, x, y, mag in zip(nodes, ra, dec, magnitude, strict=True):
            ax.annotate(
                graph.nodes[node].get("name", node),
                (x, y),
                xytext=(6, 7),
                textcoords="offset points",
                color=LABEL_COLOR,
                fontsize=8.0 if mag < 2.5 else 7.2,
                fontweight="bold" if mag < 2.5 else "normal",
                zorder=5,
            )

    x_span = float(np.ptp(ra))
    dec_span = float(np.ptp(dec))
    padding = max(dec_span, 2.0) * 0.18
    x_min, x_max = float(np.min(ra)), float(np.max(ra))
    dec_min, dec_max = float(np.min(dec)), float(np.max(dec))
    ax.set_xlim(x_max + padding, x_min - padding)  # RA increases to the left
    ax.set_ylim(dec_min - padding, dec_max + padding)
    ax.set_aspect("equal", adjustable="box")

    step = 15.0 if x_span > 60 else (10.0 if x_span > 30 else 5.0)
    first = math.ceil((x_min - padding) / step) * step
    positions = np.arange(first, x_max + padding + step * 0.5, step)
    ax.set_xticks(positions)
    ax.set_xticklabels([f"{p % 360.0:.0f}\N{DEGREE SIGN}" for p in positions])

    ax.set_title(
        title or graph.graph.get("name", "Constellation"),
        color=TITLE_COLOR,
        fontsize=14,
        fontweight="bold",
        pad=10,
    )
    ax.set_xlabel("Right Ascension (deg, J2000)", color=LABEL_COLOR, fontsize=9)
    ax.set_ylabel("Declination (deg, J2000)", color=LABEL_COLOR, fontsize=9)
    ax.tick_params(colors=LABEL_COLOR, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.grid(color=GRID_COLOR, alpha=0.55, linewidth=0.5, linestyle=":")

    return figure, ax


def plot_all_constellations(
    db: ConstellationDB,
    *,
    title: str = "AstraGraph Constellation Database",
    columns: int = 4,
    figure_width: float = 20.0,
    figure_height: float = 11.0,
    annotate_stars: bool = True,
) -> tuple[Figure, list[Axes]]:
    """Draw every constellation in ``db`` as a grid of sky-chart panels.

    Args:
        db: Loaded constellation database.
        title: Figure suptitle.
        columns: Number of grid columns.
        figure_width: Figure width in inches.
        figure_height: Figure height in inches.
        annotate_stars: Whether to print star names next to their markers.

    Returns:
        The ``(figure, visible_axes)`` pair.

    Raises:
        ValueError: If the database contains no constellations.
    """
    entries = [
        (name, db.get_constellation(name)) for name in db.list_constellations()
    ]
    if not entries:
        raise ValueError("No constellations to plot")
    if columns < 1:
        raise ValueError("columns must be at least 1")

    rows = (len(entries) + columns - 1) // columns
    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(figure_width, figure_height),
        facecolor=BACKGROUND,
        squeeze=False,
    )
    flat_axes: list[Axes] = list(axes.flat)
    visible_axes: list[Axes] = []
    for ax, (_name, graph) in zip(flat_axes, entries, strict=False):
        plot_constellation(graph, _name, ax=ax, annotate_stars=annotate_stars)
        visible_axes.append(ax)
    for unused_ax in flat_axes[len(entries) :]:
        unused_ax.set_visible(False)

    figure.suptitle(
        title,
        color=TITLE_COLOR,
        fontsize=20,
        fontweight="bold",
        y=0.995,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.965))
    return figure, visible_axes
