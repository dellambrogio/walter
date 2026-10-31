"""My hikes are personal: served by the API, never as public tiles."""

import httpx
import pytest
from fastapi.testclient import TestClient

from walter.main import app

client = TestClient(app)
TILES = "http://tiles:3000"  # Martin, by its docker compose service name


def test_hikes_are_geojson_lines() -> None:
    body = client.get("/api/me/hikes").json()
    assert body["type"] == "FeatureCollection"
    if not body["features"]:
        pytest.skip("no hikes loaded (`just load-hikes`)")
    first = body["features"][0]
    assert first["geometry"]["type"] == "LineString"
    lon, lat = first["geometry"]["coordinates"][0]
    assert -180 <= lon <= 180 and -90 <= lat <= 90
    assert {"id", "date", "certain", "km", "hours", "gain_m", "top_m"} == first["properties"].keys()


def test_tile_server_publishes_only_public_data() -> None:
    try:
        catalog = httpx.get(f"{TILES}/catalog", timeout=5).json()
    except httpx.HTTPError:
        pytest.skip("tile server not reachable")
    assert set(catalog["tiles"]) == {"sm_stage"}
