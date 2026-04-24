from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from core.settings import settings
from db.session import get_db
from main import app
from utils.yandex_oauth import YandexUserInfo

client = TestClient(app)


class FakeSession:
    def __init__(self, existing_user=None):
        self.existing_user = existing_user
        self.added_user = None

    async def scalar(self, *_args, **_kwargs):
        return self.existing_user

    def add(self, user):
        self.added_user = user

    async def commit(self):
        return None

    async def refresh(self, user):
        if getattr(user, "id", None) is None:
            user.id = 101


def test_yandex_authorize_returns_authorization_url() -> None:
    previous_enabled = settings.yandex_oauth.enabled
    previous_client_id = settings.yandex_oauth.client_id
    try:
        settings.yandex_oauth.enabled = True
        settings.yandex_oauth.client_id = "client-id"
        with patch(
            "api.v1.auth.create_yandex_oauth_state",
            AsyncMock(return_value="oauth-state"),
        ):
            response = client.get("/api/v1/auth/oauth/yandex/authorize")
    finally:
        settings.yandex_oauth.enabled = previous_enabled
        settings.yandex_oauth.client_id = previous_client_id

    assert response.status_code == 200
    assert "oauth.yandex.ru/authorize" in response.json()["authorization_url"]
    assert response.json()["state"] == "oauth-state"
    assert "state=oauth-state" in response.json()["authorization_url"]


def test_yandex_login_creates_user_and_returns_local_tokens() -> None:
    fake_session = FakeSession()

    async def override_get_db():
        yield fake_session

    previous_enabled = settings.yandex_oauth.enabled
    previous_client_secret = settings.yandex_oauth.client_secret
    settings.yandex_oauth.enabled = True
    settings.yandex_oauth.client_secret = "secret"
    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch(
            "api.v1.auth.validate_yandex_oauth_state",
            AsyncMock(return_value=None),
        ), patch(
            "api.v1.auth.exchange_code_for_token",
            AsyncMock(return_value="yandex-access-token"),
        ), patch(
            "api.v1.auth.fetch_yandex_user_info",
            AsyncMock(
                return_value=YandexUserInfo(
                    {
                    "id": "yandex-user-1",
                    "default_email": "social@example.com",
                    "emails": ["social@example.com"],
                    }
                )
            ),
        ):
            response = client.post(
                "/api/v1/auth/oauth/yandex/login",
                json={"code": "oauth-code", "state": "oauth-state"},
            )
    finally:
        settings.yandex_oauth.enabled = previous_enabled
        settings.yandex_oauth.client_secret = previous_client_secret
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "social@example.com"
    assert body["user"]["id"] == 101
    assert body["access_token"]
    assert body["refresh_token"]
    assert fake_session.added_user is not None
    assert fake_session.added_user.yandex_user_id == "yandex-user-1"


def test_yandex_login_links_existing_user_by_email() -> None:
    existing_user = SimpleNamespace(
        id=7,
        email="user@example.com",
        hashed_password="hash",
        password_salt="salt",
        yandex_user_id=None,
        is_active=True,
    )
    fake_session = FakeSession(existing_user=existing_user)

    async def override_get_db():
        yield fake_session

    previous_enabled = settings.yandex_oauth.enabled
    previous_client_secret = settings.yandex_oauth.client_secret
    settings.yandex_oauth.enabled = True
    settings.yandex_oauth.client_secret = "secret"
    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch(
            "api.v1.auth.validate_yandex_oauth_state",
            AsyncMock(return_value=None),
        ), patch(
            "api.v1.auth.exchange_code_for_token",
            AsyncMock(return_value="yandex-access-token"),
        ), patch(
            "api.v1.auth.fetch_yandex_user_info",
            AsyncMock(
                return_value=YandexUserInfo(
                    {
                    "id": "yandex-user-2",
                    "default_email": "user@example.com",
                    "emails": ["user@example.com"],
                    }
                )
            ),
        ):
            response = client.post(
                "/api/v1/auth/oauth/yandex/login",
                json={"code": "oauth-code", "state": "oauth-state"},
            )
    finally:
        settings.yandex_oauth.enabled = previous_enabled
        settings.yandex_oauth.client_secret = previous_client_secret
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["user"]["id"] == 7
    assert existing_user.yandex_user_id == "yandex-user-2"


def test_yandex_login_rejects_invalid_state() -> None:
    previous_enabled = settings.yandex_oauth.enabled
    settings.yandex_oauth.enabled = True

    try:
        response = client.post(
            "/api/v1/auth/oauth/yandex/login",
            json={"code": "oauth-code", "state": "invalid-state"},
        )
    finally:
        settings.yandex_oauth.enabled = previous_enabled

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired Yandex OAuth state"
