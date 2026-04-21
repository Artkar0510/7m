from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import verify_internal_service
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
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    normalized_email = normalize_email(payload.email)
    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists",
        )

    hashed_password, password_salt = hash_password(payload.password)
    user = User(
        email=normalized_email,
        hashed_password=hashed_password,
        password_salt=password_salt,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    cache_user_entity(user)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenPairResponse)
def login_user(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    normalized_email = normalize_email(payload.email)
    cached_user = get_user_from_cache(normalized_email)
    if cached_user is None:
        user = db.query(User).filter(User.email == normalized_email).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        cached_user = cache_user_entity(user)

    if not verify_password(
        payload.password,
        str(cached_user["hashed_password"]),
        str(cached_user["password_salt"]),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    access_token, access_expires_in = create_access_token(
        user_id=int(cached_user["id"]),
        email=normalized_email,
    )
    refresh_token, refresh_expires_in = create_refresh_token(
        user_id=int(cached_user["id"]),
        email=normalized_email,
    )
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_in=access_expires_in,
        refresh_token_expires_in=refresh_expires_in,
    )


@router.post("/logout")
def logout_user(payload: LogoutRequest) -> dict[str, str]:
    try:
        refresh_payload = decode_refresh_token(payload.refresh_token)
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    token_jti = str(refresh_payload["jti"])
    if is_refresh_token_blacklisted(token_jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token already revoked",
        )

    expires_at = datetime.fromtimestamp(int(refresh_payload["exp"]), UTC)
    ttl_seconds = max(int((expires_at - datetime.now(UTC)).total_seconds()), 1)
    blacklist_refresh_token(token_jti, ttl_seconds)
    return {"detail": "Successfully logged out"}


@router.post("/introspect", response_model=AccessTokenIntrospectResponse)
def introspect_access_token(
    payload: AccessTokenIntrospectRequest,
    _: str = Depends(verify_internal_service),
) -> AccessTokenIntrospectResponse:
    try:
        access_payload = decode_access_token(payload.access_token)
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    return AccessTokenIntrospectResponse(
        active=True,
        user_id=int(access_payload["sub"]),
        email=str(access_payload["email"]),
        token_type=str(access_payload["type"]),
        expires_at=int(access_payload["exp"]),
    )
