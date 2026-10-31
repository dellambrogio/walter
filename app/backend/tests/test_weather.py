import datetime as dt

import pytest
from fastapi.testclient import TestClient

from walter.main import app
from walter.weather import at_height, daily, daytime_min, rows, sum_hours

POINT = ("2", "3818")
OTHER = ("1", "3818")  # same id, other kind: a different point


def csv(param: str, *lines: str) -> str:
    return "\r\n".join([f"point_id;point_type_id;Date;{param}", *lines])


def test_rows_keep_only_wanted_points_and_skip_missing_values() -> None:
    content = csv("rka150p0", "3818;2;202610310000;1.5", "3818;1;202610310000;9.9", "3818;2;202611010000;")
    assert list(rows(content, {POINT})) == [(POINT, "202610310000", 1.5)]
    assert list(daily(rows(content, {POINT}))) == [(POINT, dt.date(2026, 10, 31), 1.5)]


def hourly(param: str, start: str, values: list[int]) -> str:
    """One value per hour from `start` (UTC) at POINT"""
    first = dt.datetime.strptime(start, "%Y%m%d%H%M")
    stamps = (first + dt.timedelta(hours=i) for i in range(len(values)))
    return csv(param, *(f"3818;2;{t:%Y%m%d%H%M};{v}" for t, v in zip(stamps, values, strict=True)))


def test_sunshine_is_summed_per_whole_local_day() -> None:
    # 23:00 UTC on 30 Oct is midnight in Zurich (winter time): 24 hours of the 31st, then 2 of 1 Nov
    content = hourly("sre000h0", "202610302300", [60] * 6 + [30] * 18 + [60, 60])
    assert list(sum_hours(rows(content, {POINT, OTHER}))) == [(POINT, dt.date(2026, 10, 31), 15.0)]


def test_freezing_level_is_the_daytime_minimum() -> None:
    # From midnight local: 07:00 (before DAYTIME) is lowest, but only 08:00-17:00 count
    levels = [3000] * 7 + [900] + [2400] * 4 + [2100] + [2400] * 11
    content = hourly("zprfr0hs", "202610302300", levels)
    assert list(daytime_min(rows(content, {POINT}))) == [(POINT, dt.date(2026, 10, 31), 2100)]
    assert list(daytime_min(rows(hourly("zprfr0hs", "202610302300", levels[:12]), {POINT}))) == []


def test_temperature_follows_the_lapse_rate() -> None:
    assert at_height(10.0, point_m=1000, height_m=2000) == 3.5
    assert at_height(None, point_m=1000, height_m=2000) is None


def test_every_stage_has_a_forecast_point() -> None:
    client = TestClient(app)
    if client.get("/api/routes/1").status_code == 404:
        pytest.skip("SchweizMobil data not loaded")
    response = client.get("/api/weather")
    if response.status_code == 502:
        pytest.skip("MeteoSwiss not reachable")
    body = response.json()
    assert len(body["stages"]) == 976 and 5 <= len(body["dates"]) <= 10
    grindelwald = body["stages"]["1.10"]  # Meiringen -> Grindelwald over Grosse Scheidegg (1,962 m)
    assert grindelwald["top_m"] > 1900 and len(grindelwald["days"]) == len(body["dates"])
    day = next(d for d in grindelwald["days"] if d)
    assert 0 <= day["sun_h"] <= 16 and day["precip_mm"] >= 0 and day["tmin"] <= day["tmax"]


def test_points_carry_the_forecast_at_their_own_height() -> None:
    client = TestClient(app)
    if client.get("/api/routes/1").status_code == 404:
        pytest.skip("SchweizMobil data not loaded")
    response = client.get("/api/weather/points")
    if response.status_code == 502:
        pytest.skip("MeteoSwiss not reachable")
    body = response.json()
    assert 100 < len(body["points"]) <= 976  # one per stage at most, shared by neighbours
    scheidegg = next(p for p in body["points"] if p["name"] == "Grosse Scheidegg")
    assert scheidegg["height_m"] == 1962 and 8.0 < scheidegg["lon"] < 8.2 and 46.6 < scheidegg["lat"] < 46.7
    assert len(scheidegg["days"]) == len(body["dates"])
