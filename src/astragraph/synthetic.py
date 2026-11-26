"""Synthetic star-field images for tests and demos.

Real night-sky footage is not bundled with the repository, so the detector,
tracker and matcher are exercised on rendered frames: Gaussian point sources
on a dark background, optional streaks (aircraft trails) and occluding masks
(clouds, trees).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

import networkx as nx
import numpy as np
from numpy.typing import NDArray

from astragraph.geometry import Similarity, sky_to_plane


@dataclass(frozen=True)
class SyntheticStar:
    """A point source to render: pixel position, peak brightness and blur."""

    x: float
    y: float
    brightness: float = 255.0
    sigma: float = 1.5


def magnitude_to_brightness(
    magnitude: float, *, brightest: float = 255.0, faintest: float = 190.0,
    mag_range: tuple[float, float] = (0.0, 3.5),
) -> float:
    """Map a stellar magnitude to an 8-bit peak brightness (brighter = smaller mag)."""
    lo, hi = mag_range
    t = min(max((magnitude - lo) / (hi - lo), 0.0), 1.0)
    return brightest - t * (brightest - faintest)


def render_star_field(
    stars: Iterable[SyntheticStar],
    width: int,
    height: int,
    *,
    noise_std: float = 0.0,
    background: float = 8.0,
    seed: int | None = 0,
) -> NDArray[np.uint8]:
    """Render point sources into a grayscale ``uint8`` image."""
    image = np.full((height, width), background, dtype=np.float64)
    yy, xx = np.mgrid[0:height, 0:width]
    for star in stars:
        radius = int(math.ceil(4 * star.sigma))
        x0, x1 = max(int(star.x) - radius, 0), min(int(star.x) + radius + 2, width)
        y0, y1 = max(int(star.y) - radius, 0), min(int(star.y) + radius + 2, height)
        if x0 >= x1 or y0 >= y1:
            continue
        dx = xx[y0:y1, x0:x1] - star.x
        dy = yy[y0:y1, x0:x1] - star.y
        blob = star.brightness * np.exp(-(dx**2 + dy**2) / (2 * star.sigma**2))
        image[y0:y1, x0:x1] = np.maximum(image[y0:y1, x0:x1], blob)
    if noise_std > 0:
        rng = np.random.default_rng(seed)
        image += rng.normal(0.0, noise_std, image.shape)
    return np.clip(image, 0, 255).astype(np.uint8)


def draw_streak(
    image: NDArray[np.uint8],
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    brightness: float = 240.0,
    thickness: float = 1.5,
) -> NDArray[np.uint8]:
    """Return a copy of ``image`` with a bright linear streak (e.g. aircraft trail)."""
    out = image.astype(np.float64)
    height, width = out.shape
    yy, xx = np.mgrid[0:height, 0:width]
    (x0, y0), (x1, y1) = start, end
    vx, vy = x1 - x0, y1 - y0
    length_sq = vx * vx + vy * vy
    t = np.clip(((xx - x0) * vx + (yy - y0) * vy) / length_sq, 0.0, 1.0)
    dist = np.hypot(xx - (x0 + t * vx), yy - (y0 + t * vy))
    streak = brightness * np.exp(-(dist**2) / (2 * thickness**2))
    return np.clip(np.maximum(out, streak), 0, 255).astype(np.uint8)


def apply_occlusion(
    image: NDArray[np.uint8],
    box: tuple[int, int, int, int],
    *,
    level: int = 12,
) -> NDArray[np.uint8]:
    """Return a copy of ``image`` with the box ``(x0, y0, x1, y1)`` blacked out."""
    out = image.copy()
    x0, y0, x1, y1 = box
    out[y0:y1, x0:x1] = level
    return out


def constellation_layout(
    graph: nx.Graph,
    transform: Similarity,
) -> dict[str, tuple[float, float]]:
    """Place a constellation's stars in pixel space using ``transform``.

    The template is projected with :func:`astragraph.geometry.sky_to_plane`
    (degrees, image-oriented), then mapped to pixels by ``transform``.
    """
    names = list(graph.nodes)
    plane = sky_to_plane(
        [graph.nodes[n]["ra"] for n in names],
        [graph.nodes[n]["dec"] for n in names],
    )
    pixels = transform.apply(plane)
    return {name: (float(px), float(py)) for name, (px, py) in zip(names, pixels)}


def constellation_stars(
    graph: nx.Graph,
    transform: Similarity,
    *,
    sigma: float = 1.6,
    exclude: Sequence[str] = (),
) -> list[SyntheticStar]:
    """Synthetic stars for a constellation, brightness scaled by magnitude."""
    layout = constellation_layout(graph, transform)
    return [
        SyntheticStar(
            x, y, magnitude_to_brightness(float(graph.nodes[name]["magnitude"])), sigma
        )
        for name, (x, y) in layout.items()
        if name not in exclude
    ]


def demo_sky_clip(
    graph: nx.Graph,
    frames: int,
    *,
    seed: int = 0,
    width: int = 960,
    height: int = 720,
    fps: float = 30.0,
    cloud_start: int | None = None,
) -> Iterator[NDArray[np.uint8]]:
    """Yield frames of a demo night sky around one constellation.

    The scene has slight hand-shake drift, a satellite crossing at about
    2 degrees/second, a bright planet near the constellation (not in the
    catalog) and, from ``cloud_start`` (default: halfway), a cloud hiding up
    to two of the faintest stars while always leaving five visible.
    """
    plane_extent = 20.0  # degrees, generous for the largest constellations
    scale = 0.7 * min(width, height) / plane_extent  # pixels per degree
    layout = constellation_layout(graph, Similarity(scale, 0.25, (width / 2, height / 2)))

    hidden = max(0, min(2, graph.number_of_nodes() - 5))
    faintest = sorted(graph.nodes, key=lambda n: -graph.nodes[n]["magnitude"])[:hidden]
    cloud_boxes = [
        (int(layout[s][0]) - 18, int(layout[s][1]) - 18,
         int(layout[s][0]) + 18, int(layout[s][1]) + 18)
        for s in faintest
    ]
    start_cloud = frames // 2 if cloud_start is None else cloud_start

    xs = [p[0] for p in layout.values()]
    ys = [p[1] for p in layout.values()]
    planet_xy = (min(max(xs) + 60, width - 30), (min(ys) + max(ys)) / 2)

    speed_px = 2.0 / fps * scale
    direction = np.array([0.8, -0.6])
    sat_start = np.array([60.0, height - 80.0])

    for k in range(frames):
        drift = (2.0 * math.sin(k / 9.0), 1.5 * math.cos(k / 7.0))  # hand shake
        transform = Similarity(scale, 0.25, (width / 2 + drift[0], height / 2 + drift[1]))
        stars = constellation_stars(graph, transform)
        stars.append(SyntheticStar(planet_xy[0] + drift[0], planet_xy[1] + drift[1], 252.0, 2.0))
        sat = sat_start + direction * speed_px * k
        stars.append(
            SyntheticStar(float(sat[0] + drift[0]), float(sat[1] + drift[1]), 235.0, 1.4)
        )
        frame = render_star_field(stars, width, height, noise_std=3.0, seed=seed + k)
        if k >= start_cloud:
            for box in cloud_boxes:
                frame = apply_occlusion(frame, box)
        yield frame
