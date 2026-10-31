"""Needs SchweizMobil data loaded (`just load-schweizmobil`)."""

import pytest
from fastapi.testclient import TestClient

from walter.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def require_data() -> None:
    if client.get("/api/routes/1").status_code == 404:
        pytest.skip("SchweizMobil data not loaded")


def test_stage_detail() -> None:
    body = client.get("/api/stages/1.02").json()
    assert body["route"] == {
        "nr": "1",
        "name": "Via Alpina",
        "level": "national",
        "stage_count": 20,
        "url": "https://schweizmobil.ch/de/wanderland/route-1",
    }
    assert body["url"] == "https://schweizmobil.ch/de/wanderland/route-1/etappe-2"
    assert body["prev"]["id"] == "1.01" and body["next"]["id"] == "1.03"
    west, south, east, north = body["bbox"]
    assert 5.9 < west < east < 10.6 and 45.8 < south < north < 47.9
    # one sample every 25 m plus the end point
    assert len(body["profile"]["elevations"]) == pytest.approx(body["km"] * 1000 / 25, rel=0.15)


def test_single_stage_route_links_to_route_page() -> None:
    body = client.get("/api/stages/257.00").json()
    assert body["prev"] is None and body["next"] is None
    assert body["url"] == "https://schweizmobil.ch/de/wanderland/route-257"


def test_route_lists_stages_in_order() -> None:
    body = client.get("/api/routes/1").json()
    assert [s["nr"] for s in body["stages"]] == list(range(1, 21))


def test_unknown_stage_is_404() -> None:
    assert client.get("/api/stages/nope").status_code == 404


def test_stage_list_has_filter_fields() -> None:
    stages = client.get("/api/stages").json()
    assert len(stages) == 976
    first = next(s for s in stages if s["id"] == "1.01")
    assert first["level"] == "national" and first["route_name"] == "Via Alpina"
    assert {"km", "time_h", "ascent", "fitness", "technique"} <= first.keys()
    west, south, east, north = first["bbox"]
    assert 5.9 < west < east < 10.6 and 45.8 < south < north < 47.9


def test_station_distance_when_a_station_is_configured() -> None:
    origin = client.get("/api/origin").json()
    stages = client.get("/api/stages").json()
    if origin is None:
        assert all(s["station_km"] is None for s in stages)
    else:
        assert origin["name"] and 5.9 < origin["lon"] < 10.6 and 45.8 < origin["lat"] < 47.9
        assert all(0 <= s["station_km"] < 400 for s in stages)


def test_travel_times_in_swiss_local_time() -> None:
    travel = client.get("/api/stages/1.05").json()["travel"]
    if not travel:
        pytest.skip("travel times not computed (`just travel-times`)")
    day = travel[0]
    assert day["day"] in ("sat", "sun")
    assert day["out"]["depart"].endswith("+02:00")  # summer reference weekend
    assert day["out"]["legs"][0]["from"] == day["back"]["legs"][-1]["to"]  # back to where we started
    assert day["day_h"] >= day["travel_h"] > 0
    summary = next(s for s in client.get("/api/stages").json() if s["id"] == "1.05")
    assert summary["travel_h"] == min(d["travel_h"] for d in travel if d["travel_h"] is not None)
