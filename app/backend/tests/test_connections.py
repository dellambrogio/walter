import datetime as dt

import pytest
from fastapi.testclient import TestClient

from walter.connections import Stop, finish_time, leg, sbb_link
from walter.main import app
from walter.stages import Trip


def section(journey: dict | None, start: str = "Thun", end: str = "Interlaken Ost") -> dict:
    return {
        "journey": journey,
        "departure": {"station": {"name": start}, "departure": "2026-10-31T09:02:00+0100", "delay": 3},
        "arrival": {"station": {"name": end}, "arrival": "2026-10-31T09:58:00+0100"},
    }


def test_legs_use_the_clients_modes_and_lines() -> None:
    bus = leg(section({"category": "B", "number": "21"}))
    assert bus | {"delay": 3} == bus and (bus["mode"], bus["line"]) == ("BUS", "21")
    assert (bus["depart"], bus["arrive"]) == ("09:02", "09:58")  # Swiss time, winter
    assert leg(section({"category": "IC", "number": "001303"}))["line"] == "IC"  # train number: not shown
    assert leg(section({"category": "R", "number": "000061"}))["line"] == "R 61"
    assert leg(section({"category": "PB", "number": ""}))["mode"] == "CABLE_CAR"
    assert leg(section({"category": "EV", "number": "3"}))["line"] == "Rail replacement bus"
    assert leg(section(None))["mode"] == "WALK"


def test_sbb_link_prefills_the_search() -> None:
    url = sbb_link("Zürich HB", "Grindelwald", dt.date(2026, 10, 31), "07:38")
    assert url.endswith(
        "von=Z%C3%BCrich+HB&nach=Grindelwald&datum=31.10.2026&zeit=07%3A38&an=false&suche=true"
    )


def test_connections_there_and_back() -> None:
    client = TestClient(app)
    if client.get("/api/origin").json() is None:
        pytest.skip("no start station configured")
    if client.get("/api/routes/1").status_code == 404:
        pytest.skip("SchweizMobil data not loaded")
    saturday = dt.date.today() + dt.timedelta(days=(5 - dt.date.today().weekday()) % 7 or 7)
    response = client.get(f"/api/stages/1.10/connections?date={saturday}")  # Meiringen -> Grindelwald
    if response.status_code == 502:
        pytest.skip("transport.opendata.ch not reachable")
    body = response.json()
    assert "Meiringen" in body["start_stop"]["name"] and "Grindelwald" in body["end_stop"]["name"]
    assert body["out"] and body["back"]
    assert body["back"][0]["depart"] > body["out"][0]["arrive"]
    assert body["sbb_out"].startswith("https://www.sbb.ch/")
    later = client.get(f"/api/stages/1.10/connections?date={saturday}&back_after=20:00").json()
    assert later["back_after"] == "20:00" and later["back"][0]["depart"][11:16] >= "20:00"
    assert all(t["depart"].startswith(saturday.isoformat()) for t in later["back"])  # nothing after midnight


def test_finish_time_adds_walks_and_the_hiking_time() -> None:
    trip = Trip(
        depart=dt.datetime(2026, 10, 31, 8, 10),
        arrive=dt.datetime(2026, 10, 31, 10, 20),
        transfers=1,
        legs=[],
    )
    start, end = (
        Stop(id="1", name="a", distance_m=300, walk_min=5),
        Stop(id="2", name="b", distance_m=50, walk_min=1),
    )
    assert finish_time([trip], 8.0, start, end) == "18:26"
    assert finish_time([trip], 8.0, start, end, pause_min=45) == "19:11"
    assert finish_time([], 8.0, start, end) == "15:00"


def test_unknown_stage_is_404() -> None:
    assert TestClient(app).get("/api/stages/nope/connections?date=2026-10-31").status_code == 404
