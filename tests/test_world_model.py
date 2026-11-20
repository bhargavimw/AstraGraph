"""Tests for the Skyfield-based sky world model.

Ground truth: JPL Horizons is not reachable from the build environment, so
reference positions were computed independently with Astropy 7 (ERFA, the
open implementation of the IAU SOFA routines) using the same catalog entry
for Sirius, proper motion applied, no refraction. Astropy shares no code with
Skyfield, so agreement checks the whole chain: time scales, precession,
nutation, aberration and Earth rotation.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from astragraph.constellation_db import ConstellationDB
from astragraph.world_model import SkyWorldModel, WorldModelConfig, load_catalog, to_utc

NYC = (40.7128, -74.0060)
SIDEREAL_RATE = 360.0 / 23.9344696  # degrees of Earth rotation per hour (~15.04)

# (UTC time, latitude, longitude, azimuth, altitude) of Sirius from Astropy.
SIRIUS_REFERENCE = [
    ("2024-01-15T04:00:00", 40.7128, -74.0060, 178.3557, 32.5217),   # New York, 23:00 EST
    ("2024-03-01T01:30:00", 40.7128, -74.0060, 187.1257, 32.2389),   # New York, 20:30 EST
    ("2023-12-10T20:00:00", 28.6139, 77.2090, 173.2168, 44.3758),    # New Delhi, 01:30 IST
    ("2024-07-20T12:00:00", -33.8688, 151.2093, 194.1594, -38.1934),  # Sydney, below horizon
]


@pytest.fixture(scope="module")
def db() -> ConstellationDB:
    database = ConstellationDB.from_config("config.yaml")
    database.load()
    return database


@pytest.fixture(scope="module")
def model(db: ConstellationDB) -> SkyWorldModel:
    return SkyWorldModel(config=WorldModelConfig(min_altitude=10.0), constellation_db=db)


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def angular_distance(az1: float, alt1: float, az2: float, alt2: float) -> float:
    a1, h1, a2, h2 = map(math.radians, (az1, alt1, az2, alt2))
    c = math.sin(h1) * math.sin(h2) + math.cos(h1) * math.cos(h2) * math.cos(a1 - a2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def hour_angle_and_dec(az: float, alt: float, lat: float) -> tuple[float, float]:
    """Horizontal → (hour angle, declination) in degrees, by spherical trig."""
    a, h, phi = map(math.radians, (az, alt, lat))
    sin_dec = math.sin(phi) * math.sin(h) + math.cos(phi) * math.cos(h) * math.cos(a)
    dec = math.asin(sin_dec)
    ha = math.atan2(
        -math.sin(a) * math.cos(h),
        math.cos(phi) * math.sin(h) - math.sin(phi) * math.cos(h) * math.cos(a),
    )
    return math.degrees(ha) % 360.0, math.degrees(dec)


# ------------------------------------------------------------------- catalog
def test_catalog_has_at_least_the_brightest_100_stars() -> None:
    catalog = load_catalog()
    assert len(catalog) >= 100
    magnitudes = [s.magnitude for s in catalog]
    assert magnitudes == sorted(magnitudes)
    assert catalog[0].name == "Sirius"
    names = {s.name for s in catalog}
    for star in ("Canopus", "Arcturus", "Vega", "Betelgeuse", "Rigel", "Polaris"):
        assert star in names


# --------------------------------------------------------- Test 1: accuracy
@pytest.mark.parametrize("when, lat, lon, ref_az, ref_alt", SIRIUS_REFERENCE)
def test_sirius_position_matches_reference_within_0_1_degree(
    model: SkyWorldModel, when: str, lat: float, lon: float, ref_az: float, ref_alt: float
) -> None:
    position = model.get_star_position("Sirius", utc(when), lat, lon)
    error = angular_distance(position.azimuth, position.altitude, ref_az, ref_alt)
    assert error < 0.1
    assert error < 0.001  # measured agreement is ~0.0001 degrees


def test_bulk_and_single_star_positions_agree(model: SkyWorldModel) -> None:
    when = utc("2024-01-15T04:00:00")
    single = model.get_star_position("Betelgeuse", when, *NYC)
    bulk = next(s for s in model.get_all_stars(when, *NYC) if s.name == "Betelgeuse")
    assert bulk.azimuth == pytest.approx(single.azimuth, abs=1e-9)
    assert bulk.altitude == pytest.approx(single.altitude, abs=1e-9)


# ------------------------------------------------- Test 2: horizon filtering
def test_stars_below_horizon_are_filtered(model: SkyWorldModel) -> None:
    when = utc("2024-01-15T04:00:00")
    everything = model.get_all_stars(when, *NYC)
    visible = model.get_visible_stars(when, *NYC)
    assert any(s.altitude < 0 for s in everything)
    assert 0 < len(visible) < len(everything)
    assert all(s.altitude > 10.0 for s in visible)
    names = {s.name for s in visible}
    assert "Sirius" in names
    assert "Acrux" not in names  # dec -63: never rises at New York


def test_sirius_below_horizon_in_sydney_is_excluded(model: SkyWorldModel) -> None:
    when, lat, lon, *_ = SIRIUS_REFERENCE[3]
    assert "Sirius" not in {s.name for s in model.get_visible_stars(utc(when), lat, lon)}


def test_min_altitude_override(model: SkyWorldModel) -> None:
    when = utc("2024-01-15T04:00:00")
    low = model.get_visible_stars(when, *NYC, min_altitude=0.0)
    high = model.get_visible_stars(when, *NYC, min_altitude=45.0)
    assert len(high) < len(low)
    assert all(s.altitude > 45.0 for s in high)


# --------------------------------------------------- Test 3: prediction
def test_predict_six_hours_ahead_rotates_sky_about_15_degrees_per_hour(
    model: SkyWorldModel,
) -> None:
    now = utc("2024-01-15T02:00:00")
    lat, lon = NYC
    before = {s.name: s for s in model.get_visible_stars(now, lat, lon, min_altitude=-90)}
    after = {s.name: s for s in model.predict_sky(now, lat, lon, 6.0, min_altitude=-90)}

    for name in ("Sirius", "Vega", "Betelgeuse", "Regulus"):
        ha0, dec0 = hour_angle_and_dec(before[name].azimuth, before[name].altitude, lat)
        ha1, dec1 = hour_angle_and_dec(after[name].azimuth, after[name].altitude, lat)
        shift = (ha1 - ha0) % 360.0
        assert shift == pytest.approx(6 * SIDEREAL_RATE, abs=0.1)  # ~90.25 degrees
        assert dec1 == pytest.approx(dec0, abs=0.01)  # a star keeps its declination


def test_predict_sky_equals_visible_stars_at_future_time(model: SkyWorldModel) -> None:
    now = utc("2024-01-15T02:00:00")
    predicted = model.predict_sky(now, *NYC, 3.0)
    direct = model.get_visible_stars(now + timedelta(hours=3), *NYC)
    assert [(s.name, s.azimuth) for s in predicted] == [(s.name, s.azimuth) for s in direct]


def test_negative_hours_predict_the_past(model: SkyWorldModel) -> None:
    now = utc("2024-01-15T06:00:00")
    past = model.predict_sky(now, *NYC, -2.0)
    direct = model.get_visible_stars(now - timedelta(hours=2), *NYC)
    assert [s.name for s in past] == [s.name for s in direct]


# --------------------------------------------------- Test 4: rise and set
def test_sirius_rise_and_set_times_are_reasonable(model: SkyWorldModel) -> None:
    rise, set_ = model.get_rise_set_time(
        "Sirius", date(2024, 1, 15), *NYC, tz=ZoneInfo("America/New_York")
    )
    assert rise is not None and set_ is not None
    # Astropy reference (horizon -0.5667 deg): set 09:08:08 UTC, rise 22:59:29 UTC.
    assert abs((rise - utc("2024-01-15T22:59:29")).total_seconds()) < 60
    assert abs((set_ - utc("2024-01-15T09:08:08")).total_seconds()) < 60
    # Time above the horizon follows cos H = -tan(lat) tan(dec) (~10.2 h).
    lat, dec = math.radians(NYC[0]), math.radians(-16.716)
    expected_hours = 2 * math.degrees(math.acos(-math.tan(lat) * math.tan(dec))) / SIDEREAL_RATE
    next_set = set_ + timedelta(hours=23.934)
    assert (next_set - rise).total_seconds() / 3600 == pytest.approx(expected_hours, abs=0.15)


def test_circumpolar_and_never_rising_stars(model: SkyWorldModel) -> None:
    assert model.get_rise_set_time("Polaris", date(2024, 1, 15), *NYC) == (None, None)
    assert model.get_rise_set_time("Acrux", date(2024, 1, 15), *NYC) == (None, None)


def test_rise_set_returns_utc_datetimes_within_the_local_day(model: SkyWorldModel) -> None:
    tz = ZoneInfo("Asia/Kolkata")
    rise, set_ = model.get_rise_set_time("Vega", date(2024, 6, 1), 28.6139, 77.2090, tz=tz)
    for moment in (rise, set_):
        assert moment is not None and moment.tzinfo == timezone.utc
        assert moment.astimezone(tz).date() == date(2024, 6, 1)


def test_constellation_rise_set(model: SkyWorldModel) -> None:
    rise, set_ = model.get_constellation_rise_set(
        "Orion", date(2024, 1, 15), *NYC, tz=ZoneInfo("America/New_York")
    )
    assert rise is not None and set_ is not None
    local_rise = rise.astimezone(ZoneInfo("America/New_York"))
    assert 14 <= local_rise.hour <= 17  # Orion rises mid-afternoon in January


# ------------------------------------------------- timezones and lookups
def test_naive_datetime_is_rejected(model: SkyWorldModel) -> None:
    with pytest.raises(ValueError, match="Naive datetime"):
        model.get_visible_stars(datetime(2024, 1, 15, 4, 0), *NYC)


def test_same_instant_in_any_timezone_gives_same_sky(model: SkyWorldModel) -> None:
    instant_utc = utc("2024-01-15T04:00:00")
    instant_ist = instant_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    instant_est = instant_utc.astimezone(ZoneInfo("America/New_York"))
    assert to_utc(instant_ist) == to_utc(instant_est) == instant_utc
    a = model.get_star_position("Vega", instant_ist, *NYC)
    b = model.get_star_position("Vega", instant_est, *NYC)
    assert (a.azimuth, a.altitude) == (b.azimuth, b.altitude)


def test_get_constellation_at_direction(model: SkyWorldModel) -> None:
    when = utc("2024-01-15T04:00:00")
    # Due north at an altitude equal to the latitude points at the celestial pole.
    assert model.get_constellation_at(when, *NYC, 0.0, NYC[0]) == "Ursa Minor"
    betelgeuse = model.get_star_position("Betelgeuse", when, *NYC)
    assert model.get_constellation_at(when, *NYC, betelgeuse.azimuth, betelgeuse.altitude) == "Orion"


def test_constellation_position_and_visibility(model: SkyWorldModel) -> None:
    when = utc("2024-01-15T04:00:00")
    az, alt = model.get_constellation_position("Orion", when, *NYC)
    assert 180.0 < az < 230.0 and 35.0 < alt < 60.0  # high in the south-west
    visible = {name for name, *_ in model.visible_constellations(when, *NYC)}
    assert {"Orion", "Canis Major", "Ursa Major"} <= visible
    assert "Scorpius" not in visible  # a summer constellation


def test_invalid_inputs_raise(model: SkyWorldModel) -> None:
    when = utc("2024-01-15T04:00:00")
    with pytest.raises(ValueError):
        model.get_visible_stars(when, 95.0, 0.0)
    with pytest.raises(ValueError):
        model.get_constellation_at(when, *NYC, 0.0, 120.0)
    with pytest.raises(KeyError):
        model.get_star_position("Not A Star", when, *NYC)


def test_demo_script_lists_correct_visible_constellations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "demo_world_model.py"
    spec = importlib.util.spec_from_file_location("demo_world_model", script)
    assert spec and spec.loader
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)

    assert demo.main(["--time", "2024-01-15 21:00", "--tz", "America/New_York"]) == 0
    out = capsys.readouterr().out
    now_section = out.split("Visible constellations right now:")[1].split("Visible constellations in")[0]
    assert "Orion" in now_section and "Canis Major" in now_section
    assert "Scorpius" not in now_section
    rising = out.split("Rising into view:")[1].split("\n")[0]
    assert "Bootes" in rising and "Virgo" in rising  # spring stars rise before midnight
    assert "Orion (centre) rises 2024-01-15 15:49 EST" in out
    assert "Sky map now" in out
