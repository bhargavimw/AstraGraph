"""Tests for the FastAPI layer (api/), using FastAPI's in-process test client."""

from __future__ import annotations

from datetime import datetime

import cv2
import numpy as np
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

NYC = {"lat": 40.7128, "lon": -74.006, "tz": "America/New_York"}
EVENING = {**NYC, "at": "2024-01-15T21:00:00-05:00"}  # a January night in New York


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ----------------------------------------------------------------------- meta
def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_cors_allows_configured_origin_only(client: TestClient) -> None:
    ok = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_openapi_docs_are_served(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    for path in ("/frame", "/sky", "/tonight", "/constellation/{name}", "/quiz/new", "/quiz/grade"):
        assert path in schema["paths"]


# ------------------------------------------------------------------------ sky
def test_sky_for_a_january_evening(client: TestClient) -> None:
    r = client.get("/sky", params=EVENING)
    assert r.status_code == 200
    data = r.json()
    assert data["darkness"] == "night" and data["sun_altitude"] < -18
    assert data["moon"]["phase_name"] == "Waxing Crescent" and data["moon"]["waxing"]
    assert data["time_local"].startswith("2024-01-15T21:00")
    names = {c["name"]: c for c in data["constellations"]}
    assert len(names) == 8
    orion = names["Orion"]
    assert orion["visible"] and orion["direction"] in ("SE", "S")
    assert len(orion["stars"]) == 8 and len(orion["lines"]) == 9
    assert not names["Scorpius"]["visible"]
    sirius = next(s for s in data["stars"] if s["name"] == "Sirius")
    assert sirius["ci"] == pytest.approx(0.009, abs=0.01) and sirius["alt"] > 0
    assert all(s["alt"] > -2 for s in data["stars"])


def test_sky_offset_moves_the_sky(client: TestClient) -> None:
    now = client.get("/sky", params=EVENING).json()
    later = client.get("/sky", params={**EVENING, "offset_hours": 6}).json()
    assert later["time_local"].startswith("2024-01-16T03:00")
    orion_now = next(c for c in now["constellations"] if c["name"] == "Orion")
    orion_later = next(c for c in later["constellations"] if c["name"] == "Orion")
    assert orion_later["alt"] < orion_now["alt"]  # setting in the west by 3 am
    assert orion_later["direction"] in ("W", "SW")


# --------------------------------------------------------------------- tonight
def test_tonight_summary(client: TestClient) -> None:
    r = client.get("/tonight", params=EVENING)
    assert r.status_code == 200
    data = r.json()
    assert data["darkness"]["state"] == "dark"
    assert 540 <= data["darkness"]["minutes_until_dawn"] <= 570  # dawn ~06:14 EST
    assert data["best"]["name"] in {c["name"] for c in data["up_tonight"]}
    assert "Orion" in {c["name"] for c in data["up_tonight"]}
    assert len(data["brightest_stars"]) == 5
    assert data["dusk_utc"].endswith("Z") and data["dawn_utc"].endswith("Z")


def test_time_zone_aliases_are_accepted(client: TestClient) -> None:
    # Chrome reports India's zone as "Asia/Calcutta" (the older alias of
    # Asia/Kolkata); both must work, which needs the tzdata package.
    delhi = {"lat": 28.6139, "lon": 77.209, "at": "2024-01-15T21:00:00+05:30"}
    for tz in ("Asia/Calcutta", "Asia/Kolkata"):
        r = client.get("/tonight", params={**delhi, "tz": tz})
        assert r.status_code == 200, (tz, r.text)


def test_tonight_before_dark(client: TestClient) -> None:
    data = client.get("/tonight", params={**NYC, "at": "2024-01-15T12:00:00-05:00"}).json()
    assert data["darkness"]["state"] == "light"
    assert 330 <= data["darkness"]["minutes_until_dark"] <= 360  # dusk ~17:57 EST


# ------------------------------------------------------------- constellations
def test_constellation_list(client: TestClient) -> None:
    data = client.get("/constellations").json()
    assert [c["name"] for c in data] == sorted(c["name"] for c in data)
    assert len(data) == 8
    orion = next(c for c in data if c["name"] == "Orion")
    rigel = next(s for s in orion["stars"] if s["name"] == "Rigel")
    assert rigel["ci"] < 0.1 and rigel["distance_ly"] and rigel["fact"]


def test_constellation_detail(client: TestClient) -> None:
    r = client.get("/constellation/orion", params=EVENING)  # case-insensitive
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Orion" and data["abbreviation"] == "Ori"
    assert data["mythology"] and data["fun_fact"] and data["best_season"] == "Winter"
    assert data["best_month"]["month"] == 1
    assert data["now"]["visible"]
    t = data["tonight"]
    rise, transit, set_ = (datetime.fromisoformat(t[k].replace("Z", "+00:00"))
                           for k in ("rise_utc", "transit_utc", "set_utc"))
    assert rise < transit < set_
    assert t["transit_altitude"] == pytest.approx(49.7, abs=0.6)
    assert not t["circumpolar"] and not t["never_rises"]


def test_circumpolar_and_never_rising(client: TestClient) -> None:
    umi = client.get("/constellation/Ursa Minor", params=EVENING).json()["tonight"]
    assert umi["circumpolar"] and umi["rise_utc"] is None
    tromso = {"lat": 69.65, "lon": 18.96, "tz": "Europe/Oslo", "at": "2024-01-15T21:00:00+01:00"}
    sco = client.get("/constellation/Scorpius", params=tromso).json()["tonight"]
    assert sco["never_rises"] and sco["rise_utc"] is None


def test_errors(client: TestClient) -> None:
    assert client.get("/constellation/Draco", params=EVENING).status_code == 404
    assert client.get("/sky", params={**EVENING, "tz": "Mars/Base"}).status_code == 400
    naive = client.get("/sky", params={**EVENING, "at": "2024-01-15T21:00:00"})
    assert naive.status_code == 400 and "offset" in naive.json()["detail"]
    assert client.get("/sky", params={**EVENING, "lat": 95}).status_code == 422


# ------------------------------------------------------------------------ quiz
def test_quiz_new_hides_answer_details(client: TestClient) -> None:
    easy = client.get("/quiz/new", params={"constellation": "Orion"}).json()
    hard = client.get("/quiz/new", params={"constellation": "Orion", "mode": "hard"}).json()
    assert easy["id"].startswith("Orion:easy:") and hard["mode"] == "hard"
    assert len(easy["stars"]) == 8 and len(hard["stars"]) > 8
    assert easy["line_count"] == 9
    assert all(set(s) == {"name", "x", "y", "magnitude", "ci"} for s in hard["stars"])


def test_quiz_grading(client: TestClient) -> None:
    quiz = client.get("/quiz/new", params={"constellation": "Cassiopeia"}).json()
    perfect = [["Caph", "Schedar"], ["Schedar", "Gamma Cassiopeiae"],
               ["Gamma Cassiopeiae", "Ruchbah"], ["Ruchbah", "Segin"]]
    r = client.post("/quiz/grade", json={"id": quiz["id"], "edges": perfect})
    assert r.json()["perfect"] and r.json()["score"] == 1.0

    # The same zig-zag shape through the wrong stars: "right shape, wrong stars".
    shuffled = [["Caph", "Ruchbah"], ["Ruchbah", "Schedar"],
                ["Schedar", "Segin"], ["Segin", "Gamma Cassiopeiae"]]
    hint = client.post("/quiz/grade", json={"id": quiz["id"], "edges": shuffled}).json()
    assert hint["isomorphic_hint"] and not hint["perfect"]
    assert len(hint["missing"]) + len(hint["correct"]) == 4

    partial = client.post("/quiz/grade", json={"id": quiz["id"], "edges": perfect[:2]}).json()
    assert partial["score"] == pytest.approx(0.5) and len(partial["missing"]) == 2


def test_quiz_errors(client: TestClient) -> None:
    assert client.post("/quiz/grade", json={"id": "nonsense", "edges": []}).status_code == 400
    assert client.post("/quiz/grade", json={"id": "Draco:easy:1", "edges": []}).status_code == 404
    assert client.get("/quiz/new", params={"constellation": "Draco"}).status_code == 404
    assert client.get("/quiz/new", params={"mode": "extreme"}).status_code == 422


# ----------------------------------------------------------------- live frames
def demo_frames(client: TestClient, count: int, constellation: str = "Orion") -> list[bytes]:
    return [client.get("/demo-sky/frame", params={"constellation": constellation, "index": k}).content
            for k in range(count)]


def post_frame(client: TestClient, data: bytes, session: str):  # noqa: ANN201
    return client.post("/frame", files={"image": ("frame.jpg", data, "image/jpeg")},
                       data={"session_id": session})


def test_demo_sky_info_and_frames(client: TestClient) -> None:
    info = client.get("/demo-sky").json()
    assert info["frame_count"] == 120 and "Orion" in info["constellations"]
    r = client.get("/demo-sky/frame", params={"index": 3})
    assert r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"


def test_frame_round_trip_identifies_orion_satellite_and_planet(client: TestClient) -> None:
    for data in demo_frames(client, 25):
        r = post_frame(client, data, "round-trip")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["width"] == 960 and body["meta"]["frame_index"] == 24
    assert [c["name"] for c in body["constellations"]] == ["Orion"]
    orion = body["constellations"][0]
    assert orion["confidence"] == 1.0 and len(orion["lines"]) == 9
    assert len(body["satellites"]) == 1
    sat = body["satellites"][0]
    assert sat["speed_unit"] == "deg/s" and sat["speed"] == pytest.approx(2.0, rel=0.1)
    assert sat["direction"] == "NW" and len(sat["trail"]) > 5
    assert len(body["anomalies"]) == 1
    assert body["plan"] is None


def test_frame_coordinates_are_in_the_sent_image_space(client: TestClient) -> None:
    frames = demo_frames(client, 6)
    for data in frames:
        small = post_frame(client, data, "scale-small").json()
    for data in frames:  # same frames at 2x size (downscaled internally)
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        big = cv2.resize(image, (1920, 1440), interpolation=cv2.INTER_CUBIC)
        large = post_frame(client, cv2.imencode(".jpg", big)[1].tobytes(), "scale-large").json()
    assert large["meta"]["width"] == 1920
    # Every star found in the 2x frame lies at twice its position in the 1x frame.
    small_xy = [(s["x"], s["y"]) for s in small["stars"]]
    assert len(large["stars"]) >= 7
    for star in large["stars"]:
        x, y = star["x"] / 2, star["y"] / 2
        assert min(abs(x - sx) + abs(y - sy) for sx, sy in small_xy) < 3.0


def test_sessions_are_independent(client: TestClient) -> None:
    frames = demo_frames(client, 3)
    for data in frames:
        a = post_frame(client, data, "session-a").json()
    b = post_frame(client, frames[0], "session-b").json()
    assert a["meta"]["frame_index"] == 2 and b["meta"]["frame_index"] == 0


def test_frame_rejects_bad_and_oversized_images(client: TestClient) -> None:
    assert post_frame(client, b"definitely not an image", "bad").status_code == 400
    assert post_frame(client, b"\xff" * (5 * 1024 * 1024), "big").status_code == 413
    missing = client.post("/frame", files={"image": ("f.jpg", b"x", "image/jpeg")})
    assert missing.status_code == 422  # session_id is required
