"""Shared 2-D geometry helpers.

The sky-to-image convention used throughout AstraGraph:

* Sky coordinates are projected with the gnomonic (tangent-plane) projection,
  giving standard coordinates ``(xi, eta)`` in degrees, where ``xi`` points
  east and ``eta`` points north.
* Image coordinates have ``x`` to the right and ``y`` downwards. Looking up at
  the sky with north at the top, east is on the *left*, so the "plane"
  coordinates used for image-like layouts are ``(-xi, -eta)``.

Keeping every module on the same convention means a constellation template
and a camera image differ only by a rotation, a uniform scale and a
translation (a similarity transform), never by a reflection.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def gnomonic_project(
    ra_deg: FloatArray | Sequence[float],
    dec_deg: FloatArray | Sequence[float],
    ra0_deg: float,
    dec0_deg: float,
) -> tuple[FloatArray, FloatArray]:
    """Project equatorial coordinates onto the tangent plane at ``(ra0, dec0)``.

    Returns standard coordinates ``(xi, eta)`` in degrees (east, north).
    """
    ra = np.radians(np.asarray(ra_deg, dtype=float))
    dec = np.radians(np.asarray(dec_deg, dtype=float))
    ra0 = math.radians(ra0_deg)
    dec0 = math.radians(dec0_deg)

    d_ra = ra - ra0
    cos_c = math.sin(dec0) * np.sin(dec) + math.cos(dec0) * np.cos(dec) * np.cos(d_ra)
    if np.any(cos_c <= 0):
        raise ValueError("Point is more than 90 degrees from the projection centre")
    xi = np.cos(dec) * np.sin(d_ra) / cos_c
    eta = (
        math.cos(dec0) * np.sin(dec) - math.sin(dec0) * np.cos(dec) * np.cos(d_ra)
    ) / cos_c
    return np.degrees(xi), np.degrees(eta)


def mean_sky_position(
    ra_deg: Sequence[float], dec_deg: Sequence[float]
) -> tuple[float, float]:
    """Return the vector-mean ``(ra, dec)`` of points, safe across RA = 0."""
    ra = np.radians(np.asarray(ra_deg, dtype=float))
    dec = np.radians(np.asarray(dec_deg, dtype=float))
    x = np.mean(np.cos(dec) * np.cos(ra))
    y = np.mean(np.cos(dec) * np.sin(ra))
    z = np.mean(np.sin(dec))
    ra_mean = math.degrees(math.atan2(y, x)) % 360.0
    dec_mean = math.degrees(math.atan2(z, math.hypot(x, y)))
    return ra_mean, dec_mean


def sky_to_plane(
    ra_deg: Sequence[float], dec_deg: Sequence[float]
) -> FloatArray:
    """Project sky points to image-oriented plane coordinates in degrees.

    The projection centre is the mean position of the points. The result is an
    ``(n, 2)`` array with east to the left and north up (y grows downwards).
    """
    ra0, dec0 = mean_sky_position(ra_deg, dec_deg)
    xi, eta = gnomonic_project(ra_deg, dec_deg, ra0, dec0)
    return np.column_stack([-xi, -eta])


@dataclass(frozen=True)
class Similarity:
    """A 2-D similarity transform ``p' = scale * R(rotation) @ p + translation``.

    ``rotation`` is in radians, counter-clockwise in a y-up frame (which is
    clockwise on screen, where y points down).
    """

    scale: float
    rotation: float
    translation: tuple[float, float]

    def matrix(self) -> FloatArray:
        c, s = math.cos(self.rotation), math.sin(self.rotation)
        return self.scale * np.array([[c, -s], [s, c]])

    def apply(self, points: FloatArray) -> FloatArray:
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        return pts @ self.matrix().T + np.asarray(self.translation)

    def apply_vector(self, vectors: FloatArray) -> FloatArray:
        """Transform direction vectors (no translation)."""
        vecs = np.asarray(vectors, dtype=float).reshape(-1, 2)
        return vecs @ self.matrix().T

    def inverse(self) -> "Similarity":
        inv_scale = 1.0 / self.scale
        inv_rot = -self.rotation
        c, s = math.cos(inv_rot), math.sin(inv_rot)
        tx, ty = self.translation
        itx = -inv_scale * (c * tx - s * ty)
        ity = -inv_scale * (s * tx + c * ty)
        return Similarity(inv_scale, inv_rot, (itx, ity))


def fit_similarity(source: FloatArray, target: FloatArray) -> Similarity:
    """Least-squares similarity (no reflection) mapping ``source`` onto ``target``.

    Uses the closed-form Umeyama solution. Requires at least two points.
    """
    src = np.asarray(source, dtype=float).reshape(-1, 2)
    dst = np.asarray(target, dtype=float).reshape(-1, 2)
    if len(src) != len(dst) or len(src) < 2:
        raise ValueError("Need at least two corresponding points")

    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_c = src - src_mean
    dst_c = dst - dst_mean
    var_src = float(np.sum(src_c**2))
    if var_src == 0.0:
        raise ValueError("Source points are degenerate")

    # Treat points as complex numbers: dst ≈ a * src with a = scale * e^{i θ}.
    zs = src_c[:, 0] + 1j * src_c[:, 1]
    zd = dst_c[:, 0] + 1j * dst_c[:, 1]
    a = np.sum(np.conj(zs) * zd) / var_src
    scale = float(abs(a))
    rotation = float(np.angle(a))
    if scale == 0.0:
        raise ValueError("Degenerate correspondence")
    c, s = math.cos(rotation), math.sin(rotation)
    rot = scale * np.array([[c, -s], [s, c]])
    translation = dst_mean - rot @ src_mean
    return Similarity(scale, rotation, (float(translation[0]), float(translation[1])))


def normalize_points(points: FloatArray) -> FloatArray:
    """Centre points at their centroid and scale so the farthest point is at 1."""
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    centred = pts - pts.mean(axis=0)
    radius = float(np.max(np.linalg.norm(centred, axis=1))) if len(pts) else 0.0
    return centred / radius if radius > 0 else centred


def pairwise_distances(points: FloatArray) -> FloatArray:
    """Return the ``(n, n)`` Euclidean distance matrix of 2-D points."""
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    diff = pts[:, None, :] - pts[None, :, :]
    return np.linalg.norm(diff, axis=-1)
