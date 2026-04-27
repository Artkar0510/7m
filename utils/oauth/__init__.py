from .registry import register_provider, get_provider, get_all_providers
from .yandex import YandexOAuthProvider
from .google import GoogleOAuthProvider

register_provider(YandexOAuthProvider())
register_provider(GoogleOAuthProvider())

__all__ = ["get_provider", "get_all_providers"]