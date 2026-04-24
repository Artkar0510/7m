from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
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
    AuthenticatedUserResponse,
    LoginRequest,
    LogoutRequest,
    TokenPairResponse,
    YandexAuthorizeResponse,
    YandexOAuthExchangeRequest,
    YandexOAuthLoginResponse,
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
from utils.yandex_oauth import (
    YandexOAuthError,
    build_yandex_authorization_url,
    create_yandex_oauth_state,
    exchange_code_for_token,
    fetch_yandex_user_info,
    validate_yandex_oauth_state,
)

router = APIRouter()


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def _get_or_create_user_from_yandex(
    db: AsyncSession,
    code: str,
    redirect_uri: str | None = None,
) -> User:
    access_token = await exchange_code_for_token(code, redirect_uri=redirect_uri)
    yandex_user = await fetch_yandex_user_info(access_token)
    normalized_email = normalize_email(str(yandex_user.email))

    user = await db.scalar(
        select(User).where(
            or_(
                User.yandex_user_id == yandex_user.user_id,
                User.email == normalized_email,
            )
        )
    )

    if user is None:
        user = User(
            email=normalized_email,
            hashed_password=None,
            password_salt=None,
            yandex_user_id=yandex_user.user_id,
            is_active=True,
        )
        db.add(user)
    else:
        if user.yandex_user_id is None:
            user.yandex_user_id = yandex_user.user_id

    await db.commit()
    await db.refresh(user)
    await cache_user_entity(user)
    return user


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
            detail="Use Yandex login for this account",
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


@router.get("/oauth/yandex/authorize", response_model=YandexAuthorizeResponse)
async def get_yandex_authorization_url(redirect_uri: str | None = None) -> YandexAuthorizeResponse:
    state = await create_yandex_oauth_state()
    return YandexAuthorizeResponse(
        authorization_url=build_yandex_authorization_url(state=state, redirect_uri=redirect_uri),
        state=state,
    )


@router.post("/oauth/yandex/login", response_model=YandexOAuthLoginResponse)
async def login_with_yandex(
    payload: YandexOAuthExchangeRequest,
    db: AsyncSession = Depends(get_db),
) -> YandexOAuthLoginResponse:
    await validate_yandex_oauth_state(payload.state)

    try:
        user = await _get_or_create_user_from_yandex(
            db,
            code=payload.code,
            redirect_uri=payload.redirect_uri,
        )
    except YandexOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    access_token, access_expires_in = create_access_token(
        user_id=int(user.id),
        email=str(user.email),
    )
    refresh_token, refresh_expires_in = create_refresh_token(
        user_id=int(user.id),
        email=str(user.email),
    )

    return YandexOAuthLoginResponse(
        user=AuthenticatedUserResponse.model_validate(user),
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_in=access_expires_in,
        refresh_token_expires_in=refresh_expires_in,
    )


@router.get("/oauth/yandex/callback", response_model=YandexOAuthLoginResponse)
async def yandex_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> YandexOAuthLoginResponse:
    return await login_with_yandex(
        YandexOAuthExchangeRequest(code=code, state=state),
        db=db,
    )
