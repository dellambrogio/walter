from fastapi.testclient import TestClient

from walter.main import app


def test_health_reports_postgis() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgis"]
