"""FastAPI service for the AstraGraph wallpaper gallery.

Endpoints:
    GET  /api/health    → {status, catalog_size, ephemeris}
    GET  /api/gallery   → manifest.json contents; ?featured=true and ?city= filters
    GET  /api/wallpapers/{filename} → PNG from outputs/wallpapers/
    POST /api/render    → custom PNG from {lat, lon, datetime_iso, timezone, style, aspect, overlays}

SkyWorldModel, the catalog, and the renderer are loaded ONCE at import time,
never per request.
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from astragraph.constellation_db import load_config, resolve_path
from astragraph.overlays import RenderOptions
from astragraph.styles import STYLES, get_style
from astragraph.wallpaper import ASPECT_PRESETS, WallpaperRenderer

from api.models import GalleryResponse, HealthResponse, RenderRequest, Wallpaper

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"

config = load_config(CONFIG_PATH)
wallpaper_cfg = config.get("wallpaper", {})

WALLPAPERS_DIR = resolve_path(
    wallpaper_cfg.get("output_dir", "outputs/wallpapers"),
    relative_to=CONFIG_PATH,
)
MANIFEST_PATH = WALLPAPERS_DIR / "manifest.json"

# --------------------------------------------------------------------------- #
# Load heavy objects once at import time
# --------------------------------------------------------------------------- #

renderer = WallpaperRenderer(CONFIG_PATH)
catalog_size = len(renderer.model.catalog)
ephemeris_name = "JPL DE421 (via Skyfield)"

# CORS allow-list from config, defaulting to all origins
_cors_raw = config.get("api", {}).get("cors_allow_origins", ["*"])
CORS_ORIGINS = [o.strip() for o in _cors_raw] if isinstance(_cors_raw, list) else ["*"]

# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #

app = FastAPI(title="AstraGraph Wallpaper API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _safe_filename(filename: str) -> str:
    """Reject path-traversal attempts; return a safe basename."""
    if not _FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename


def _load_manifest() -> dict:
    import json

    if not MANIFEST_PATH.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _apply_overlay_options(
    options: RenderOptions, overlays: dict[str, bool] | None
) -> RenderOptions:
    """Merge overlay toggles from a request dict into RenderOptions."""
    if overlays:
        return RenderOptions(
            seed=options.seed,
            magnitude_limit=options.magnitude_limit,
            draw_constellation_lines=overlays.get(
                "constellation_lines", options.draw_constellation_lines
            ),
            draw_constellation_labels=overlays.get(
                "constellation_labels", options.draw_constellation_labels
            ),
            draw_moon=overlays.get("moon", options.draw_moon),
            draw_planets=overlays.get("planets", options.draw_planets),
            draw_caption=overlays.get("caption", options.draw_caption),
            caption_corner=options.caption_corner,
        )
    return options


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health check: service status, catalog size, ephemeris."""
    return HealthResponse(
        status="ok",
        catalog_size=catalog_size,
        ephemeris=ephemeris_name,
    )


@app.get("/api/gallery", response_model=GalleryResponse)
def gallery(
    featured: bool | None = Query(None, description="Filter to featured wallpapers only"),
    city: str | None = Query(None, description="Filter by city ID (e.g. nyc, tokyo)"),
) -> GalleryResponse:
    """Return the manifest, optionally filtered by featured flag or city."""
    manifest = _load_manifest()
    wallpapers = manifest["wallpapers"]

    if featured is True:
        wallpapers = [w for w in wallpapers if w.get("featured")]
    elif featured is False:
        wallpapers = [w for w in wallpapers if not w.get("featured")]
    if city:
        city_lower = city.lower()
        wallpapers = [
            w for w in wallpapers if w["id"].split("_")[0].lower() == city_lower
        ]

    return GalleryResponse(
        generated_at=manifest.get("generated_at", ""),
        engine=manifest.get("engine", ""),
        count=len(wallpapers),
        wallpapers=wallpapers,
    )


@app.get("/api/wallpapers/{filename}")
def wallpaper_file(filename: str) -> FileResponse:
    """Serve a wallpaper PNG file (path-traversal-safe)."""
    _safe_filename(filename)
    file_path = WALLPAPERS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Wallpaper not found")
    return FileResponse(file_path, media_type="image/png")


@app.post("/api/render")
def render_custom(request: RenderRequest) -> StreamingResponse:
    """Render a custom wallpaper PNG on demand."""
    try:
        moment = datetime.fromisoformat(request.datetime_iso)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid datetime_iso: {exc}")

    if moment.tzinfo is None:
        # Resolve naive datetime using the supplied IANA timezone
        try:
            tz = ZoneInfo(request.timezone)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Unknown timezone: {exc}")
        moment = moment.replace(tzinfo=tz)

    style = get_style(request.style)
    width, height = renderer.resolution_for(request.aspect)

    options = _apply_overlay_options(
        RenderOptions(seed=0, magnitude_limit=6.0), request.overlays
    )

    try:
        img = renderer.render(
            lat=request.lat,
            lon=request.lon,
            moment=moment,
            style=style,
            aspect=request.aspect,
            options=options,
            location_name=f"{request.lat:.2f},{request.lon:.2f}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="custom_{request.lat}_{request.lon}.png"'},
    )


# --------------------------------------------------------------------------- #
# Error handler for Pydantic validation errors → 422
# --------------------------------------------------------------------------- #

@app.exception_handler(ValidationError)
async def _validation_exception_handler(request, exc: ValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )
