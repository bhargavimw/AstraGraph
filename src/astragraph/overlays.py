"""Wallpaper overlays: constellation lines, labels, moon, planets and caption.

These functions draw on top of the base sky image produced by
:class:`astragraph.wallpaper.WallpaperRenderer`.  Every overlay is
independently toggleable via :class:`RenderOptions`; with all toggles off the
output is still a valid image.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from astragraph.styles import Style
from astragraph.wallpaper import zenithal_equidistant
from astragraph.world_model import to_utc

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from astragraph.wallpaper import WallpaperRenderer


# --------------------------------------------------------------------------- #
# Render options (overlay toggles live here)
# --------------------------------------------------------------------------- #

@dataclass
class RenderOptions:
    """Rendering options including per-overlay toggles.

    Attributes:
        seed: Deterministic seed (reserved for aurora noise in later phases).
        magnitude_limit: Faintest star magnitude to draw.
        draw_constellation_lines: Draw constellation stick lines.
        draw_constellation_labels: Draw constellation names.
        draw_moon: Draw the Moon disc with terminator.
        draw_planets: Draw labelled discs for Venus/Mars/Jupiter/Saturn.
        draw_caption: Draw the location/time caption.
        caption_override: Override the auto-generated caption text.
        caption_corner: Corner for the caption (bottom-left, bottom-right,
            top-left or top-right).
    """

    seed: int = 0
    magnitude_limit: float = 6.0
    draw_constellation_lines: bool = True
    draw_constellation_labels: bool = True
    draw_moon: bool = True
    draw_planets: bool = False
    draw_caption: bool = True
    caption_override: str | None = None
    caption_corner: str = "bottom-left"
    """Corner for the caption: bottom-left, bottom-right, top-left or top-right."""


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #

_FONT_CANDIDATES: list[str] = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:\\\\Windows\\\\Fonts\\\\arial.ttf",
]


@lru_cache(maxsize=16)
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a truetype font at ``size`` px, falling back to PIL default."""
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# --------------------------------------------------------------------------- #
# Moon phase
# --------------------------------------------------------------------------- #

def _moon_phase_name(fraction: float) -> str:
    """Return a common phase name from an illuminated fraction (0–1)."""
    if fraction < 0.0625:
        return "new"
    if fraction < 0.1875:
        return "waxing crescent"
    if fraction < 0.3125:
        return "first quarter"
    if fraction < 0.4375:
        return "waxing gibbous"
    if fraction < 0.5625:
        return "full"
    if fraction < 0.6875:
        return "waning gibbous"
    if fraction < 0.8125:
        return "last quarter"
    if fraction < 0.9375:
        return "waning crescent"
    return "new"


# --------------------------------------------------------------------------- #
# Constellation lines
# --------------------------------------------------------------------------- #

def _draw_constellation_lines(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    renderer: "WallpaperRenderer",
    lat: float,
    lon: float,
    moment: datetime,
    style: Style,
    cx: float,
    cy: float,
    sky_radius: float,
) -> None:
    """Draw constellation stick lines for all visible constellations."""
    width, height = img.size
    line_colour = style.line_colour
    stroke = max(1, int(min(width, height) * 0.002))

    db = renderer.db
    model = renderer.model

    for name in db.list_constellations():
        graph = db.get_constellation(name)
        # Collect positions of member stars that are above the horizon.
        positions: dict[str, tuple[float, float]] = {}
        for star_name in graph.nodes:
            try:
                sp = model.get_star_position(star_name, moment, lat, lon)
            except KeyError:
                continue
            if sp.altitude <= 0.0:
                continue
            pos = zenithal_equidistant(
                sp.azimuth, sp.altitude, cx, cy, sky_radius
            )
            if pos is None:
                continue
            positions[star_name] = pos

        # Draw each stick-figure edge where both endpoints are visible.
        for a, b in graph.edges:
            pa = positions.get(a)
            pb = positions.get(b)
            if pa is None or pb is None:
                continue
            # Clip: skip if both endpoints are far off-frame.
            if (pa[0] < -sky_radius or pa[0] > width + sky_radius
                    and pb[0] < -sky_radius or pb[0] > width + sky_radius):
                continue
            if (pa[1] < -sky_radius or pa[1] > height + sky_radius
                    and pb[1] < -sky_radius or pb[1] > height + sky_radius):
                continue
            draw.line([pa, pb], fill=line_colour, width=stroke)


