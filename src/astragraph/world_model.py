"""Deterministic sky world model: where every star is, at any time and place.

Positions come from real astronomy rather than a learned model: Skyfield
combines the star catalog (J2000 positions plus proper motion and parallax)
with Earth's rotation, precession, nutation, aberration and light deflection,
using the JPL DE421 ephemeris for Earth's orbit. Accuracy is at the
arcsecond level, far inside the 0.1 degree target.

Conventions:

* Times must be timezone-aware :class:`datetime.datetime` objects; they are
  converted to UTC internally. Naive datetimes are rejected because their
  meaning is ambiguous (a silent hours-long error).
* Altitude and azimuth are geometric (no atmospheric refraction), matching
  the airless default of online ephemerides such as JPL Horizons. Refraction
  lifts objects near the horizon by up to ~0.6 degrees.
* Azimuth is measured from north through east, in degrees ``[0, 360)``.
* Rise and set times use Skyfield's standard horizon of -0.5667 degrees,
  which includes average refraction, as almanacs do.
"""

from __future__ import annotations

import csv
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from skyfield import almanac
from skyfield.api import (
    Loader,
    Star,
    load,
    load_constellation_map,
    load_constellation_names,
    wgs84,
)

from astragraph.geometry import mean_sky_position

DEFAULT_CATALOG = Path(__file__).resolve().parents[2] / "data" / "bright_stars.csv"
EPHEMERIS_NAME = "de421.bsp"


@dataclass(frozen=True)
class StarPosition:
    """A star's catalog coordinates and where it appears from the observer.

    ``ra`` and ``dec`` are J2000.0 catalog coordinates in degrees (the same
    frame as :class:`astragraph.constellation_db.ConstellationDB`);
    ``azimuth`` and ``altitude`` are apparent horizontal coordinates in
    degrees at the requested time.
    """

    name: str
    ra: float
    dec: float
    azimuth: float
    altitude: float
    magnitude: float
    constellation: str = ""


@dataclass(frozen=True)
class CatalogStar:
    name: str
    hip: int
    ra_hours: float
    dec_degrees: float
    magnitude: float
    pmra_mas: float
    pmdec_mas: float
    parallax_mas: float
    constellation: str


@dataclass(frozen=True)
class WorldModelConfig:
    """``world_model`` block of config.yaml."""

    default_lat: float = 40.7128
    default_lon: float = -74.0060
    min_altitude: float = 10.0
    elevation_m: float = 0.0

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "WorldModelConfig":
        values = values or {}
        known = {f: values[f] for f in cls.__dataclass_fields__ if f in values}
        return cls(**known)


def to_utc(moment: datetime) -> datetime:
    """Convert an aware datetime to UTC; reject naive datetimes."""
    if not isinstance(moment, datetime):
        raise TypeError(f"Expected a datetime, got {type(moment).__name__}")
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(
            "Naive datetime is ambiguous: attach a timezone, e.g. "
            "datetime.now(timezone.utc) or datetime(..., tzinfo=ZoneInfo('Asia/Kolkata'))"
        )
    return moment.astimezone(timezone.utc)


def _validate_location(lat: float, lon: float) -> None:
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"Latitude must be in [-90, 90], got {lat}")
    if not -180.0 <= lon <= 360.0:
        raise ValueError(f"Longitude must be in [-180, 360], got {lon}")


@lru_cache(maxsize=4)
def load_catalog(path: str | Path = DEFAULT_CATALOG) -> tuple[CatalogStar, ...]:
    """Read the bundled bright-star CSV (cached per path)."""
    file = Path(path)
    with file.open(newline="", encoding="utf-8") as handle:
        lines = (line for line in handle if not line.startswith("#"))
        stars = tuple(
            CatalogStar(
                name=row["name"],
                hip=int(row["hip"]),
                ra_hours=float(row["ra_hours"]),
                dec_degrees=float(row["dec_degrees"]),
                magnitude=float(row["magnitude"]),
                pmra_mas=float(row["pmra_mas"]),
                pmdec_mas=float(row["pmdec_mas"]),
                parallax_mas=float(row["parallax_mas"]),
                constellation=row["constellation"],
            )
            for row in csv.DictReader(lines)
        )
    if not stars:
        raise ValueError(f"Star catalog is empty: {file}")
    return stars


