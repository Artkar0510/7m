import hmac

from fastapi import Header, HTTPException, status

from core.settings import settings


def verify_internal_service(x_service_token: str = Header(...)) -> str:
    if not hmac.compare_digest(
        x_service_token.encode(),
        settings.internal_auth.service_token.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid service credentials",
        )
    return x_service_token