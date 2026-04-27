from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import HTTPException, status

from core.settings import settings
from db.redis import consume_yandex_oauth_state, store_yandex_oauth_state


class YandexOAuthError(Exception):
    """Raised when Yandex OAuth flow fails."""


class YandexUserInfo(dict):
    @property
    def user_id(self) -> str:
        raw_user_id = self.get("id")
        if isinstance(raw_user_id, str) and raw_user_id:
            return raw_user_id
        return ""

    @property
    def email(self) -> str | None:
        default_email = self.get("default_email")
        if isinstance(default_email, str) and default_email:
            return default_email

        emails = self.get("emails")
        if isinstance(emails, list) and emails:
            first_email = emails[0]
            if isinstance(first_email, str) and first_email:
                return first_email
        return None


def ensure_yandex_oauth_enabled() -> None:
    if not settings.yandex_oauth.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Yandex OAuth is disabled",
        )


def ensure_yandex_oauth_configured(require_secret: bool = False) -> None:
    if not settings.yandex_oauth.client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Yandex OAuth client_id is not configured",
        )

    if require_secret and not settings.yandex_oauth.client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Yandex OAuth client_secret is not configured",
        )


def build_yandex_authorization_url(state: str) -> str:
    ensure_yandex_oauth_enabled()
    ensure_yandex_oauth_configured()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.yandex_oauth.client_id,
            "scope": settings.yandex_oauth.scope,
            "state": state,
            "force_confirm": "no",
        }
    )
    return f"{settings.yandex_oauth.authorize_url}?{query}"


async def create_yandex_oauth_state() -> str:
    ensure_yandex_oauth_enabled()
    state = str(uuid4())
    stored = await store_yandex_oauth_state(state)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to store Yandex OAuth state",
        )
    return state


async def validate_yandex_oauth_state(state: str) -> None:
    ensure_yandex_oauth_enabled()
    consumed = await consume_yandex_oauth_state(state)
    if not consumed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired Yandex OAuth state",
        )


async def exchange_code_for_token(code: str) -> str:
    ensure_yandex_oauth_enabled()
    ensure_yandex_oauth_configured(require_secret=True) 
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.yandex_oauth.client_id,
        "client_secret": settings.yandex_oauth.client_secret
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(settings.yandex_oauth.token_url, data=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise YandexOAuthError("Failed to exchange Yandex OAuth code") from exc
    except httpx.HTTPError as exc:
        raise YandexOAuthError("Failed to reach Yandex OAuth") from exc
    access_token = response.json().get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise YandexOAuthError("Yandex OAuth response does not contain access token")
    return access_token


async def fetch_yandex_user_info(access_token: str) -> YandexUserInfo:
    ensure_yandex_oauth_enabled()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                settings.yandex_oauth.user_info_url,
                headers={"Authorization": f"OAuth {access_token}"},
                params={"format": "json"},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise YandexOAuthError("Failed to fetch Yandex user info") from exc
    except httpx.HTTPError as exc:
        raise YandexOAuthError("Failed to reach Yandex user info endpoint") from exc

    payload = response.json()
    user_info = YandexUserInfo(payload)
    if not user_info.user_id:
        raise YandexOAuthError("Yandex user info does not contain user id")
    if not user_info.email:
        raise YandexOAuthError("Yandex user info does not contain email")
    return user_info