@lru_cache(maxsize=1)
def load_ephemeris() -> Any:
    """Load DE421, preferring the copy bundled with ``skyfield-data`` (offline)."""
    try:
        with warnings.catch_warnings():
            # skyfield-data warns about its Earth-orientation file, which is unused here.
            warnings.simplefilter("ignore", RuntimeWarning)
            import skyfield_data

            data_dir = skyfield_data.get_skyfield_data_path()
        return Loader(data_dir, verbose=False)(EPHEMERIS_NAME)
    except (ImportError, OSError):
        cache = Path.home() / ".cache" / "astragraph" / "skyfield"
        return Loader(str(cache), verbose=False)(EPHEMERIS_NAME)


@lru_cache(maxsize=1)
def _timescale() -> Any:
    return load.timescale(builtin=True)


@lru_cache(maxsize=1)
def _constellation_lookup() -> tuple[Any, dict[str, str]]:
    return load_constellation_map(), dict(load_constellation_names())


class SkyWorldModel:
    """Predict star positions, constellations and rise/set times."""

    def __init__(
        self,
        catalog_path: str | Path = DEFAULT_CATALOG,
        *,
        config: WorldModelConfig | None = None,
        constellation_db: Any | None = None,
    ) -> None:
        self.config = config or WorldModelConfig()
        self.catalog = load_catalog(str(catalog_path))
        self.db = constellation_db
        self._eph = load_ephemeris()
        self._earth = self._eph["earth"]
        self._ts = _timescale()
        self._by_name = {s.name.lower(): s for s in self.catalog}
        cat = self.catalog
        self._stars = Star(
            ra_hours=np.array([s.ra_hours for s in cat]),
            dec_degrees=np.array([s.dec_degrees for s in cat]),
            ra_mas_per_year=np.array([s.pmra_mas for s in cat]),
            dec_mas_per_year=np.array([s.pmdec_mas for s in cat]),
            parallax_mas=np.array([s.parallax_mas for s in cat]),
        )

    # ------------------------------------------------------------ helpers
    def _time(self, moment: datetime) -> Any:
        return self._ts.from_datetime(to_utc(moment))

    def _observer(self, lat: float, lon: float) -> Any:
        _validate_location(lat, lon)
        return self._earth + wgs84.latlon(lat, lon, elevation_m=self.config.elevation_m)

    def _star(self, name: str) -> tuple[Star, str]:
        """Skyfield Star for a catalog star, or a ConstellationDB star."""
        entry = self._by_name.get(name.lower())
        if entry is not None:
            return (
                Star(
                    ra_hours=entry.ra_hours,
                    dec_degrees=entry.dec_degrees,
                    ra_mas_per_year=entry.pmra_mas,
                    dec_mas_per_year=entry.pmdec_mas,
                    parallax_mas=entry.parallax_mas,
                ),
                entry.name,
            )
        if self.db is not None:
            try:
                info = self.db.get_star(name)
            except KeyError:
                pass
            else:
                return Star(ra_hours=info["ra"] / 15.0, dec_degrees=info["dec"]), info["name"]
        raise KeyError(f"Unknown star {name!r}")

    def altaz(
        self, ra_degrees: float, dec_degrees: float, time_utc: datetime, lat: float, lon: float
    ) -> tuple[float, float]:
        """Apparent (azimuth, altitude) in degrees of a fixed J2000 position."""
        star = Star(ra_hours=ra_degrees / 15.0, dec_degrees=dec_degrees)
        apparent = self._observer(lat, lon).at(self._time(time_utc)).observe(star).apparent()
        alt, az, _ = apparent.altaz()
        return float(az.degrees), float(alt.degrees)

    def altaz_many(
        self,
        ra_degrees: Sequence[float],
        dec_degrees: Sequence[float],
        time_utc: datetime,
        lat: float,
        lon: float,
    ) -> list[tuple[float, float]]:
        """Vectorised :meth:`altaz`: (azimuth, altitude) for many J2000 positions."""
        if len(ra_degrees) == 0:
            return []
        stars = Star(
            ra_hours=np.asarray(ra_degrees, dtype=float) / 15.0,
            dec_degrees=np.asarray(dec_degrees, dtype=float),
        )
        apparent = self._observer(lat, lon).at(self._time(time_utc)).observe(stars).apparent()
        alt, az, _ = apparent.altaz()
        return [(float(a), float(h)) for a, h in zip(az.degrees, alt.degrees)]

    def best_viewing_month(
        self,
        name: str,
        lat: float,
        lon: float,
        *,
        tz: tzinfo = timezone.utc,
        local_hour: int = 21,
        year: int = 2025,
    ) -> tuple[int, float] | None:
        """Month (1-12) when a constellation stands highest at ``local_hour``.

        Samples the 15th of each month at ``local_hour`` local time and returns
        ``(month, altitude)`` for the best one, or ``None`` if the
        constellation never clears the horizon limit at that hour.
        """
        ra, dec = self._constellation_center(name)
        best: tuple[int, float] | None = None
        for month in range(1, 13):
            moment = datetime(year, month, 15, local_hour, 0, tzinfo=tz)
            _, alt = self.altaz(ra, dec, moment, lat, lon)
            if best is None or alt > best[1]:
                best = (month, alt)
        if best is None or best[1] <= self.config.min_altitude:
            return None
        return best

    # ------------------------------------------------------------- stars
    def get_all_stars(self, time_utc: datetime, lat: float, lon: float) -> list[StarPosition]:
        """Every catalog star with its apparent position (above or below horizon)."""
        observer = self._observer(lat, lon)
        apparent = observer.at(self._time(time_utc)).observe(self._stars).apparent()
        alt, az, _ = apparent.altaz()
        return [
            StarPosition(
                name=s.name,
                ra=s.ra_hours * 15.0,
                dec=s.dec_degrees,
                azimuth=float(a),
                altitude=float(h),
                magnitude=s.magnitude,
                constellation=s.constellation,
            )
            for s, a, h in zip(self.catalog, az.degrees, alt.degrees)
        ]

    def get_visible_stars(
        self,
        time_utc: datetime,
        lat: float,
        lon: float,
        *,
        min_altitude: float | None = None,
    ) -> list[StarPosition]:
        """Stars above ``min_altitude`` (default from config), brightest first."""
        limit = self.config.min_altitude if min_altitude is None else min_altitude
        visible = [s for s in self.get_all_stars(time_utc, lat, lon) if s.altitude > limit]
        return sorted(visible, key=lambda s: s.magnitude)

    def predict_sky(
        self,
        time_utc: datetime,
        lat: float,
        lon: float,
        hours_ahead: float,
        *,
        min_altitude: float | None = None,
    ) -> list[StarPosition]:
        """Visible stars ``hours_ahead`` hours after ``time_utc`` (negative = past)."""
        future = to_utc(time_utc) + timedelta(hours=hours_ahead)
        return self.get_visible_stars(future, lat, lon, min_altitude=min_altitude)

    def get_star_position(
        self, star_name: str, time_utc: datetime, lat: float, lon: float
    ) -> StarPosition:
        """Apparent position of one named star."""
        star, name = self._star(star_name)
        apparent = self._observer(lat, lon).at(self._time(time_utc)).observe(star).apparent()
        alt, az, _ = apparent.altaz()
        entry = self._by_name.get(name.lower())
        return StarPosition(
            name=name,
            ra=float(star.ra.hours) * 15.0,
            dec=float(star.dec.degrees),
            azimuth=float(az.degrees),
            altitude=float(alt.degrees),
            magnitude=entry.magnitude if entry else float("nan"),
            constellation=entry.constellation if entry else "",
        )

    # ------------------------------------------------------ constellations
    def get_constellation_at(
        self, time_utc: datetime, lat: float, lon: float, az: float, alt: float
    ) -> str:
        """IAU constellation (full name) in the direction ``(az, alt)``."""
        if not -90.0 <= alt <= 90.0:
            raise ValueError(f"Altitude must be in [-90, 90], got {alt}")
        topos = wgs84.latlon(lat, lon, elevation_m=self.config.elevation_m)
        _validate_location(lat, lon)
        position = topos.at(self._time(time_utc)).from_altaz(
            alt_degrees=alt, az_degrees=az % 360.0
        )
        lookup, names = _constellation_lookup()
        abbreviation = lookup(position)
        return names.get(abbreviation, abbreviation)

    def constellation_name(self, abbreviation: str) -> str:
        """Full IAU name for an abbreviation such as ``"Ori"``."""
        return _constellation_lookup()[1].get(abbreviation, abbreviation)

    def visible_constellations(
        self,
        time_utc: datetime,
        lat: float,
        lon: float,
        *,
        min_altitude: float | None = None,
    ) -> list[tuple[str, int, float, float]]:
        """IAU constellations with bright stars above the horizon limit.

        Returns ``(full name, bright-star count, mean azimuth, mean altitude)``
        sorted by star count, then name.
        """
        groups: dict[str, list[StarPosition]] = {}
        for star in self.get_visible_stars(time_utc, lat, lon, min_altitude=min_altitude):
            groups.setdefault(star.constellation, []).append(star)
        result = []
        for abbreviation, stars in groups.items():
            az, alt = _mean_horizontal([s.azimuth for s in stars], [s.altitude for s in stars])
            result.append((self.constellation_name(abbreviation), len(stars), az, alt))
        return sorted(result, key=lambda r: (-r[1], r[0]))

    def get_constellation_position(
        self, name: str, time_utc: datetime, lat: float, lon: float
    ) -> tuple[float, float]:
        """(azimuth, altitude) of the centre of a ConstellationDB constellation."""
        ra, dec = self._constellation_center(name)
        return self.altaz(ra, dec, time_utc, lat, lon)

    def _constellation_center(self, name: str) -> tuple[float, float]:
        if self.db is None:
            raise RuntimeError("No ConstellationDB was given to the world model")
        graph = self.db.get_constellation(name)
        return mean_sky_position(
            [graph.nodes[n]["ra"] for n in graph.nodes],
            [graph.nodes[n]["dec"] for n in graph.nodes],
        )

    # ----------------------------------------------------- rise and set
    def _rise_set(
        self, target: Star, day: date, lat: float, lon: float, tz: tzinfo
    ) -> tuple[datetime | None, datetime | None]:
        start = datetime.combine(day, time(0, 0), tzinfo=tz)
        end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=tz)
        observer = self._observer(lat, lon)
        t0, t1 = self._time(start), self._time(end)

        def first(times: Any, real: Any) -> datetime | None:
            for t, ok in zip(times, real):
                if ok:
                    return t.utc_datetime().replace(microsecond=0)
            return None

        rise = first(*almanac.find_risings(observer, target, t0, t1))
        set_ = first(*almanac.find_settings(observer, target, t0, t1))
        return rise, set_

    def get_rise_set_time(
        self,
        star_name: str,
        day: date,
        lat: float,
        lon: float,
        *,
        tz: tzinfo = timezone.utc,
    ) -> tuple[datetime | None, datetime | None]:
        """When ``star_name`` rises and sets during calendar ``day`` in ``tz``.

        Returns UTC datetimes; ``None`` means no rising (or setting) that day —
        the star is circumpolar or never above the horizon at this latitude.
        """
        if isinstance(day, datetime):
            day = day.date()
        star, _ = self._star(star_name)
        return self._rise_set(star, day, lat, lon, tz)

    def get_constellation_rise_set(
        self,
        name: str,
        day: date,
        lat: float,
        lon: float,
        *,
        tz: tzinfo = timezone.utc,
    ) -> tuple[datetime | None, datetime | None]:
        """Rise/set of a ConstellationDB constellation's centre on ``day``."""
        if isinstance(day, datetime):
            day = day.date()
        ra, dec = self._constellation_center(name)
        return self._rise_set(Star(ra_hours=ra / 15.0, dec_degrees=dec), day, lat, lon, tz)


def _mean_horizontal(az: Sequence[float], alt: Sequence[float]) -> tuple[float, float]:
    """Vector mean of horizontal positions (safe across azimuth 0/360)."""
    mean_az, mean_alt = mean_sky_position(list(az), list(alt))
    return mean_az, mean_alt
