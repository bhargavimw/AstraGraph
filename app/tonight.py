""""Tonight's sky" summary for the home page.

Pure computation (no Streamlit), so it can be tested directly.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from astragraph.constellation_db import ConstellationDB  # noqa: E402
from astragraph.world_model import SkyWorldModel  # noqa: E402

MOON_EMOJI = {
    "New Moon": "🌑", "Waxing Crescent": "🌒", "First Quarter": "🌓",
    "Waxing Gibbous": "🌔", "Full Moon": "🌕", "Waning Gibbous": "🌖",
    "Last Quarter": "🌗", "Waning Crescent": "🌘",
}
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compass(azimuth: float) -> str:
    return COMPASS[int(((azimuth % 360) + 22.5) // 45) % 8]


@dataclass(frozen=True)
class VisibleConstellation:
    name: str
    azimuth: float
    altitude: float

    @property
    def direction(self) -> str:
        return compass(self.azimuth)


@dataclass(frozen=True)
class TonightSummary:
    """What to look for tonight from one place."""

    dusk: datetime | None
    dawn: datetime | None
    viewing_time: datetime
    dark_now: bool
    never_dark: bool
    moon_phase: str
    moon_emoji: str
    moon_illuminated: float
    moon_up: bool
    constellations: tuple[VisibleConstellation, ...] = field(default=())
    bright_stars: tuple[str, ...] = field(default=())

    @property
    def best(self) -> VisibleConstellation | None:
        return self.constellations[0] if self.constellations else None

    @property
    def moon_advice(self) -> str:
        if self.moon_illuminated < 0.25 or not self.moon_up:
            return "Great conditions: the Moon won't wash out the fainter stars."
        if self.moon_illuminated < 0.7:
            return "Fair conditions: some moonlight, but the main stars are easy to see."
        return "Bright moonlight: only the brightest stars will stand out."


def tonight_summary(
    model: SkyWorldModel,
    db: ConstellationDB,
    lat: float,
    lon: float,
    tz: tzinfo,
    now: datetime | None = None,
) -> TonightSummary:
    """Summarise the coming (or current) night at ``lat``/``lon``.

    The viewing time is now if it is already dark, otherwise one hour after
    dusk. Before dawn the night that is already in progress is used.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local_day = now.astimezone(tz).date()
    dusk, dawn = model.darkness_window(local_day - timedelta(days=1), lat, lon, tz=tz)
    if not (dusk and dawn and dusk <= now < dawn):  # not inside last night's darkness
        dusk, dawn = model.darkness_window(local_day, lat, lon, tz=tz)

    never_dark = dusk is None
    dark_now = bool(dusk and dawn and dusk <= now < dawn) or (
        dusk is not None and dawn is None and now >= dusk
    )
    if dark_now:
        viewing = now
    elif dusk is not None:
        viewing = dusk + timedelta(hours=1)
    else:  # never fully dark: use local midnight, the darkest it gets
        viewing = datetime.combine(local_day + timedelta(days=1),
                                   datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)

    moon = model.moon_info(viewing, lat, lon)
    limit = model.config.min_altitude
    visible = []
    for name in db.list_constellations():
        az, alt = model.get_constellation_position(name, viewing, lat, lon)
        if alt > limit:
            visible.append(VisibleConstellation(name, az, alt))
    visible.sort(key=lambda c: -c.altitude)
    stars = tuple(s.name for s in model.get_visible_stars(viewing, lat, lon)[:5])

    return TonightSummary(
        dusk=dusk,
        dawn=dawn,
        viewing_time=viewing,
        dark_now=dark_now,
        never_dark=never_dark,
        moon_phase=moon["phase_name"],
        moon_emoji=MOON_EMOJI.get(moon["phase_name"], "🌙"),
        moon_illuminated=moon["illuminated"],
        moon_up=moon["altitude"] > 0,
        constellations=tuple(visible),
        bright_stars=stars,
    )
