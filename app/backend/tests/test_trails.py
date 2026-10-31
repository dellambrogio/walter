"""Needs the trail network loaded (`just load-trails`)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from walter.main import app
from walter.trails import hiking_hours

client = TestClient(app)
# Kleine Scheidegg -> Grindelwald, ~10 km and ~1100 m down
WAYPOINTS = [[7.9614, 46.5853], [8.0420, 46.6243]]


@pytest.fixture(autouse=True)
def require_data() -> None:
    if client.post("/api/trails/route", json={"waypoints": WAYPOINTS}).status_code == 422:
        pytest.skip("trail network not loaded")


def test_hiking_hours_din_33466() -> None:
    assert hiking_hours(8, 0, 0) == 2  # flat: 4 km/h
    assert hiking_hours(4, 600, 0) == 2.5  # climb 2 h dominates, plus half of 1 h on the flat


def test_route_follows_trails_downhill() -> None:
    body = client.post("/api/trails/route", json={"waypoints": WAYPOINTS}).json()
    assert body["geometry"]["type"] == "LineString"
    lon, lat, ele = body["geometry"]["coordinates"][0]
    assert body["waypoints"][0] == pytest.approx([lon, lat], abs=1e-5)  # starts at the snapped first point
    assert 2000 < ele < 2100  # Kleine Scheidegg, 2061 m
    assert 9 < body["km"] < 13
    assert body["descent"] > 900 > body["ascent"]
    assert len(body["profile"]["elevations"]) == pytest.approx(body["km"] * 1000 / 25, rel=0.05)


def test_point_far_from_trails_is_rejected() -> None:
    response = client.post("/api/trails/route", json={"waypoints": [[2.0, 47.0], WAYPOINTS[1]]})
    assert response.status_code == 422


def test_planned_hike_lifecycle() -> None:
    created = client.post("/api/me/planned-hikes", json={"name": "Test hike", "waypoints": WAYPOINTS}).json()
    try:
        assert created["name"] == "Test hike" and created["km"] > 9
        listed = client.get("/api/me/planned-hikes").json()["features"]
        assert created["id"] in [f["properties"]["id"] for f in listed]
        back = list(reversed(WAYPOINTS))
        updated = client.put(f"/api/me/planned-hikes/{created['id']}", json={"name": "Up", "waypoints": back})
        assert updated.json()["ascent"] > 900
    finally:
        assert client.delete(f"/api/me/planned-hikes/{created['id']}").status_code == 204
    assert client.get(f"/api/me/planned-hikes/{created['id']}").status_code == 404


def test_day_plan_for_a_drawn_line() -> None:
    route = client.post("/api/trails/route", json={"waypoints": WAYPOINTS}).json()
    weather = client.post("/api/weather/line", json={"coordinates": route["geometry"]["coordinates"]})
    if weather.status_code != 502:  # MeteoSwiss not reachable: skip this part
        body = weather.json()
        assert len(body["weather"]["days"]) == len(body["dates"])
        assert body["weather"]["top_m"] > 2000 > body["weather"]["low_m"]  # Kleine Scheidegg -> Grindelwald
    assert client.post("/api/weather/line", json={"coordinates": WAYPOINTS}).status_code == 422  # no heights
    if client.get("/api/origin").json() is None:
        return  # no start station configured
    saturday = dt.date.today() + dt.timedelta(days=(5 - dt.date.today().weekday()) % 7 or 7)
    (start, end) = (",".join(map(str, route["geometry"]["coordinates"][i][:2])) for i in (0, -1))
    response = client.get(
        f"/api/connections?start={start}&end={end}&time_h={route['time_h']}&date={saturday}"
    )
    if response.status_code == 502:
        return  # transport.opendata.ch not reachable
    body = response.json()
    assert "Scheidegg" in body["start_stop"]["name"] and "Grindelwald" in body["end_stop"]["name"]
    assert body["start_stop"]["lon"] == pytest.approx(7.96, abs=0.02)
    assert body["out"] and body["back"]
    assert client.get(f"/api/connections?start=x&end={end}&time_h=3&date={saturday}").status_code == 422
