"""AstraGraph API.

Run locally (from the repository root):
    uvicorn api.main:app --reload --port 8000
Interactive docs: http://localhost:8000/docs

Environment:
    ASTRAGRAPH_ALLOWED_ORIGINS  Comma-separated origins allowed by CORS
                                (default: http://localhost:3000).
    ASTRAGRAPH_MAX_UPLOAD_MB    Largest accepted /frame image (default 4).
    ASTRAGRAPH_MAX_SESSIONS     Live camera sessions kept in memory (default 50).
    ASTRAGRAPH_SESSION_TTL      Seconds before an idle session is dropped (default 600).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api import __version__, schemas, services

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    services.resources()  # load the catalogue and ephemeris before the first request
    yield


app = FastAPI(
    lifespan=lifespan,
    title="AstraGraph API",
    version=__version__,
    description="Star detection, constellation identification, sky positions and quizzes.",
)

origins = [o.strip() for o in os.environ.get(
    "ASTRAGRAPH_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    max_age=600,
)

MAX_UPLOAD = int(float(os.environ.get("ASTRAGRAPH_MAX_UPLOAD_MB", "4")) * 1024 * 1024)

Lat = Annotated[float, Query(ge=-90, le=90, description="Latitude, degrees north")]
Lon = Annotated[float, Query(ge=-180, le=180, description="Longitude, degrees east")]
Tz = Annotated[str, Query(min_length=1, description="IANA time zone, e.g. America/New_York")]
At = Annotated[datetime | None, Query(description="Optional ISO time with offset (default: now)")]


def bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def not_found(name: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Unknown constellation: {name}")


def require_aware(at: datetime | None) -> datetime | None:
    if at is not None and at.tzinfo is None:
        raise HTTPException(status_code=400, detail="'at' must include a UTC offset, e.g. 2024-01-15T21:00:00-05:00")
    return at


@app.get("/health", response_model=schemas.Health, tags=["meta"])
def health() -> schemas.Health:
    return schemas.Health(version=__version__)


@app.post("/frame", response_model=schemas.FrameResponse, tags=["live"])
async def frame(
    image: Annotated[UploadFile, File(description="JPEG or PNG camera frame")],
    session_id: Annotated[str, Form(min_length=1, max_length=128)],
) -> schemas.FrameResponse:
    """Detect stars, track them across frames in this session, and identify constellations."""
    data = await image.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="Image too large")
    try:
        return services.process_frame(session_id, data)
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/sky", response_model=schemas.SkyResponse, tags=["sky"])
def sky(lat: Lat, lon: Lon, tz: Tz,
        offset_hours: Annotated[float, Query(ge=-48, le=48)] = 0.0, at: At = None) -> schemas.SkyResponse:
    """Positions of bright stars and every constellation for a place and time (now + offset)."""
    try:
        return services.sky(lat, lon, tz, offset_hours, require_aware(at))
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/tonight", response_model=schemas.TonightResponse, tags=["sky"])
def tonight(lat: Lat, lon: Lon, tz: Tz, at: At = None) -> schemas.TonightResponse:
    """Tonight's summary: darkness, Moon, best constellation, brightest stars, what is up."""
    try:
        return services.tonight(lat, lon, tz, require_aware(at))
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/constellations", response_model=list[schemas.ConstellationSummary], tags=["learn"])
def constellations() -> list[schemas.ConstellationSummary]:
    """All constellations with chart data (for pickers and thumbnails)."""
    return services.constellation_list()


@app.get("/constellation/{name}", response_model=schemas.ConstellationDetail, tags=["learn"])
def constellation(name: str, lat: Lat, lon: Lon, tz: Tz, at: At = None) -> schemas.ConstellationDetail:
    """Chart, stories, best month, current position and tonight's rise/transit/set."""
    try:
        return services.constellation_detail(name, lat, lon, tz, require_aware(at))
    except KeyError as exc:
        raise not_found(name) from exc
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/quiz/new", response_model=schemas.QuizNew, tags=["academy"])
def quiz_new(mode: Literal["easy", "hard"] = "easy", constellation: str | None = None) -> schemas.QuizNew:
    """A connect-the-dots puzzle. Hard mode adds real distractor stars."""
    try:
        return services.new_quiz(mode, constellation)
    except KeyError as exc:
        raise not_found(constellation or "") from exc


@app.post("/quiz/grade", response_model=schemas.QuizGrade, tags=["academy"])
def quiz_grade(body: schemas.QuizGradeRequest) -> schemas.QuizGrade:
    """Grade the drawn lines: correct, missing, extra, and a right-shape hint."""
    try:
        return services.grade_quiz(body.id, body.edges)
    except KeyError as exc:
        raise not_found(body.id.split(":")[0]) from exc
    except ValueError as exc:
        raise bad_request(exc) from exc


@app.get("/demo-sky", response_model=schemas.DemoSkyInfo, tags=["live"])
def demo_sky() -> schemas.DemoSkyInfo:
    """Describe the synthetic demo clip (play it by fetching frames and POSTing them to /frame)."""
    res = services.resources()
    return schemas.DemoSkyInfo(
        constellations=res.db.list_constellations(), frame_count=services.DEMO_FRAMES,
        fps=res.pipeline_config.fps, width=services.DEMO_WIDTH, height=services.DEMO_HEIGHT,
    )


@app.get("/demo-sky/frame", tags=["live"], responses={200: {"content": {"image/jpeg": {}}}},
         response_class=Response)
def demo_sky_frame(constellation: str = "Orion",
                   index: Annotated[int, Query(ge=0)] = 0) -> Response:
    """One JPEG frame of the demo sky (frames loop)."""
    try:
        data = services.DEMO.jpeg(constellation, index)
    except KeyError as exc:
        raise not_found(constellation) from exc
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})
