from urllib.parse import urlencode
from uuid import uuid4
import httpx
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.settings import settings
from db.models import User
from db.redis import store_yandex_oauth_state, consume_yandex_oauth_state
from utils.cache import cache_user_entity
from .base import OAuthProvider


class YandexOAuthError(Exception):
    pass


class YandexOAuthProvider(OAuthProvider):
    
    @property
    def provider_name(self) -> str:
        return "yandex"
    
    async def build_authorization_url(self, state: str) -> str:
        if not settings.yandex_oauth.enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Yandex OAuth is disabled"
            )
        
        query = urlencode({
            "response_type": "code",
            "client_id": settings.yandex_oauth.client_id,
            "redirect_uri": settings.yandex_oauth.redirect_uri,
            "scope": settings.yandex_oauth.scope,
            "state": state,
            "force_confirm": "no",
        })
        return f"{settings.yandex_oauth.authorize_url}?{query}"
    
    async def exchange_code(self, code: str) -> str:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.yandex_oauth.client_id,
            "client_secret": settings.yandex_oauth.client_secret,
            "redirect_uri": settings.yandex_oauth.redirect_uri,
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    settings.yandex_oauth.token_url,
                    data=payload
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise YandexOAuthError("Failed to exchange code") from exc
        
        access_token = response.json().get("access_token")
        if not access_token:
            raise YandexOAuthError("No access token in response")
        return access_token
    
    async def fetch_user_info(self, access_token: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    settings.yandex_oauth.user_info_url,
                    headers={"Authorization": f"OAuth {access_token}"},
                    params={"format": "json"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise YandexOAuthError("Failed to fetch user info") from exc
        
        payload = response.json()
        return {
            "id": str(payload.get("id")),
            "email": payload.get("default_email"),
            "name": payload.get("real_name", ""),
        }
    
    async def get_or_create_user(self, db: AsyncSession, code: str) -> User:
        access_token = await self.exchange_code(code)
        user_info = await self.fetch_user_info(access_token)
        
        normalized_email = user_info["email"].strip().lower()
        
        user = await db.scalar(
            select(User).where(
                or_(
                    User.yandex_user_id == user_info["id"],
                    User.email == normalized_email,
                )
            )
        )
        
        if user is None:
            user = User(
                email=normalized_email,
                hashed_password=None,
                password_salt=None,
                yandex_user_id=user_info["id"],
                is_active=True,
            )
            db.add(user)
        else:
            if user.yandex_user_id is None:
                user.yandex_user_id = user_info["id"]
        
        await db.commit()
        await db.refresh(user)
        await cache_user_entity(user)
        return user
    
    async def create_state(self) -> str:
        state = str(uuid4())
        stored = await store_yandex_oauth_state(state)
        if not stored:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to store OAuth state"
            )
        return state
    
    async def validate_state(self, state: str) -> None:
        consumed = await consume_yandex_oauth_state(state)
        if not consumed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OAuth state"
            )