"""Tests for the wallpaper renderer."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from astragraph.styles import STYLES, get_style
from astragraph.wallpaper import (
    ASPECT_PRESETS,
    RenderOptions,
    WallpaperRenderer,
    bv_to_rgb,
    star_radius,
    star_brightness,
    zenithal_equidistant,
)

NYC = (40.7128, -74.0060)
MOMENT = datetime(2026, 11, 25, 23, 0, tzinfo=ZoneInfo("America/New_York"))


@pytest.fixture
def renderer() -> WallpaperRenderer:
    return WallpaperRenderer()


# ---------------------------------------------------------------- projection

def test_zenithal_equidistant_north_up() -> None:
    # Zenith: alt 90 → centre.
    cx, cy, sky_r = 500.0, 500.0, 400.0
    x, y = zenithal_equidistant(0.0, 90.0, cx, cy, sky_r)
    assert x == pytest.approx(cx)
    assert y == pytest.approx(cy)

    # North (az 0) at alt 0 → top edge.
    x, y = zenithal_equidistant(0.0, 0.0, cx, cy, sky_r)
    assert x == pytest.approx(cx)
    assert y == pytest.approx(cy - sky_r)

    # East (az 90) at alt 0 → left edge (E-left convention).
    x, y = zenithal_equidistant(90.0, 0.0, cx, cy, sky_r)
    assert x == pytest.approx(cx - sky_r)
    assert y == pytest.approx(cy)

    # South (az 180) → bottom edge.
    x, y = zenithal_equidistant(180.0, 0.0, cx, cy, sky_r)
    assert x == pytest.approx(cx)
    assert y == pytest.approx(cy + sky_r)

    # West (az 270) → right edge.
    x, y = zenithal_equidistant(270.0, 0.0, cx, cy, sky_r)
    assert x == pytest.approx(cx + sky_r)
    assert y == pytest.approx(cy)

    # Below horizon → None.
    assert zenithal_equidistant(0.0, -1.0, cx, cy, sky_r) is None


# ---------------------------------------------------------------- star helpers

def test_star_radius_clamped() -> None:
    assert star_radius(1.5) == pytest.approx(8.0)
    assert star_radius(-10.0) == 12.0   # brightest → clamp max
    assert star_radius(20.0) == pytest.approx(2.0)  # formula asymptotes to 2


def test_star_brightness_falls_off() -> None:
    assert star_brightness(0.0) == 1.0
    assert star_brightness(6.0) < star_brightness(1.0)
    assert 0.2 <= star_brightness(10.0) <= 1.0


def test_bv_to_rgb() -> None:
    # B-V = 0 → white
    assert bv_to_rgb(0.0) == (255, 255, 255)
    # Negative B-V → blue-ish
    r, g, b = bv_to_rgb(-0.2)
    assert b > r
    # Positive B-V → red-ish
    r, g, b = bv_to_rgb(1.4)
    assert r > b
    # Clamping at extremes
    assert bv_to_rgb(-10.0) == bv_to_rgb(-0.5)
    assert bv_to_rgb(10.0) == bv_to_rgb(2.2)


# ---------------------------------------------------------------- render

def test_render_nyc_default(renderer: WallpaperRenderer) -> None:
    img = renderer.render(NYC[0], NYC[1], MOMENT, style="classic", aspect="phone")
    assert isinstance(img, Image.Image)
    assert img.size == (1080, 2340)
    assert img.mode == "RGB"


def test_render_all_aspects(renderer: WallpaperRenderer) -> None:
    for aspect, (w, h) in ASPECT_PRESETS.items():
        img = renderer.render(NYC[0], NYC[1], MOMENT, style="classic", aspect=aspect)
        assert img.size == (w, h), f"aspect {aspect}: expected {(w, h)}, got {img.size}"


def test_render_custom_resolution(renderer: WallpaperRenderer) -> None:
    img = renderer.render(
        NYC[0], NYC[1], MOMENT, style="classic", aspect="phone",
        resolution=(800, 1200),
    )
    assert img.size == (800, 1200)


def test_magnitude_limit_increases_stars(renderer: WallpaperRenderer) -> None:
    img_few = renderer.render(
        NYC[0], NYC[1], MOMENT, style="classic", aspect="phone",
        options=RenderOptions(magnitude_limit=1.0),
    )
    img_many = renderer.render(
        NYC[0], NYC[1], MOMENT, style="classic", aspect="phone",
        options=RenderOptions(magnitude_limit=6.0),
    )
    # More stars drawn → different pixel data (not just background).
    assert img_few.tobytes() != img_many.tobytes()


def test_naive_datetime_rejected(renderer: WallpaperRenderer) -> None:
    naive = datetime(2026, 11, 25, 23, 0)
    with pytest.raises(ValueError, match="Naive datetime"):
        renderer.render(NYC[0], NYC[1], naive, style="classic", aspect="phone")


def test_deterministic_same_seed(renderer: WallpaperRenderer) -> None:
    img1 = renderer.render(
        NYC[0], NYC[1], MOMENT, style="classic", aspect="phone",
        options=RenderOptions(seed=42),
    )
    img2 = renderer.render(
        NYC[0], NYC[1], MOMENT, style="classic", aspect="phone",
        options=RenderOptions(seed=42),
    )
    assert img1.tobytes() == img2.tobytes()


def test_different_seed_can_differ(renderer: WallpaperRenderer) -> None:
    img1 = renderer.render(
        NYC[0], NYC[1], MOMENT, style="classic", aspect="phone",
        options=RenderOptions(seed=1),
    )
    img2 = renderer.render(
        NYC[0], NYC[1], MOMENT, style="classic", aspect="phone",
        options=RenderOptions(seed=2),
    )
    # With no randomness in phase 2 these should be identical; the seed is
    # reserved for aurora noise in phase 3.  Same output is fine.
    assert img1.tobytes() == img2.tobytes()


# ---------------------------------------------------------------- output helpers

def test_render_to_file(tmp_path, renderer: WallpaperRenderer) -> None:
    path = tmp_path / "test_wallpaper.png"
    renderer.render_to_file(
        path, lat=NYC[0], lon=NYC[1], moment=MOMENT, style="classic", aspect="phone"
    )
    assert path.exists()
    img = Image.open(path)
    assert img.size == (1080, 2340)


def test_render_to_bytes(renderer: WallpaperRenderer) -> None:
    data = renderer.render_to_bytes(
        lat=NYC[0], lon=NYC[1], moment=MOMENT, style="classic", aspect="phone"
    )
    assert len(data) > 0
    img = Image.open(BytesIO(data))
    assert img.size == (1080, 2340)


def test_resolution_for_unknown_aspect(renderer: WallpaperRenderer) -> None:
    with pytest.raises(ValueError, match="Unknown aspect"):
        renderer.resolution_for("not_an_aspect")


# ---------------------------------------------------------------- styles

def test_every_style_renders(renderer: WallpaperRenderer) -> None:
    for name in STYLES:
        img = renderer.render(
            NYC[0], NYC[1], MOMENT, style=name, aspect="phone"
        )
        assert isinstance(img, Image.Image)
        assert img.size == (1080, 2340)


def test_get_style_unknown_raises() -> None:
    with pytest.raises(KeyError, match="Unknown style"):
        get_style("not_a_style")


def test_get_style_known_returns() -> None:
    for name in ("classic", "minimal", "vintage", "aurora"):
        style = get_style(name)
        assert style.name == name
