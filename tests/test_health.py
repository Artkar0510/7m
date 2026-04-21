from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_healthcheck() -> None:
    response = client.get("/api/v1/auth/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
