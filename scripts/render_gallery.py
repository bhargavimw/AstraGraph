"""Batch-generate a pre-rendered wallpaper gallery for the AstraGraph frontend.

Usage:
    python scripts/render_gallery.py                      # 36 wallpapers, phone aspect
    python scripts/render_gallery.py --aspects phone desktop square
    python scripts/render_gallery.py --cities nyc tokyo   # subset of cities
    python scripts/render_gallery.py --no-thumbs          # skip thumbnails
    python scripts/render_gallery.py --out-dir /tmp/gallery

For each (city, style):
- Writes outputs/wallpapers/{city}_{style}.png
- Writes outputs/wallpapers/thumbs/{city}_{style}.webp
- Builds an entry in outputs/manifest.json
- Also assembles outputs/frontend_bundle/ (wallpapers/ + thumbs/ + manifest.json)

The frontend team should copy outputs/frontend_bundle/* into their public/ dir.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astragraph.constellation_db import load_config, resolve_path
from astragraph.overlays import RenderOptions
from astragraph.styles import STYLES, get_style
from astragraph.wallpaper import WallpaperRenderer, ASPECT_PRESETS

# --------------------------------------------------------------------------- #
# City definitions: lat, lon, IANA timezone, local render time
# --------------------------------------------------------------------------- #

CITIES: dict[str, dict] = {
    "bengaluru": {
        "lat": 12.9716, "lon": 77.5946, "timezone": "Asia/Kolkata",
        "time": "2026-11-25T23:00", "country": "India", "name": "Bengaluru",
    },
    "mumbai": {
        "lat": 19.0760, "lon": 72.8777, "timezone": "Asia/Kolkata",
        "time": "2026-11-25T21:30", "country": "India", "name": "Mumbai",
    },
    "chennai": {
        "lat": 13.0827, "lon": 80.2707, "timezone": "Asia/Kolkata",
        "time": "2026-11-26T01:00", "country": "India", "name": "Chennai",
    },
    "kolkata": {
        "lat": 22.5726, "lon": 88.3639, "timezone": "Asia/Kolkata",
        "time": "2026-11-25T20:00", "country": "India", "name": "Kolkata",
    },
    "nyc": {
        "lat": 40.7128, "lon": -74.0060, "timezone": "America/New_York",
        "time": "2026-11-25T23:00", "country": "United States", "name": "New York City",
    },
    "tokyo": {
        "lat": 35.6762, "lon": 139.6503, "timezone": "Asia/Tokyo",
        "time": "2026-11-25T23:00", "country": "Japan", "name": "Tokyo",
    },
    "sydney": {
        "lat": -33.8688, "lon": 151.2093, "timezone": "Australia/Sydney",
        "time": "2026-11-25T23:00", "country": "Australia", "name": "Sydney",
    },
    "reykjavik": {
        "lat": 64.1466, "lon": -21.9426, "timezone": "Atlantic/Reykjavik",
        "time": "2026-11-25T22:00", "country": "Iceland", "name": "Reykjavik",
    },
    "cairo": {
        "lat": 30.0444, "lon": 31.2357, "timezone": "Africa/Cairo",
        "time": "2026-11-25T23:00", "country": "Egypt", "name": "Cairo",
    },
}

STYLE_DISPLAY = {
    "classic": "Classic",
    "minimal": "Minimal",
    "vintage": "Vintage",
    "aurora": "Aurora",
}

# Cities whose ALL styles are featured (5 cities × 4 styles = 20 featured)
FEATURED_CITIES = {"bengaluru", "mumbai", "chennai", "kolkata", "nyc"}


# --------------------------------------------------------------------------- #
# Helpers
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


def _compute_moon_phase(renderer: WallpaperRenderer, lat: float, lon: float,
                        moment: datetime) -> str:
    """Compute the Moon phase name for a given moment using Skyfield."""
    from astragraph.world_model import to_utc
    model = renderer.model
    t = model._ts.from_datetime(to_utc(moment))
    observer = model._observer(lat, lon)
    eph = model._eph

    sun_app = observer.at(t).observe(eph["sun"]).apparent()
    moon_app = observer.at(t).observe(eph["moon"]).apparent()

    sun_p = np.array(eph["sun"].at(t).position.km, dtype=np.float64)
    earth_p = np.array(eph["earth"].at(t).position.km, dtype=np.float64)
    moon_p = np.array(eph["moon"].at(t).position.km, dtype=np.float64)

    sun_to_moon = moon_p - sun_p
    earth_to_moon = moon_p - earth_p
    denom = np.linalg.norm(sun_to_moon) * np.linalg.norm(earth_to_moon)
    cos_phase = float(np.dot(sun_to_moon, earth_to_moon) / denom)
    cos_phase = max(-1.0, min(1.0, cos_phase))
    illuminated = (1.0 + cos_phase) / 2.0
    return _moon_phase_name(illuminated)


def _visible_constellations(renderer: WallpaperRenderer, lat: float, lon: float,
                            moment: datetime, limit: int = 8) -> list[str]:
    """Return up to ``limit`` visible constellation names."""
    rows = renderer.model.visible_constellations(
        moment, lat, lon, min_altitude=renderer.world_model_config.min_altitude
    )
    return [name for name, *_ in rows[:limit]]


def _format_caption(city_name: str, moment: datetime,
                    tz_name: str) -> str:
    """Format the caption: 'City · DD Mon YYYY · HH:MM TZ'."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        from zoneinfo import ZoneInfo as _ZI

        tz = _ZI("UTC")
    local = moment.astimezone(tz)
    return (
        f"{city_name} · {local.strftime('%d %b %Y')} · "
        f"{local.strftime('%H:%M')} {local.tzname()}"
    )


