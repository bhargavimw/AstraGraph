"""Wallpaper renderer built on top of :class:`astragraph.world_model.SkyWorldModel`.

Renders a zenithal-equidistant sky chart (zenith at centre, north up, east
left) as a wallpaper using Pillow.  Output is deterministic: the same
latitude, longitude, moment, style, aspect and seed always produce
byte-identical pixels.

Public API::

    renderer = WallpaperRenderer("config.yaml")
    img = renderer.render(lat, lon, moment, style="classic", aspect="phone")
    renderer.render_to_file("out.png", lat=..., lon=..., moment=..., ...)
    png_bytes = renderer.render_to_bytes(lat=..., lon=..., moment=..., ...)
"""

from __future__ import annotations

import io
import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from astragraph.constellation_db import ConstellationDB, load_config, resolve_path
from astragraph.styles import STYLES, Style, get_style
from astragraph.world_model import SkyWorldModel, WorldModelConfig


# --------------------------------------------------------------------------- #
# Aspect presets
# --------------------------------------------------------------------------- #

ASPECT_PRESETS: dict[str, tuple[int, int]] = {
    "phone": (1080, 2340),
    "desktop": (3840, 2160),
    "square": (2048, 2048),
}


# --------------------------------------------------------------------------- #
# Colour: B-V → RGB blackbody approximation
# --------------------------------------------------------------------------- #

_BV_CONTROL_POINTS: list[tuple[float, float, float, float]] = [
    # (bv, r, g, b)
    (-0.50, 0.15, 0.35, 1.00),   # deep blue
    (-0.20, 0.55, 0.78, 1.00),   # blue-white
    (0.00, 1.00, 1.00, 1.00),    # white
    (0.35, 1.00, 0.94, 0.82),    # warm white
    (0.60, 1.00, 0.89, 0.72),    # yellow-white (Sun-like)
    (1.00, 1.00, 0.76, 0.56),    # orange-yellow
    (1.40, 1.00, 0.60, 0.30),    # orange-red
    (2.20, 1.00, 0.40, 0.20),    # red
]


@lru_cache(maxsize=512)
def bv_to_rgb(bv: float) -> tuple[int, int, int]:
    """Convert a B-V colour index to an 8-bit RGB triplet via linear
    interpolation over blackbody control points.  Missing/NaN B-V (0.0)
    falls through to the white control point."""
    bv = max(-0.50, min(2.20, bv))
    for i in range(len(_BV_CONTROL_POINTS) - 1):
        b0, r0, g0, b0c = _BV_CONTROL_POINTS[i]
        b1, r1, g1, b1c = _BV_CONTROL_POINTS[i + 1]
        if b0 <= bv <= b1:
            t = (bv - b0) / (b1 - b0) if b1 > b0 else 0.0
            return (
                int(round((r0 + (r1 - r0) * t) * 255)),
                int(round((g0 + (g1 - g0) * t) * 255)),
                int(round((b0c + (b1c - b0c) * t) * 255)),
            )
    return (255, 255, 255)


# --------------------------------------------------------------------------- #
# Star rendering helpers
# --------------------------------------------------------------------------- #

def star_radius(mag: float) -> float:
    """Radius in px for a star of apparent magnitude ``mag``.

    ``clamp(2 + 6 * 10**(-0.4 * (mag - 1.5)), 1, 12)``.
    """
    r = 2.0 + 6.0 * 10 ** (-0.4 * (mag - 1.5))
    return max(1.0, min(12.0, r))


def star_brightness(mag: float) -> float:
    """Relative brightness (0–1) falling off with magnitude so faint stars
    stay subtle."""
    return max(0.20, min(1.0, 10 ** (-0.4 * (mag - 1.0))))


# --------------------------------------------------------------------------- #
# Projection: zenithal equidistant, N-up, E-left
# --------------------------------------------------------------------------- #

def zenithal_equidistant(
    az_deg: float,
    alt_deg: float,
    cx: float,
    cy: float,
    sky_radius: float,
) -> tuple[float, float] | None:
    """Project horizontal coordinates (azimuth, altitude) onto the image
    plane using a zenithal-equidistant projection centred on the zenith.

    Convention (per ``docs/decisions.md``): north is up, east is on the
    left, RA increases to the left — the sky is never mirrored.

    Returns ``None`` for objects below the horizon (alt < 0).
    """
    if alt_deg < 0.0:
        return None
    az = math.radians(az_deg)
    zenith_dist = 90.0 - alt_deg          # 0 at zenith, 90 at horizon
    r = (zenith_dist / 90.0) * sky_radius
    x = cx - r * math.sin(az)             # E-left
    y = cy - r * math.cos(az)             # N-up
    return (x, y)


