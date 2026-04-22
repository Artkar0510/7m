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

router = APIRouter()


def normalize_email(email: str) -> str:
    return email.strip().lower()


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
    normalized_email = normalize_email(payload.email)
    existing_user = await db.scalar(select(User).where(User.email == normalized_email))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
        )

    hashed_password, password_salt = hash_password(payload.password)
    user = User(
        email=normalized_email,
        hashed_password=hashed_password,
        password_salt=password_salt,
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
    if await is_refresh_token_blacklisted(token_jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token already revoked",
        )

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
    cache_matches_user = (
        cached_user is not None
        and int(cached_user["id"]) == user_id
        and bool(cached_user["is_active"])
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

    if not cache_matches_user:
        await cache_user_entity(user)

    return AccessTokenIntrospectResponse(
        active=True,
        user_id=user_id,
        email=email,
        token_type=token_type,
        expires_at=expires_at,
    )
