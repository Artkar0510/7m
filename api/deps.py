from fastapi import Header, HTTPException, status

from core.settings import settings


def verify_internal_service(x_service_token: str = Header(...)) -> str:
    if x_service_token != settings.internal_auth.service_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid service credentials",
        )
    return x_service_token
