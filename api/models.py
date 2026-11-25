"""Pydantic schemas for the AstraGraph wallpaper API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator


class Wallpaper(BaseModel):
    """A single wallpaper entry from the manifest."""

    id: str
    title: str
    city: str
    country: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    timezone: str
    datetime_local: str
    datetime_utc: str
    style: str
    aspect: str
    width: int
    height: int
    filename: str
    path: str
    thumbnail: str
    bytes: int
    featured: bool
    hemisphere: str
    tags: list[str]
    visible_constellations: list[str]
    moon_phase: str
    caption: str


class GalleryResponse(BaseModel):
    """Response for GET /api/gallery."""

    generated_at: str
    engine: str
    count: int
    wallpapers: list[Wallpaper]


class RenderRequest(BaseModel):
    """Request body for POST /api/render."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    datetime_iso: str
    timezone: str = "UTC"
    style: str = "classic"
    aspect: str = "phone"
    overlays: dict[str, bool] | None = None

    @field_validator("datetime_iso")
    @classmethod
    def _parse_datetime(cls, v: str) -> str:
        """Validate that the datetime string is parseable."""
        try:
            moment = datetime.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"Invalid datetime_iso: {v}") from exc
        if moment.tzinfo is None:
            # Naive datetime — must supply a timezone to resolve it
            pass  # resolved at render time using the `timezone` field
        return v

    @model_validator(mode="after")
    def _resolve_timezone(self) -> "RenderRequest":
        """Validate that the timezone exists."""
        try:
            ZoneInfo(self.timezone)
        except Exception as exc:
            raise ValueError(f"Unknown timezone: {self.timezone}") from exc
        return self

    @field_validator("style")
    @classmethod
    def _validate_style(cls, v: str) -> str:
        from astragraph.styles import STYLES

        if v not in STYLES:
            raise ValueError(f"Unknown style: {v}. Available: {sorted(STYLES)}")
        return v

    @field_validator("aspect")
    @classmethod
    def _validate_aspect(cls, v: str) -> str:
        from astragraph.wallpaper import ASPECT_PRESETS

        if v not in ASPECT_PRESETS:
            raise ValueError(f"Unknown aspect: {v}. Available: {sorted(ASPECT_PRESETS)}")
        return v


class HealthResponse(BaseModel):
    """Response for GET /api/health."""

    status: str
    catalog_size: int
    ephemeris: str


# Backward-compatible type aliases
GalleryEntry = Wallpaper
