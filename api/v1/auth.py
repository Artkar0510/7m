import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import verify_internal_service
from core.rate_limit import limiter
from core.settings import settings
from db.models import User
from db.redis import blacklist_refresh_token, is_refresh_token_blacklisted
from db.session import get_db
from schemas.auth import (
    AccessTokenIntrospectRequest,
    AccessTokenIntrospectResponse,
    LoginRequest,
    LogoutRequest,
    TokenPairResponse,
)
from schemas.user import UserCreate, UserResponse
from utils.cache import cache_user_entity, get_user_from_cache
from utils.jwt import (
    TokenValidationError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)
from utils.security import hash_password, verify_password
from utils.oauth import get_provider, get_all_providers

logger = logging.getLogger(__name__)

router = APIRouter()


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def _oauth_login_logic(
    provider_name: str,
    code: str,
    state: str,
    db: AsyncSession,
) -> TokenPairResponse:
    provider = get_provider(provider_name)
    await provider.validate_state(state)
    
    try:
        user = await provider.get_or_create_user(db, code)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{provider_name} OAuth failed: {str(exc)}",
        ) from exc
    
    access_token, access_expires_in = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
    )
    refresh_token, refresh_expires_in = create_refresh_token(
        user_id=int(user.id),
        email=str(user.email),
    )
    
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_in=access_expires_in,
        refresh_token_expires_in=refresh_expires_in,
    )


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.auth.register_rate_limit)
async def register_user(
    request: Request,
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    import asyncio
    import random
    
    normalized_email = normalize_email(payload.email)
    existing_user = await db.scalar(select(User).where(User.email == normalized_email))
    
    if existing_user:
        await asyncio.sleep(random.uniform(0.05, 0.15))
        fake_user = User(
            email=normalized_email,
            hashed_password="",
            password_salt="",
        )
        return UserResponse.model_validate(fake_user)

    hashed_password, password_salt = hash_password(payload.password)
    user = User(
        email=normalized_email,
        hashed_password=hashed_password,
        password_salt=password_salt,
        country_code=payload.country_code,
        region_code=payload.region_code,
        birth_date=payload.birth_date,
        last_device_type=payload.last_device_type,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await cache_user_entity(user)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenPairResponse)
@limiter.limit(settings.auth.login_rate_limit)
async def login_user(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    normalized_email = normalize_email(payload.email)
    user = await db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if user.hashed_password is None or user.password_salt is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Use OAuth login for this account",
        )

    if not verify_password(
        payload.password,
        str(user.hashed_password),
        str(user.password_salt),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    await cache_user_entity(user)

    access_token, access_expires_in = create_access_token(
        user_id=int(user.id),
        email=normalized_email,
    )
    refresh_token, refresh_expires_in = create_refresh_token(
        user_id=int(user.id),
        email=normalized_email,
    )
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_in=access_expires_in,
        refresh_token_expires_in=refresh_expires_in,
    )


@router.post("/logout")
async def logout_user(payload: LogoutRequest) -> dict[str, str]:
    try:
        refresh_payload = decode_refresh_token(payload.refresh_token)
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    token_jti = str(refresh_payload["jti"])
    
    try:
        if await is_refresh_token_blacklisted(token_jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token already revoked",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Unexpected error checking blacklist: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        ) from exc

    expires_at = datetime.fromtimestamp(int(refresh_payload["exp"]), UTC)
    ttl_seconds = max(int((expires_at - datetime.now(UTC)).total_seconds()), 1)
    await blacklist_refresh_token(token_jti, ttl_seconds)
    return {"detail": "Successfully logged out"}


@router.post("/introspect", response_model=AccessTokenIntrospectResponse)
async def introspect_access_token(
    payload: AccessTokenIntrospectRequest,
    _: str = Depends(verify_internal_service),
    db: AsyncSession = Depends(get_db),
) -> AccessTokenIntrospectResponse:
    try:
        access_payload = decode_access_token(payload.access_token)
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    user_id = int(access_payload["sub"])
    email = str(access_payload["email"])
    token_type = str(access_payload["type"])
    expires_at = int(access_payload["exp"])

    cached_user = await get_user_from_cache(email)
    
    if cached_user and int(cached_user["id"]) == user_id and cached_user.get("is_active", False):
        return AccessTokenIntrospectResponse(
            active=True,
            user_id=user_id,
            email=email,
            token_type=token_type,
            expires_at=expires_at,
        )

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        return AccessTokenIntrospectResponse(
            active=False,
            user_id=user_id,
            email=email,
            token_type=token_type,
            expires_at=expires_at,
        )

    await cache_user_entity(user)

    return AccessTokenIntrospectResponse(
        active=True,
        user_id=user_id,
        email=email,
        token_type=token_type,
        expires_at=expires_at,
    )


@router.get("/oauth/{provider_name}/authorize")
async def oauth_authorize(provider_name: str) -> dict:
    provider = get_provider(provider_name)
    state = await provider.create_state()
    authorization_url = await provider.build_authorization_url(state)
    return {"authorization_url": authorization_url, "state": state}


@router.post("/oauth/{provider_name}/login")
async def oauth_login(
    provider_name: str,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    return await _oauth_login_logic(provider_name, code, state, db)


@router.get("/oauth/{provider_name}/callback")
async def oauth_callback(
    provider_name: str,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    return await _oauth_login_logic(provider_name, code, state, db)


@router.get("/oauth/providers")
async def list_oauth_providers() -> dict:
    providers = get_all_providers()
    return {"providers": list(providers.keys())}