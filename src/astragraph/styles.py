"""Style presets for the wallpaper renderer.

Each :class:`Style` describes the colours and behaviour of one wallpaper
theme.  All colours are 8-bit RGB triples.
"""

from __future__ import annotations

from dataclasses import dataclass

# Default noise seed used when a style does not specify one.
DEFAULT_NOISE_SEED: int = 0


@dataclass(frozen=True)
class Style:
    """A wallpaper style preset.

    Attributes:
        name: Style identifier (``"classic"``, ``"minimal"``, …).
        sky_zenith_rgb: Colour at the zenith (centre of the sky disc).
        sky_horizon_rgb: Colour at the horizon (edge of the sky disc).
        star_tint_rgb: Multiplicative tint applied to every star.
        glow_enabled: Whether bright stars get a soft additive glow.
        glow_colour: Colour of the glow halo.
        line_colour: Colour of constellation stick lines.
        label_colour: Colour of constellation labels.
        background_mode: ``"gradient"`` | ``"solid"`` | ``"noise"``.
        noise_seed: Seed for any procedural noise (deterministic).
    """

    name: str
    sky_zenith_rgb: tuple[int, int, int]
    sky_horizon_rgb: tuple[int, int, int]
    star_tint_rgb: tuple[int, int, int]
    glow_enabled: bool
    glow_colour: tuple[int, int, int]
    line_colour: tuple[int, int, int]
    label_colour: tuple[int, int, int]
    background_mode: str = "gradient"
    noise_seed: int = DEFAULT_NOISE_SEED


# ── Preset styles ──────────────────────────────────────────────────────────

STYLES: dict[str, Style] = {
    "classic": Style(
        name="classic",
        sky_zenith_rgb=(12, 22, 64),      # deep navy at zenith
        sky_horizon_rgb=(0, 0, 0),         # black at horizon
        star_tint_rgb=(255, 255, 255),     # neutral white stars
        glow_enabled=True,
        glow_colour=(180, 200, 255),
        line_colour=(130, 150, 190),
        label_colour=(200, 220, 255),
        background_mode="gradient",
        noise_seed=0,
    ),
    "minimal": Style(
        name="minimal",
        sky_zenith_rgb=(0, 0, 0),          # pure black
        sky_horizon_rgb=(0, 0, 0),
        star_tint_rgb=(255, 255, 255),
        glow_enabled=False,
        glow_colour=(255, 255, 255),
        line_colour=(70, 70, 70),
        label_colour=(170, 170, 170),
        background_mode="solid",
        noise_seed=0,
    ),
    "vintage": Style(
        name="vintage",
        sky_zenith_rgb=(244, 228, 193),   # parchment at zenith
        sky_horizon_rgb=(210, 185, 140),   # deeper parchment at horizon
        star_tint_rgb=(160, 110, 60),      # sepia stars
        glow_enabled=False,
        glow_colour=(160, 110, 60),
        line_colour=(110, 70, 35),
        label_colour=(110, 70, 35),
        background_mode="gradient",
        noise_seed=0,
    ),
    "aurora": Style(
        name="aurora",
        sky_zenith_rgb=(18, 30, 70),      # deep blue at zenith
        sky_horizon_rgb=(8, 14, 36),      # slightly lighter at horizon
        star_tint_rgb=(225, 240, 255),
        glow_enabled=True,
        glow_colour=(110, 255, 170),
        line_colour=(90, 210, 140),
        label_colour=(210, 235, 255),
        background_mode="gradient",
        noise_seed=42,
    ),
}


def get_style(name: str) -> Style:
    """Return the style preset for ``name``.

    Raises:
        KeyError: If ``name`` is not a known style.
    """
    if name not in STYLES:
        raise KeyError(
            f"Unknown style: {name!r}. Available: {sorted(STYLES)}"
        )
    return STYLES[name]
