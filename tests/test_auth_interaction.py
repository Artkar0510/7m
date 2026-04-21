from fastapi.testclient import TestClient

from core.settings import settings
from main import app
from utils.jwt import create_access_token

client = TestClient(app)


def test_introspect_access_token_for_internal_services() -> None:
    access_token, _ = create_access_token(user_id=7, email="user@example.com")

    response = client.post(
        "/api/v1/auth/introspect",
        json={"access_token": access_token},
        headers={"X-Service-Token": settings.internal_auth.service_token},
    )

    assert response.status_code == 200
    assert response.json()["active"] is True
    assert response.json()["user_id"] == 7
    assert response.json()["email"] == "user@example.com"


def test_introspect_rejects_invalid_service_token() -> None:
    access_token, _ = create_access_token(user_id=7, email="user@example.com")

    response = client.post(
        "/api/v1/auth/introspect",
        json={"access_token": access_token},
        headers={"X-Service-Token": "wrong-token"},
    )

    assert response.status_code == 403
