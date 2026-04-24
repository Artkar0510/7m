from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_healthcheck() -> None:
    response = client.get("/api/v1/auth/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthcheck_returns_generated_request_id() -> None:
    response = client.get("/api/v1/auth/health")

    assert response.status_code == 200
    assert response.headers["X-Request-Id"]


def test_healthcheck_reuses_incoming_request_id() -> None:
    response = client.get(
        "/api/v1/auth/health",
        headers={"X-Request-Id": "request-id-from-client"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "request-id-from-client"