# --------------------------------------------------------------------------- #
# Renderer
# --------------------------------------------------------------------------- #

class WallpaperRenderer:
    """Render sky wallpapers from the AstraGraph world model."""

    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        self.config_path = Path(config_path).expanduser().resolve()
        self.config: dict[str, Any] = load_config(self.config_path)

        wallpaper_cfg = self.config.get("wallpaper", {})
        self.output_dir = resolve_path(
            wallpaper_cfg.get("output_dir", "outputs/wallpapers"),
            relative_to=self.config_path,
        )
        self.thumbnail_dir = resolve_path(
            wallpaper_cfg.get("thumbnail_dir", "outputs/wallpapers/thumbs"),
            relative_to=self.config_path,
        )
        self.frontend_bundle = resolve_path(
            wallpaper_cfg.get("frontend_bundle", "outputs/frontend_bundle"),
            relative_to=self.config_path,
        )
        self.default_width = int(wallpaper_cfg.get("default_width", 1080))
        self.default_height = int(wallpaper_cfg.get("default_height", 2340))
        self.thumbnail_width = int(wallpaper_cfg.get("thumbnail_width", 400))
        self.default_style = str(wallpaper_cfg.get("default_style", "classic"))
        self.default_magnitude_limit = float(
            wallpaper_cfg.get("magnitude_limit", 6.0)
        )
        self.dpi = int(wallpaper_cfg.get("dpi", 300))

        wm_cfg = self.config.get("world_model", {})
        self.world_model_config = WorldModelConfig.from_mapping(wm_cfg)
        catalog_path = resolve_path(
            wm_cfg.get("star_catalog", "data/bright_stars.csv"),
            relative_to=self.config_path,
        )
        db_path = resolve_path(
            self.config.get("paths", {}).get(
                "constellation_data", "data/constellations.json"
            ),
            relative_to=self.config_path,
        )

        # SkyWorldModel and ConstellationDB are loaded once, never per frame.
        self.model = SkyWorldModel(catalog_path, config=self.world_model_config)
        self.db = ConstellationDB(str(db_path))
        self.db.load()

        # Name → B-V lookup from the catalog, for star colours.  Stars not in
        # the catalog (e.g. from ConstellationDB) fall back to 0.0 → white.
        self._bv_by_name: dict[str, float] = {
            s.name: s.bv_mag for s in self.model.catalog
        }

    # ------------------------------------------------------------------ #
    # Resolution helpers
    # ------------------------------------------------------------------ #

    def resolution_for(
        self, aspect: str, resolution: tuple[int, int] | None = None
    ) -> tuple[int, int]:
        """Return (width, height) for an aspect preset or explicit size."""
        if resolution is not None:
            return resolution
        if aspect not in ASPECT_PRESETS:
            raise ValueError(
                f"Unknown aspect: {aspect!r}. Available: {sorted(ASPECT_PRESETS)}"
            )
        return ASPECT_PRESETS[aspect]

    # ------------------------------------------------------------------ #
    # Core render
    # ------------------------------------------------------------------ #

    def render(
        self,
        lat: float,
        lon: float,
        moment: datetime,
        style: str | Style = "classic",
        aspect: str = "phone",
        resolution: tuple[int, int] | None = None,
        options: RenderOptions | None = None,
        location_name: str | None = None,
    ) -> Image.Image:
        """Render one wallpaper frame as a PIL Image.

        ``moment`` must be timezone-aware (naive datetimes are rejected by
        ``SkyWorldModel``).  ``location_name`` is used for the caption.
        """
        from astragraph.overlays import RenderOptions, apply_overlays

        if isinstance(style, str):
            style = get_style(style)

        options = options or RenderOptions()
        width, height = self.resolution_for(aspect, resolution)

        # Visible stars above the configured horizon limit, then apply the
        # render magnitude limit.
        stars = self.model.get_visible_stars(
            moment, lat, lon, min_altitude=self.world_model_config.min_altitude
        )
        stars = [s for s in stars if s.magnitude <= options.magnitude_limit]

        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        cx, cy = width / 2.0, height / 2.0
        sky_radius = min(width, height) * 0.40

        self._draw_background(img, style, cx, cy, sky_radius)
        self._draw_stars(img, draw, stars, style, cx, cy, sky_radius)

        # Apply overlays (constellation lines, labels, moon, planets, caption).
        from astragraph.overlays import apply_overlays

        img = apply_overlays(
            img,
            self,
            lat,
            lon,
            moment,
            style,
            options,
            cx,
            cy,
            sky_radius,
        )

        return img

    # ------------------------------------------------------------------ #
    # Background
    # ------------------------------------------------------------------ #

    def _draw_background(
        self, img: Image.Image, style: Style, cx: float, cy: float, sky_radius: float
    ) -> None:
        width, height = img.size
        yy, xx = np.mgrid[0:height, 0:width]
        dx = xx - cx
        dy = yy - cy
        dist = np.sqrt(dx ** 2 + dy ** 2)
        t = np.clip(dist / sky_radius, 0.0, 1.0)

        zc = np.array(style.sky_zenith_rgb, dtype=np.float32)[None, None, :]
        hc = np.array(style.sky_horizon_rgb, dtype=np.float32)[None, None, :]
        gradient = zc + (hc - zc) * t[..., None]
        img.paste(Image.fromarray(gradient.astype(np.uint8)))

    # ------------------------------------------------------------------ #
    # Stars
    # ------------------------------------------------------------------ #

    def _draw_stars(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        stars: list,
        style: Style,
        cx: float,
        cy: float,
        sky_radius: float,
    ) -> None:
        width, height = img.size

        # Glow layer for bright stars (mag < 1.5) — additive Gaussian halo.
        glow_layer = Image.new("L", (width, height), 0)
        glow_draw = ImageDraw.Draw(glow_layer)

        for star in stars:
            pos = zenithal_equidistant(
                star.azimuth, star.altitude, cx, cy, sky_radius
            )
            if pos is None:
                continue
            x, y = pos
            if x < -60 or x > width + 60 or y < -60 or y > height + 60:
                continue

            radius = star_radius(star.magnitude)
            brightness = star_brightness(star.magnitude)

            # Colour from B-V, tinted by style, scaled by brightness.
            bv = self._bv_by_name.get(star.name, 0.0)
            base_rgb = bv_to_rgb(bv)
            col = (
                int(base_rgb[0] * style.star_tint_rgb[0] / 255 * brightness),
                int(base_rgb[1] * style.star_tint_rgb[1] / 255 * brightness),
                int(base_rgb[2] * style.star_tint_rgb[2] / 255 * brightness),
            )

            # Star core.
            draw.ellipse(
                [x - radius, y - radius, x + radius, y + radius],
                fill=col,
            )

            # Soft additive glow for the brightest stars.
            if style.glow_enabled and star.magnitude < 1.5:
                glow_radius = max(4.0, radius * 3.0)
                glow_intensity = int(
                    255 * brightness * max(0.0, 1.5 - star.magnitude) / 1.5
                )
                glow_draw.ellipse(
                    [
                        x - glow_radius,
                        y - glow_radius,
                        x + glow_radius,
                        y + glow_radius,
                    ],
                    fill=glow_intensity,
                )

        if style.glow_enabled:
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=10))
            base_arr = np.array(img, dtype=np.float32)
            glow_arr = np.array(glow_layer, dtype=np.float32)[..., None]
            combined = np.clip(base_arr + glow_arr * 0.55, 0, 255).astype(np.uint8)
            img.paste(Image.fromarray(combined))

    # ------------------------------------------------------------------ #
    # Output helpers
    # ------------------------------------------------------------------ #

    def render_to_file(
        self,
        path: str | Path,
        dpi: int | None = None,
        **render_kwargs: Any,
    ) -> None:
        """Render and save to ``path``.  ``dpi`` defaults to config value."""
        img = self.render(**render_kwargs)
        save_dpi = dpi if dpi is not None else self.dpi
        img.save(path, dpi=(save_dpi, save_dpi))

    def render_to_bytes(
        self, format: str = "PNG", **render_kwargs: Any
    ) -> bytes:
        """Render and return the image as bytes (PNG by default)."""
        img = self.render(**render_kwargs)
        buf = io.BytesIO()
        img.save(buf, format=format)
        return buf.getvalue()