def _draw_constellation_labels(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    renderer: "WallpaperRenderer",
    lat: float,
    lon: float,
    moment: datetime,
    style: Style,
    font: ImageFont.FreeTypeFont,
    cx: float,
    cy: float,
    sky_radius: float,
) -> None:
    """Draw constellation names at the centroid of visible member stars."""
    width, height = img.size
    label_colour = style.label_colour

    db = renderer.db
    model = renderer.model

    for name in db.list_constellations():
        graph = db.get_constellation(name)
        pts: list[tuple[float, float]] = []
        for star_name in graph.nodes:
            try:
                sp = model.get_star_position(star_name, moment, lat, lon)
            except KeyError:
                continue
            if sp.altitude <= 0.0:
                continue
            pos = zenithal_equidistant(
                sp.azimuth, sp.altitude, cx, cy, sky_radius
            )
            if pos is None:
                continue
            pts.append(pos)

        if not pts:
            continue
        # Skip if the constellation is mostly below the horizon: require at
        # least half of its stars to be visible.
        if len(pts) < graph.number_of_nodes() / 2:
            continue

        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)

        # Skip if the label would be entirely off-frame.
        if mx < -100 or mx > width + 100 or my < -100 or my > height + 100:
            continue

        abbreviation = graph.graph.get("abbreviation", name[:3])
        bbox = draw.textbbox((0, 0), abbreviation, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = mx - tw / 2
        y = my - th / 2 - 6

        # Small black outline for readability on the gradient.
        for dx_, dy_ in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text((x + dx_, y + dy_), abbreviation, font=font, fill=(0, 0, 0))
        draw.text((x, y), abbreviation, font=font, fill=label_colour)


# --------------------------------------------------------------------------- #
# Moon
# --------------------------------------------------------------------------- #

def _draw_moon(
    img: Image.Image,
    renderer: "WallpaperRenderer",
    lat: float,
    lon: float,
    moment: datetime,
    cx: float,
    cy: float,
    sky_radius: float,
    width: int,
    height: int,
) -> Image.Image:
    """Draw the Moon disc with a correct terminator.

    Returns the (possibly modified) image.  The Moon is omitted entirely if it
    is below the horizon.
    """
    model = renderer.model
    t = model._ts.from_datetime(to_utc(moment))
    observer = model._observer(lat, lon)
    eph = model._eph

    moon_app = observer.at(t).observe(eph["moon"]).apparent()
    alt, az, _ = moon_app.altaz()
    if alt.degrees < 0.0:
        return img  # below horizon — skip

    sun_app = observer.at(t).observe(eph["sun"]).apparent()

    pos = zenithal_equidistant(az.degrees, alt.degrees, cx, cy, sky_radius)
    if pos is None:
        return img
    mx, my = pos

    # ---- Illuminated fraction from the Sun-Moon-Earth phase angle ----
    sun_p = np.array(eph["sun"].at(t).position.km, dtype=np.float64)
    earth_p = np.array(eph["earth"].at(t).position.km, dtype=np.float64)
    moon_p = np.array(eph["moon"].at(t).position.km, dtype=np.float64)

    sun_to_moon = moon_p - sun_p
    earth_to_moon = moon_p - earth_p
    denom = np.linalg.norm(sun_to_moon) * np.linalg.norm(earth_to_moon)
    cos_phase = float(np.dot(sun_to_moon, earth_to_moon) / denom)
    cos_phase = max(-1.0, min(1.0, cos_phase))
    illuminated = (1.0 + cos_phase) / 2.0

    # ---- Terminator orientation: position angle of the Sun from the Moon ----
    sun_ra, sun_dec, _ = sun_app.radec()
    moon_ra, moon_dec, _ = moon_app.radec()

    dra = math.radians((sun_ra.hours - moon_ra.hours) * 15.0)
    ds = math.radians(sun_dec.degrees)
    dm = math.radians(moon_dec.degrees)

    y = math.sin(dra) * math.cos(ds)
    x = math.cos(dm) * math.sin(ds) - math.sin(dm) * math.cos(ds) * math.cos(dra)
    pa = math.degrees(math.atan2(y, x)) % 360.0  # from north through east

    # Image convention: N up, E left.  0 = right, 90 = up, 180 = left,
    # 270 = down.
    sun_angle = (90.0 + pa) % 360.0

    # ---- Draw ----
    diameter = max(20, min(width, height) * 0.05)
    radius = diameter / 2.0

    y0 = int(my - radius)
    x0 = int(mx - radius)
    y1 = y0 + int(diameter) + 2
    x1 = x0 + int(diameter) + 2

    cy0, cy1 = max(0, y0), min(height, y1)
    cx0, cx1 = max(0, x0), min(width, x1)
    if cy0 >= cy1 or cx0 >= cx1:
        return img

    local_yy, local_xx = np.mgrid[cy0:cy1, cx0:cx1]
    dy = local_yy - my
    dx = local_xx - mx
    dist = np.sqrt(dx ** 2 + dy ** 2)
    in_disc = dist <= radius

    angle = np.degrees(np.arctan2(-dy, dx)) % 360.0
    ang_diff = np.abs((angle - sun_angle + 180.0) % 360.0 - 180.0)
    shadow = (ang_diff > 90.0) & in_disc

    arr = np.array(img)
    moon_colour = np.array([150, 150, 160], dtype=np.uint8)
    shadow_colour = np.array([75, 75, 85], dtype=np.uint8)

    patch = arr[cy0:cy1, cx0:cx1]
    patch[in_disc] = moon_colour
    patch[shadow] = shadow_colour
    arr[cy0:cy1, cx0:cx1] = patch

    return Image.fromarray(arr)


# --------------------------------------------------------------------------- #
# Planets
# --------------------------------------------------------------------------- #

_PLANETS: list[tuple[str, str]] = [
    ("venus", "Venus"),
    ("mars", "Mars"),
    ("jupiter barycenter", "Jupiter"),
    ("saturn barycenter", "Saturn"),
]


def _draw_planets(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    renderer: "WallpaperRenderer",
    lat: float,
    lon: float,
    moment: datetime,
    style: Style,
    font: ImageFont.FreeTypeFont,
    cx: float,
    cy: float,
    sky_radius: float,
    width: int,
    height: int,
) -> None:
    """Draw labelled discs for bright planets above the horizon."""
    model = renderer.model
    t = model._ts.from_datetime(to_utc(moment))
    observer = model._observer(lat, lon)
    eph = model._eph

    for key, label in _PLANETS:
        try:
            app = observer.at(t).observe(eph[key]).apparent()
        except KeyError:
            continue
        alt, az, _ = app.altaz()
        if alt.degrees < 0.0:
            continue

        pos = zenithal_equidistant(az.degrees, alt.degrees, cx, cy, sky_radius)
        if pos is None:
            continue
        px, py = pos

        radius = max(4, int(min(width, height) * 0.012))
        if px < -radius or px > width + radius or py < -radius or py > height + radius:
            continue

        # Planetary disc (pale yellow-white)
        draw.ellipse(
            [px - radius, py - radius, px + radius, py + radius],
            fill=(230, 230, 220),
            outline=(180, 180, 170),
        )

        # Label just below the disc
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        lx = px - tw / 2
        ly = py + radius + 4
        for dx_, dy_ in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text((lx + dx_, ly + dy_), label, font=font, fill=(0, 0, 0))
        draw.text((lx, ly), label, font=font, fill=style.label_colour)


# --------------------------------------------------------------------------- #
# Caption
# --------------------------------------------------------------------------- #

def _format_caption(
    location_name: str | None,
    moment: datetime,
    config: dict[str, Any],
    override: str | None,
) -> str:
    if override:
        return override
    tz_name = config.get("world_model", {}).get("timezone", "UTC")
    try:
        tz = __import__("zoneinfo").ZoneInfo(tz_name)
    except Exception:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
    local = moment.astimezone(tz)
    return (
        f"{location_name or ''} · "
        f"{local.strftime('%d %b %Y')} · "
        f"{local.strftime('%H:%M')} {local.tzname()}"
    ).strip(" ·")


def _draw_caption(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    renderer: "WallpaperRenderer",
    lat: float,
    lon: float,
    moment: datetime,
    style: Style,
    font: ImageFont.FreeTypeFont,
    width: int,
    height: int,
    options: RenderOptions,
) -> None:
    """Draw the location/time caption in a configured corner."""
    config = renderer.config
    location_name = None
    wm_cfg = config.get("wallpaper", {})
    if "default_location" in wm_cfg:
        location_name = wm_cfg["default_location"]

    text = _format_caption(location_name, moment, config, options.caption_override)
    if not text:
        return

    corner = options.caption_corner
    margin = 30

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    if corner == "bottom-right":
        x = width - tw - margin
        y = height - th - margin
    elif corner == "top-left":
        x = margin
        y = margin
    elif corner == "top-right":
        x = width - tw - margin
        y = margin
    else:  # bottom-left
        x = margin
        y = height - th - margin

    # Black outline for readability on the gradient background.
    for dx_, dy_ in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw.text((x + dx_, y + dy_), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=style.label_colour)


# --------------------------------------------------------------------------- #
# Master overlay applier
# --------------------------------------------------------------------------- #

def apply_overlays(
    img: Image.Image,
    renderer: "WallpaperRenderer",
    lat: float,
    lon: float,
    moment: datetime,
    style: Style,
    options: RenderOptions,
    cx: float,
    cy: float,
    sky_radius: float,
) -> Image.Image:
    """Apply all enabled overlays to ``img`` and return it.

    The base star field must already be drawn on ``img`` before calling this.
    """
    draw = ImageDraw.Draw(img)
    width, height = img.size

    font_small = _load_font(max(12, int(height * 0.02)))
    font_tiny = _load_font(max(10, int(height * 0.015)))

    if options.draw_constellation_lines:
        _draw_constellation_lines(
            img, draw, renderer, lat, lon, moment, style, cx, cy, sky_radius
        )
    if options.draw_constellation_labels:
        _draw_constellation_labels(
            img, draw, renderer, lat, lon, moment, style,
            font_small, cx, cy, sky_radius,
        )

    # Moon may return a new image (numpy manipulation), so re-acquire draw.
    if options.draw_moon:
        img = _draw_moon(
            img, renderer, lat, lon, moment, cx, cy, sky_radius, width, height
        )
        draw = ImageDraw.Draw(img)

    if options.draw_planets:
        _draw_planets(
            img, draw, renderer, lat, lon, moment, style,
            font_tiny, cx, cy, sky_radius, width, height,
        )

    if options.draw_caption:
        _draw_caption(
            img, draw, renderer, lat, lon, moment, style,
            font_small, width, height, options,
        )

    return img
