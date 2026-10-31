"""Needs the lifts loaded (`just load-lifts`)."""

import pytest
from fastapi.testclient import TestClient

from walter.main import app

client = TestClient(app)


def test_lifts_have_heights_and_kinds() -> None:
    features = client.get("/api/lifts").json()["features"]
    if not features:
        pytest.skip("lifts not loaded")
    assert {f["properties"]["kind"] for f in features} == {"cable_car", "gondola", "chairlift", "lift"}
    for f in features:
        coords = f["geometry"]["coordinates"]
        assert all(len(c) == 3 and 5.9 < c[0] < 10.6 and 45.8 < c[1] < 47.9 for c in coords)
        p = f["properties"]
        assert 190 < p["bottom_m"] <= p["top_m"] < 4000 and p["length_m"] >= 0  # 0: vertical lifts
