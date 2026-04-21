from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from core.settings import settings


class TokenValidationError(Exception):
    """Raised when a JWT token is invalid."""


def _build_token_payload(
    user_id: int,
    email: str,
    token_type: str,
    expires_delta: timedelta,
) -> tuple[dict[str, str | int], int]:
    now = datetime.now(UTC)
    expires_at = now + expires_delta
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": token_type,
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return payload, int(expires_delta.total_seconds())


def create_access_token(user_id: int, email: str) -> tuple[str, int]:
    payload, expires_in = _build_token_payload(
        user_id=user_id,
        email=email,
        token_type="access",
        expires_delta=timedelta(minutes=settings.jwt.access_token_expire_minutes),
    )
    token = jwt.encode(
        payload,
        settings.jwt.secret_key,
        algorithm=settings.jwt.algorithm,
    )
    return token, expires_in


def create_refresh_token(user_id: int, email: str) -> tuple[str, int]:
    payload, expires_in = _build_token_payload(
        user_id=user_id,
        email=email,
        token_type="refresh",
        expires_delta=timedelta(days=settings.jwt.refresh_token_expire_days),
    )
    token = jwt.encode(
        payload,
        settings.jwt.secret_key,
        algorithm=settings.jwt.algorithm,
    )
    return token, expires_in


def decode_token(token: str) -> dict[str, str | int]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt.secret_key,
            algorithms=[settings.jwt.algorithm],
        )
    except ExpiredSignatureError as exc:
        raise TokenValidationError("Token expired") from exc
    except InvalidTokenError as exc:
        raise TokenValidationError("Invalid token") from exc
    return payload


def decode_refresh_token(token: str) -> dict[str, str | int]:
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise TokenValidationError("Invalid token type")
    return payload


def decode_access_token(token: str) -> dict[str, str | int]:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise TokenValidationError("Invalid token type")
    return payload
