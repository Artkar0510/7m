from db.models import User
from db.redis import cache_user, get_cached_user


def build_user_cache_payload(user: User) -> dict[str, str | int | bool]:
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
    }


async def cache_user_entity(user: User) -> dict[str, str | int | bool]:
    payload = build_user_cache_payload(user)
    await cache_user(payload)
    return payload


async def get_user_from_cache(email: str) -> dict[str, str | int | bool] | None:
    return await get_cached_user(email)