# --------------------------------------------------------------------------- #
# Gallery builder
# --------------------------------------------------------------------------- #

def build_gallery(
    cities: dict[str, dict] | None = None,
    styles: list[str] | None = None,
    aspects: list[str] | None = None,
    out_dir: Path | None = None,
    seed: int = 0,
    no_thumbs: bool = False,
) -> dict:
    """Render the full gallery and return the manifest dict.

    Parameters mirror the CLI flags.
    """
    config = load_config()
    wallpaper_cfg = config.get("wallpaper", {})

    cities = cities or CITIES
    styles = styles or list(STYLES.keys())
    aspects = aspects or ["phone"]
    out_dir = out_dir or resolve_path(
        wallpaper_cfg.get("output_dir", "outputs/wallpapers"),
        relative_to=Path("config.yaml").resolve(),
    )
    out_dir = Path(out_dir).expanduser().resolve()

    thumbs_dir = resolve_path(
        wallpaper_cfg.get("thumbnail_dir", "outputs/wallpapers/thumbs"),
        relative_to=Path("config.yaml").resolve(),
    )
    thumbs_dir = Path(thumbs_dir).expanduser().resolve()
    frontend_bundle = resolve_path(
        wallpaper_cfg.get("frontend_bundle", "outputs/frontend_bundle"),
        relative_to=Path("config.yaml").resolve(),
    )
    frontend_bundle = Path(frontend_bundle).expanduser().resolve()

    thumbnail_width = int(wallpaper_cfg.get("thumbnail_width", 400))
    default_magnitude_limit = float(wallpaper_cfg.get("magnitude_limit", 6.0))

    renderer = WallpaperRenderer("config.yaml")

    # Create output directories
    out_dir.mkdir(parents=True, exist_ok=True)
    if not no_thumbs:
        thumbs_dir.mkdir(parents=True, exist_ok=True)
    (frontend_bundle / "wallpapers").mkdir(parents=True, exist_ok=True)
    (frontend_bundle / "thumbs").mkdir(parents=True, exist_ok=True)

    wallpapers: list[dict] = []
    total_stars = 0

    for city_id, city in cities.items():
        lat = city["lat"]
        lon = city["lon"]
        tz = ZoneInfo(city["timezone"])
        local_time = datetime.fromisoformat(city["time"])
        # Attach timezone to make it aware
        if local_time.tzinfo is None:
            local_time = local_time.replace(tzinfo=tz)
        utc_time = local_time.astimezone(ZoneInfo("UTC"))

        moon_phase = _compute_moon_phase(renderer, lat, lon, local_time)
        visible_consts = _visible_constellations(renderer, lat, lon, local_time)
        caption = _format_caption(city["name"], local_time, city["timezone"])
        hemisphere = "northern" if lat >= 0 else "southern"

        for style_name in styles:
            style = get_style(style_name)

            for aspect in aspects:
                width, height = renderer.resolution_for(aspect)

                options = RenderOptions(
                    seed=seed,
                    magnitude_limit=default_magnitude_limit,
                    draw_constellation_lines=True,
                    draw_constellation_labels=True,
                    draw_moon=True,
                    draw_planets=False,
                    draw_caption=True,
                    caption_corner="bottom-left",
                )

                img = renderer.render(
                    lat=lat,
                    lon=lon,
                    moment=local_time,
                    style=style,
                    aspect=aspect,
                    options=options,
                    location_name=city["name"],
                )

                file_id = f"{city_id}_{style_name}_{aspect}"
                filename = f"{city_id}_{style_name}_{aspect}.png"
                out_path = out_dir / filename

                # Save full PNG
                img.save(out_path, dpi=(300, 300))
                file_bytes = out_path.stat().st_size

                # Count stars drawn
                star_count = len(renderer.model.get_visible_stars(
                    local_time, lat, lon,
                    min_altitude=renderer.world_model_config.min_altitude,
                ))
                total_stars += star_count

                # Thumbnail
                thumb_filename = f"{city_id}_{style_name}_{aspect}.webp"
                thumb_path = thumbs_dir / thumb_filename
                if not no_thumbs:
                    thumb = img.copy()
                    w, h = thumb.size
                    new_h = int(h * (thumbnail_width / w))
                    thumb = thumb.resize((thumbnail_width, new_h), Image.LANCZOS)
                    thumb.save(thumb_path, "WEBP", quality=85)

                # Copy into frontend bundle
                bundle_wp = frontend_bundle / "wallpapers" / filename
                shutil.copy2(out_path, bundle_wp)
                if not no_thumbs:
                    bundle_thumb = frontend_bundle / "thumbs" / thumb_filename
                    shutil.copy2(thumb_path, bundle_thumb)

                featured = city_id in FEATURED_CITIES

                tags = [
                    city["country"].lower(),
                    "city",
                    style_name,
                    hemisphere,
                ]

                entry = {
                    "id": file_id,
                    "title": f"{city['name']} — {STYLE_DISPLAY[style_name]}",
                    "city": city["name"],
                    "country": city["country"],
                    "lat": lat,
                    "lon": lon,
                    "timezone": city["timezone"],
                    "datetime_local": local_time.isoformat(),
                    "datetime_utc": utc_time.isoformat().replace("+00:00", "Z"),
                    "style": style_name,
                    "aspect": aspect,
                    "width": width,
                    "height": height,
                    "filename": filename,
                    "path": f"/wallpapers/{filename}",
                    "thumbnail": f"/wallpapers/thumbs/{thumb_filename}",
                    "bytes": file_bytes,
                    "featured": featured,
                    "hemisphere": hemisphere,
                    "tags": tags,
                    "visible_constellations": visible_consts,
                    "moon_phase": moon_phase,
                    "caption": caption,
                }
                wallpapers.append(entry)

    # Sort: featured first, then by city, then style
    wallpapers.sort(key=lambda e: (not e["featured"], e["city"], e["style"]))

    manifest = {
        "generated_at": datetime.now(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
        "engine": "AstraGraph SkyWorldModel (Skyfield + JPL DE421 + HYG v4.1)",
        "count": len(wallpapers),
        "wallpapers": wallpapers,
    }

    # Write manifest to outputs/ and frontend bundle
    manifest_path = out_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    bundle_manifest = frontend_bundle / "manifest.json"
    with bundle_manifest.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "out_dir": out_dir,
        "thumbs_dir": thumbs_dir,
        "frontend_bundle": frontend_bundle,
        "total_stars": total_stars,
    }


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def validate_gallery(manifest: dict, out_dir: Path, thumbs_dir: Path,
                     no_thumbs: bool, expected_count: int) -> list[str]:
    """Validate the generated gallery. Returns a list of error messages."""
    errors: list[str] = []

    if manifest["count"] != expected_count:
        errors.append(
            f"manifest count {manifest['count']} != expected {expected_count}"
        )

    featured_count = sum(1 for w in manifest["wallpapers"] if w["featured"])
    if featured_count != 20:
        errors.append(f"featured count {featured_count} != 20")

    for entry in manifest["wallpapers"]:
        wp_path = out_dir / entry["filename"]
        if not wp_path.exists():
            errors.append(f"missing wallpaper: {entry['filename']}")
        else:
            try:
                with Image.open(wp_path) as img:
                    if img.size != (entry["width"], entry["height"]):
                        errors.append(
                            f"{entry['filename']}: size {img.size} "
                            f"!= {(entry['width'], entry['height'])}"
                        )
                    if img.size != (1080, 2340):
                        errors.append(
                            f"{entry['filename']}: not phone aspect 1080x2340"
                        )
            except Exception as exc:
                errors.append(f"cannot open {entry['filename']}: {exc}")

        if not no_thumbs:
            thumb_name = Path(entry["thumbnail"]).name
            thumb_path = thumbs_dir / thumb_name
            if not thumb_path.exists():
                errors.append(f"missing thumbnail: {thumb_name}")

    return errors


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch-generate AstraGraph wallpaper gallery."
    )
    parser.add_argument(
        "--cities", nargs="*", default=None,
        help="Subset of city IDs to render (default: all 9)",
    )
    parser.add_argument(
        "--styles", nargs="*", default=None,
        help="Styles to render (default: all 4)",
    )
    parser.add_argument(
        "--aspects", nargs="*", default=None,
        help="Aspect presets (default: phone). Options: phone desktop square",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Deprecated: magnitude limit is read from config.yaml",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=None,
        help="Output directory for wallpapers (default: config wallpaper.output_dir)",
    )
    parser.add_argument(
        "--seed", type=int, default=0,
        help="Deterministic seed (default: 0)",
    )
    parser.add_argument(
        "--no-thumbs", action="store_true",
        help="Skip WebP thumbnail generation",
    )
    args = parser.parse_args(argv)

    # Filter cities/styles/aspects
    cities = None
    if args.cities:
        cities = {c: CITIES[c] for c in args.cities if c in CITIES}
        unknown = set(args.cities) - set(CITIES)
        if unknown:
            print(f"Warning: unknown cities ignored: {sorted(unknown)}")

    styles = None
    if args.styles:
        unknown = set(args.styles) - set(STYLES)
        if unknown:
            print(f"Warning: unknown styles ignored: {sorted(unknown)}")
        styles = [s for s in args.styles if s in STYLES]

    aspects = None
    if args.aspects:
        unknown = set(args.aspects) - set(ASPECT_PRESETS)
        if unknown:
            print(f"Warning: unknown aspects ignored: {sorted(unknown)}")
        aspects = [a for a in args.aspects if a in ASPECT_PRESETS]

    result = build_gallery(
        cities=cities,
        styles=styles,
        aspects=aspects,
        out_dir=args.out_dir,
        seed=args.seed,
        no_thumbs=args.no_thumbs,
    )

    manifest = result["manifest"]
    out_dir = result["out_dir"]
    thumbs_dir = result["thumbs_dir"]

    # Validation
    expected_count = len(cities or CITIES) * len(styles or STYLES) * \
        len(aspects or ["phone"])
    errors = validate_gallery(manifest, out_dir, thumbs_dir, args.no_thumbs,
                              expected_count)
    if errors:
        print("\nVALIDATION ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return 1

    # Summary table
    print("\nAstraGraph wallpaper gallery — summary")
    print("=" * 95)
    print(f"{'City':<14} {'Style':<10} {'Aspect':<9} {'Filename':<40} {'Size':>8} {'Stars':>6}")
    print("-" * 95)
    for entry in manifest["wallpapers"]:
        size_kb = entry["bytes"] / 1024
        print(
            f"{entry['city']:<14} {entry['style']:<10} {entry['aspect']:<9} "
            f"{entry['filename']:<40} {size_kb:>7.1f}K {'—':>6}"
        )
    print("=" * 95)
    print(f"Total wallpapers: {manifest['count']}")
    print(f"Featured: {sum(1 for w in manifest['wallpapers'] if w['featured'])}")
    print(f"Total gallery size: {sum(w['bytes'] for w in manifest['wallpapers']) / 1024 / 1024:.2f} MB")
    print(f"Manifest: {result['manifest_path']}")
    print(f"Frontend bundle: {result['frontend_bundle']}")
    print()
    print("FRONTEND HANDOFF: copy outputs/frontend_bundle/* into your Next.js public/ dir")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
