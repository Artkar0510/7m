from fastapi.testclient import TestClient

from core.settings import settings
from db.session import get_db
from main import app
from utils.jwt import create_access_token

client = TestClient(app)


def test_introspect_access_token_for_internal_services() -> None:
    class ActiveUserSession:
        async def scalar(self, *_args, **_kwargs):
            class UserStub:
                id = 7
                email = "user@example.com"
                is_active = True

            return UserStub()

    async def override_get_db():
        yield ActiveUserSession()

    app.dependency_overrides[get_db] = override_get_db
    access_token, _ = create_access_token(user_id=7, email="user@example.com")
    try:
        response = client.post(
            "/api/v1/auth/introspect",
            json={"access_token": access_token},
            headers={"X-Service-Token": settings.internal_auth.service_token},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["active"] is True
    assert response.json()["user_id"] == 7
    assert response.json()["email"] == "user@example.com"


def test_introspect_returns_inactive_for_missing_user() -> None:
    class MissingUserSession:
        async def scalar(self, *_args, **_kwargs):
            return None

    async def override_get_db():
        yield MissingUserSession()

    app.dependency_overrides[get_db] = override_get_db
    access_token, _ = create_access_token(user_id=7, email="user@example.com")
    try:
        response = client.post(
            "/api/v1/auth/introspect",
            json={"access_token": access_token},
            headers={"X-Service-Token": settings.internal_auth.service_token},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["active"] is False


def test_introspect_rejects_invalid_service_token() -> None:
    class MissingUserSession:
        async def scalar(self, *_args, **_kwargs):
            return None

    async def override_get_db():
        yield MissingUserSession()

    app.dependency_overrides[get_db] = override_get_db
    access_token, _ = create_access_token(user_id=7, email="user@example.com")
    try:
        response = client.post(
            "/api/v1/auth/introspect",
            json={"access_token": access_token},
            headers={"X-Service-Token": "wrong-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
