from typing import Dict
from fastapi import HTTPException, status
from .base import OAuthProvider


_providers: Dict[str, OAuthProvider] = {}


def register_provider(provider: OAuthProvider) -> None:
    _providers[provider.provider_name] = provider


def get_provider(provider_name: str) -> OAuthProvider:
    if provider_name not in _providers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OAuth provider '{provider_name}' not found"
        )
    return _providers[provider_name]


def get_all_providers() -> Dict[str, OAuthProvider]:
    return _providers