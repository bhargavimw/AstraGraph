"""Response and request models for the AstraGraph API.

Field names are snake_case. Pixel coordinates in /frame responses are in the
pixel space of the image that was sent (x right, y down). Sky positions are
degrees: azimuth from north through east, altitude above the horizon.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Compass = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


# --------------------------------------------------------------------- common
class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


class SkyStar(BaseModel):
    name: str
    az: float
    alt: float
    magnitude: float
    ci: float | None = Field(None, description="B−V colour index (null if unknown)")


# ---------------------------------------------------------------------- /frame
class FrameStar(BaseModel):
    id: int
    x: float
    y: float
    r: float = Field(description="Suggested ring radius in pixels")
    brightness: float


class FrameConstellationStar(BaseModel):
    id: int
    name: str


class FrameConstellation(BaseModel):
    name: str
    confidence: float
    matched: int
    total: int
    lines: list[tuple[float, float, float, float]] = Field(description="[x1, y1, x2, y2] per line")
    label: tuple[float, float] = Field(description="Suggested label anchor [x, y]")
    stars: list[FrameConstellationStar]
    partial: bool = Field(description="True when some stars are hidden (ghosts drawn)")


class FrameGhost(BaseModel):
    name: str
    x: float
    y: float
    r: float


class FrameSatellite(BaseModel):
    id: int
    x: float
    y: float
    vx: float = Field(description="Pixels per frame, relative to the star field")
    vy: float
    speed: float = Field(description="Degrees per second if the plate scale is known, else pixels per second")
    speed_unit: Literal["deg/s", "px/s"]
    direction: Compass | None
    trail: list[tuple[float, float]]


class FrameAnomaly(BaseModel):
    id: int
    x: float
    y: float
    label: str


class FrameEvent(BaseModel):
    type: str
    id: int


class FrameMeta(BaseModel):
    width: int
    height: int
    frame_index: int
    processing_ms: float


class FrameResponse(BaseModel):
    stars: list[FrameStar]
    constellations: list[FrameConstellation]
    ghosts: list[FrameGhost]
    satellites: list[FrameSatellite]
    anomalies: list[FrameAnomaly]
    events: list[FrameEvent]
    plan: None = Field(
        None,
        description="Camera-pan hint. Always null for now: it needs the camera's "
        "azimuth/altitude, which a single image does not provide.",
    )
    meta: FrameMeta


# ------------------------------------------------------------------------ /sky
class Moon(BaseModel):
    phase_name: str
    phase_degrees: float = Field(description="0 = new, 90 = first quarter, 180 = full, 270 = last quarter")
    illumination: float = Field(description="Fraction of the disc lit, 0–1")
    waxing: bool
    altitude: float


class SkyConstellation(BaseModel):
    name: str
    abbreviation: str
    az: float = Field(description="Azimuth of the constellation's centre")
    alt: float
    direction: Compass
    visible: bool = Field(description="Centre above the horizon limit")
    stars: list[SkyStar]
    lines: list[tuple[str, str]]


class SkyResponse(BaseModel):
    time_utc: str
    time_local: str
    tz: str
    lat: float
    lon: float
    sun_altitude: float
    darkness: Literal["day", "twilight", "night"]
    moon: Moon
    stars: list[SkyStar] = Field(description="Bright stars above the horizon")
    constellations: list[SkyConstellation]


# --------------------------------------------------------------------- /tonight
class DarknessDark(BaseModel):
    state: Literal["dark"] = "dark"
    minutes_until_dawn: int


class DarknessLight(BaseModel):
    state: Literal["light"] = "light"
    minutes_until_dark: int


class DarknessNever(BaseModel):
    state: Literal["never-dark"] = "never-dark"


class TonightBest(BaseModel):
    name: str
    altitude: float
    azimuth: float
    direction: Compass


class TonightUp(BaseModel):
    name: str
    direction: Compass


class TonightResponse(BaseModel):
    darkness: DarknessDark | DarknessLight | DarknessNever = Field(discriminator="state")
    dusk_utc: str | None
    dawn_utc: str | None
    moon: Moon
    best: TonightBest | None
    brightest_stars: list[str]
    up_tonight: list[TonightUp]


# --------------------------------------------------------------- constellations
class ChartStar(BaseModel):
    name: str
    designation: str
    ra: float
    dec: float
    magnitude: float
    ci: float | None
    distance_ly: int | None
    fact: str | None


class ConstellationSummary(BaseModel):
    name: str
    abbreviation: str
    stars: list[ChartStar]
    lines: list[tuple[str, str]]


class BestMonth(BaseModel):
    month: int = Field(ge=1, le=12)
    altitude: float


class NowPosition(BaseModel):
    az: float
    alt: float
    direction: Compass
    visible: bool


class RiseTransitSet(BaseModel):
    rise_utc: str | None
    transit_utc: str | None
    set_utc: str | None
    transit_altitude: float | None
    circumpolar: bool
    never_rises: bool


class ConstellationDetail(ConstellationSummary):
    mythology: str
    best_season: str
    fun_fact: str
    best_month: BestMonth | None
    now: NowPosition
    tonight: RiseTransitSet


# ------------------------------------------------------------------------ quiz
class QuizStar(BaseModel):
    name: str
    x: float = Field(description="Chart x in degrees, east to the LEFT")
    y: float = Field(description="Chart y in degrees, north UP")
    magnitude: float
    ci: float | None


class QuizNew(BaseModel):
    id: str
    constellation: str
    mode: Literal["easy", "hard"]
    stars: list[QuizStar]
    line_count: int


class QuizGradeRequest(BaseModel):
    id: str
    edges: list[tuple[str, str]]


class QuizGrade(BaseModel):
    constellation: str
    score: float
    perfect: bool
    correct: list[tuple[str, str]]
    missing: list[tuple[str, str]]
    extra: list[tuple[str, str]]
    isomorphic_hint: bool = Field(description="Right shape, wrong stars")


# ------------------------------------------------------------------------ demo
class DemoSkyInfo(BaseModel):
    constellations: list[str]
    frame_count: int
    fps: float
    width: int
    height: int
