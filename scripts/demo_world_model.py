"""Stage 4 demo: the sky now, the sky in a few hours, and Orion's rise/set.

Usage:
    python scripts/demo_world_model.py                      # now, location from config.yaml
    python scripts/demo_world_model.py --time "2024-01-15 23:00"
    python scripts/demo_world_model.py --lat 28.6139 --lon 77.2090 --tz Asia/Kolkata
    python scripts/demo_world_model.py --hours 6

A ``--time`` without a UTC offset is read in the ``--tz`` timezone (default:
``world_model.timezone`` in config.yaml).

The text sky map is a planisphere view: the zenith in the centre, the horizon
on the rim, north at the top and east on the LEFT (as when looking up).
Labels are IAU constellation abbreviations; ``*`` marks stars brighter than
magnitude 1.5.
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astragraph.constellation_db import ConstellationDB, load_config, resolve_path  # noqa: E402
from astragraph.pipeline import compass_heading  # noqa: E402
from astragraph.world_model import SkyWorldModel, StarPosition, WorldModelConfig  # noqa: E402

MAP_WIDTH, MAP_HEIGHT = 65, 33  # characters (terminal cells are ~2:1)


def compass(azimuth: float) -> str:
    rad = math.radians(azimuth)
    return compass_heading(math.sin(rad), math.cos(rad))


def parse_time(text: str | None, tz: ZoneInfo) -> datetime:
    if text is None:
        return datetime.now(timezone.utc)
    moment = datetime.fromisoformat(text)
    return moment if moment.tzinfo else moment.replace(tzinfo=tz)


def sky_map(model: SkyWorldModel, stars: list[StarPosition]) -> str:
    """ASCII planisphere of visible constellations and bright stars."""
    grid = [[" "] * MAP_WIDTH for _ in range(MAP_HEIGHT)]
    cx, cy = MAP_WIDTH // 2, MAP_HEIGHT // 2
    rx, ry = cx - 2, cy - 1

    def cell(az: float, alt: float) -> tuple[int, int]:
        r = (90.0 - alt) / 90.0
        x = cx - r * rx * math.sin(math.radians(az))  # east on the left
        y = cy - r * ry * math.cos(math.radians(az))  # north at the top
        return int(round(x)), int(round(y))

    for step in range(360):  # horizon circle
        x, y = cell(float(step), 0.0)
        grid[y][x] = "."
    for label, az in (("N", 0.0), ("E", 90.0), ("S", 180.0), ("W", 270.0)):
        x, y = cell(az, -6.0 if label in "NS" else -4.0)
        grid[max(0, min(MAP_HEIGHT - 1, y))][max(0, min(MAP_WIDTH - 1, x))] = label
    grid[cy][cx] = "+"  # zenith

    for star in stars:
        if star.magnitude < 1.5 and star.altitude > 0:
            x, y = cell(star.azimuth, star.altitude)
            grid[y][x] = "*"

    groups: dict[str, list[StarPosition]] = {}
    for star in stars:
        if star.altitude > 0:
            groups.setdefault(star.constellation, []).append(star)
    # Place labels for constellations with the most bright stars first.
    for abbreviation, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        bright = min(members, key=lambda s: s.magnitude)
        x, y = cell(bright.azimuth, bright.altitude)
        x = max(0, min(MAP_WIDTH - len(abbreviation), x + 1))
        span = grid[y][x : x + len(abbreviation)]
        if all(c in " ." for c in span):
            grid[y][x : x + len(abbreviation)] = list(abbreviation)

    return "\n".join("    " + "".join(row).rstrip() for row in grid)


def print_constellations(
    title: str, rows: list[tuple[str, int, float, float]], limit: int = 15
) -> None:
    print(title)
    for name, count, az, alt in rows[:limit]:
        print(f"  {name:20s} {count:2d} bright stars   {compass(az):>2s} "
              f"(az {az:5.1f}°)  alt {alt:4.1f}°")
    if len(rows) > limit:
        print(f"  … and {len(rows) - limit} more")


def fmt_local(moment: datetime | None, tz: ZoneInfo) -> str:
    if moment is None:
        return "—"
    return moment.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--time", help="ISO time, e.g. '2024-01-15 23:00' (default: now)")
    parser.add_argument("--lat", type=float, help="latitude in degrees (north positive)")
    parser.add_argument("--lon", type=float, help="longitude in degrees (east positive)")
    parser.add_argument("--tz", help="IANA timezone for local times, e.g. Asia/Kolkata")
    parser.add_argument("--hours", type=float, default=3.0, help="look-ahead (default 3)")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    section = config.get("world_model") or {}
    wm_config = WorldModelConfig.from_mapping(section)
    lat = wm_config.default_lat if args.lat is None else args.lat
    lon = wm_config.default_lon if args.lon is None else args.lon
    tz = ZoneInfo(args.tz or section.get("timezone", "UTC"))
    catalog = resolve_path(section.get("star_catalog", "data/bright_stars.csv"),
                           relative_to=args.config)

    db = ConstellationDB.from_config(args.config)
    db.load()
    model = SkyWorldModel(catalog, config=wm_config, constellation_db=db)
    now = parse_time(args.time, tz)
    later = now + timedelta(hours=args.hours)

    print(f"AstraGraph world model — lat {lat:.4f}°, lon {lon:.4f}°")
    print(f"Now:   {fmt_local(now, tz)}  ({now.astimezone(timezone.utc):%H:%M} UTC)")
    print(f"Later: {fmt_local(later, tz)}  (+{args.hours:g} h)")
    print(f"Horizon limit: {wm_config.min_altitude:g}° altitude\n")

    visible_now = model.visible_constellations(now, lat, lon)
    visible_later = model.visible_constellations(later, lat, lon)
    print_constellations("Visible constellations right now:", visible_now)
    print()
    print_constellations(f"Visible constellations in {args.hours:g} hours:", visible_later)

    names_now = {r[0] for r in visible_now}
    names_later = {r[0] for r in visible_later}
    print()
    print("  Rising into view: " + (", ".join(sorted(names_later - names_now)) or "none"))
    print("  Setting from view: " + (", ".join(sorted(names_now - names_later)) or "none"))

    print("\nAstraGraph constellations (from the constellation database):")
    for name in db.list_constellations():
        az_now, alt_now = model.get_constellation_position(name, now, lat, lon)
        az_l, alt_l = model.get_constellation_position(name, later, lat, lon)
        state = "visible" if alt_now > wm_config.min_altitude else "below limit"
        print(f"  {name:11s} now {compass(az_now):>2s} alt {alt_now:5.1f}° ({state:11s})"
              f" → in {args.hours:g} h: {compass(az_l):>2s} alt {alt_l:5.1f}°")

    print("\nSky map now (zenith '+', horizon '.', N up, E left, * = mag < 1.5):\n")
    print(sky_map(model, model.get_all_stars(now, lat, lon)))

    local_day: date = now.astimezone(tz).date()
    print(f"\nOrion rise/set for {local_day.isoformat()} ({tz.key}):")

    def rise_then_set(lookup) -> tuple[datetime | None, datetime | None]:
        """Today's rising and the first setting after it (may be tomorrow)."""
        rise, set_ = lookup(local_day)
        if rise is not None and (set_ is None or set_ < rise):
            set_ = lookup(local_day + timedelta(days=1))[1]
        return rise, set_

    rise, set_ = rise_then_set(
        lambda d: model.get_constellation_rise_set("Orion", d, lat, lon, tz=tz)
    )
    if rise is None and set_ is None:
        az, alt = model.get_constellation_position("Orion", now, lat, lon)
        print("  Orion does not cross the horizon today "
              f"({'always up' if alt > 0 else 'never rises'} at this latitude).")
    else:
        print(f"  Orion (centre) rises {fmt_local(rise, tz)}, sets {fmt_local(set_, tz)}")
    for star in ("Betelgeuse", "Rigel"):
        s_rise, s_set = rise_then_set(
            lambda d, s=star: model.get_rise_set_time(s, d, lat, lon, tz=tz)
        )
        print(f"  {star:14s} rises {fmt_local(s_rise, tz)}, sets {fmt_local(s_set, tz)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
