import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from core.settings import settings

redis_client: Redis | None = None


async def init_redis_client() -> Redis:
    global redis_client
    if redis_client is None:
        redis_client = Redis.from_url(settings.redis.url, decode_responses=True)
    return redis_client


async def close_redis_client() -> None:
    global redis_client
    if redis_client is None:
        return
    await redis_client.aclose()
    redis_client = None


async def get_redis_client() -> Redis:
    # Fallback for contexts where FastAPI lifespan is not triggered.
    return await init_redis_client()


def build_user_cache_key(email: str) -> str:
    return f"{settings.redis.user_cache_prefix}:{email}"


def build_refresh_blacklist_key(token_jti: str) -> str:
    return f"{settings.redis.refresh_blacklist_prefix}:{token_jti}"


async def get_cached_user(email: str) -> dict[str, Any] | None:
    try:
        redis_client = await get_redis_client()
        cached_user = await redis_client.get(build_user_cache_key(email))
    except RedisError:
        return None
    if not cached_user:
        return None
    return json.loads(cached_user)


async def cache_user(user_data: dict[str, Any]) -> None:
    try:
        redis_client = await get_redis_client()
        await redis_client.setex(
            build_user_cache_key(user_data["email"]),
            settings.redis.user_cache_ttl_seconds,
            json.dumps(user_data),
        )
    except RedisError:
        return None


async def blacklist_refresh_token(token_jti: str, ttl_seconds: int) -> None:
    try:
        redis_client = await get_redis_client()
        await redis_client.setex(build_refresh_blacklist_key(token_jti), ttl_seconds, "1")
    except RedisError:
        return None


async def is_refresh_token_blacklisted(token_jti: str) -> bool:
    try:
        redis_client = await get_redis_client()
        return await redis_client.exists(build_refresh_blacklist_key(token_jti)) == 1
    except RedisError:
        return False
