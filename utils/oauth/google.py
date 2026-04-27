from urllib.parse import urlencode
from uuid import uuid4
import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.settings import settings
from db.models import User
from db.redis import store_oauth_state, consume_oauth_state
from utils.cache import cache_user_entity
from .base import OAuthProvider


class GoogleOAuthError(Exception):
    pass


class GoogleOAuthProvider(OAuthProvider):
    
    @property
    def provider_name(self) -> str:
        return "google"
    
    async def build_authorization_url(self, state: str) -> str:
        query = urlencode({
            "response_type": "code",
            "client_id": settings.google_oauth.client_id,
            "redirect_uri": settings.google_oauth.redirect_uri,
            "scope": settings.google_oauth.scope,
            "state": state,
        })
        return f"{settings.google_oauth.authorize_url}?{query}"
    
    async def exchange_code(self, code: str) -> str:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.google_oauth.client_id,
            "client_secret": settings.google_oauth.client_secret,
            "redirect_uri": settings.google_oauth.redirect_uri,
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.google_oauth.token_url,
                data=payload
            )
            response.raise_for_status()
        
        return response.json()["access_token"]
    
    async def fetch_user_info(self, access_token: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                settings.google_oauth.user_info_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
        
        payload = response.json()
        return {
            "id": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name", ""),
        }
    
    async def get_or_create_user(self, db: AsyncSession, code: str) -> User:
        access_token = await self.exchange_code(code)
        user_info = await self.fetch_user_info(access_token)
        
        normalized_email = user_info["email"].strip().lower()
        
        user = await db.scalar(
            select(User).where(
                or_(
                    User.google_user_id == user_info["id"],
                    User.email == normalized_email,
                )
            )
        )
        
        if user is None:
            user = User(
                email=normalized_email,
                hashed_password=None,
                password_salt=None,
                google_user_id=user_info["id"],
                is_active=True,
            )
            db.add(user)
        else:
            if user.google_user_id is None:
                user.google_user_id = user_info["id"]
        
        await db.commit()
        await db.refresh(user)
        await cache_user_entity(user)
        return user
    
    async def create_state(self) -> str:
        state = str(uuid4())
        await store_oauth_state("google", state)
        return state
    
    async def validate_state(self, state: str) -> None:
        if not await consume_oauth_state("google", state):
            raise GoogleOAuthError("Invalid or expired state")