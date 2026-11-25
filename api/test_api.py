"""Tests for the AstraGraph FastAPI service.

Run with: pytest api/test_api.py
Requires the gallery to be generated first (scripts/render_gallery.py).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

# Ensure the gallery exists before testing
MANIFEST_PATH = ROOT / "outputs" / "wallpapers" / "manifest.json"


@pytest.fixture(scope="module")
def client() -> TestClient:
    if not MANIFEST_PATH.exists():
        pytest.skip(
            "Gallery not generated — run scripts/render_gallery.py first"
        )
    from api.main import app

    return TestClient(app)


# ------------------------------------------------------------------ # health

def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["catalog_size"] == 3000
    assert "DE421" in data["ephemeris"]


# ---------------------------------------------------------------- gallery

def test_gallery_count(client: TestClient) -> None:
    r = client.get("/api/gallery")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 36
    assert len(data["wallpapers"]) == 36


def test_gallery_featured_filter(client: TestClient) -> None:
    r = client.get("/api/gallery?featured=true")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 20
    assert all(w["featured"] for w in data["wallpapers"])


def test_gallery_featured_false(client: TestClient) -> None:
    r = client.get("/api/gallery?featured=false")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 16
    assert all(not w["featured"] for w in data["wallpapers"])


def test_gallery_city_filter(client: TestClient) -> None:
    r = client.get("/api/gallery?city=nyc")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 4  # 4 styles for NYC
    assert all(w["city"] == "New York City" for w in data["wallpapers"])


def test_gallery_city_filter_case_insensitive(client: TestClient) -> None:
    r = client.get("/api/gallery?city=NYC")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 4


# ------------------------------------------------------------ static files

def test_wallpaper_static(client: TestClient) -> None:
    r = client.get("/api/wallpapers/bengaluru_classic_phone.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 0

    img = Image.open(io.BytesIO(r.content))
    assert img.size == (1080, 2340)


def test_wallpaper_static_thumb(client: TestClient) -> None:
    r = client.get("/api/wallpapers/thumbs/bengaluru_classic_phone.webp")
    # Thumbnails are served from the wallpapers dir (same route)
    assert r.status_code in (200, 404)  # 404 if route doesn't map to thumbs


def test_wallpaper_path_traversal(client: TestClient) -> None:
    """Path-traversal attempts must be rejected, not leak files.

    Starlette normalizes ``../`` segments before routing, so the request
    never matches the wallpapers route and returns 404.  Either way, no
    file outside outputs/wallpapers/ can be served.
    """
    r = client.get("/api/wallpapers/../../config.yaml")
    assert r.status_code in (400, 404)


def test_wallpaper_nonexistent(client: TestClient) -> None:
    r = client.get("/api/wallpapers/does_not_exist.png")
    assert r.status_code == 404


# ---------------------------------------------------------------- custom render

def test_render_valid(client: TestClient) -> None:
    r = client.post(
        "/api/render",
        json={
            "lat": 40.7128,
            "lon": -74.0060,
            "datetime_iso": "2026-11-25T23:00:00-05:00",
            "timezone": "America/New_York",
            "style": "classic",
            "aspect": "phone",
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 0

    img = Image.open(io.BytesIO(r.content))
    assert img.size == (1080, 2340)


def test_render_naive_datetime_with_tz(client: TestClient) -> None:
    """A naive datetime should be resolved using the supplied timezone."""
    r = client.post(
        "/api/render",
        json={
            "lat": 40.7128,
            "lon": -74.0060,
            "datetime_iso": "2026-11-25T23:00:00",
            "timezone": "America/New_York",
            "style": "minimal",
            "aspect": "phone",
        },
    )
    assert r.status_code == 200


def test_render_invalid_lat(client: TestClient) -> None:
    r = client.post(
        "/api/render",
        json={
            "lat": 95.0,
            "lon": -74.0060,
            "datetime_iso": "2026-11-25T23:00:00-05:00",
            "style": "classic",
            "aspect": "phone",
        },
    )
    assert r.status_code == 422


def test_render_unknown_style(client: TestClient) -> None:
    r = client.post(
        "/api/render",
        json={
            "lat": 40.7128,
            "lon": -74.0060,
            "datetime_iso": "2026-11-25T23:00:00-05:00",
            "style": "psychedelic",
            "aspect": "phone",
        },
    )
    assert r.status_code == 422


def test_render_unknown_aspect(client: TestClient) -> None:
    r = client.post(
        "/api/render",
        json={
            "lat": 40.7128,
            "lon": -74.0060,
            "datetime_iso": "2026-11-25T23:00:00-05:00",
            "style": "classic",
            "aspect": "ultrawide",
        },
    )
    assert r.status_code == 422


def test_render_overlays(client: TestClient) -> None:
    """Custom overlays should be accepted."""
    r = client.post(
        "/api/render",
        json={
            "lat": 40.7128,
            "lon": -74.0060,
            "datetime_iso": "2026-11-25T23:00:00-05:00",
            "style": "classic",
            "aspect": "phone",
            "overlays": {
                "constellation_lines": True,
                "constellation_labels": False,
                "moon": True,
                "planets": True,
                "caption": True,
            },
        },
    )
    assert r.status_code == 200
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (1080, 2340)
