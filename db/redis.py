import asyncio
import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from core.settings import settings

redis_client: Redis | None = None
redis_client_loop_id: int | None = None


async def init_redis_client() -> Redis:
    global redis_client, redis_client_loop_id
    current_loop_id = id(asyncio.get_running_loop())

    if redis_client is not None and redis_client_loop_id != current_loop_id:
        try:
            await redis_client.aclose()
        except RuntimeError:
            pass
        redis_client = None
        redis_client_loop_id = None

    if redis_client is None:
        redis_client = Redis.from_url(settings.redis.url, decode_responses=True)
        redis_client_loop_id = current_loop_id
    return redis_client


async def close_redis_client() -> None:
    global redis_client, redis_client_loop_id
    if redis_client is None:
        return
    await redis_client.aclose()
    redis_client = None
    redis_client_loop_id = None


async def get_redis_client() -> Redis:
    # Fallback for contexts where FastAPI lifespan is not triggered.
    return await init_redis_client()


def build_user_cache_key(email: str) -> str:
    return f"{settings.redis.user_cache_prefix}:{email}"


def build_refresh_blacklist_key(token_jti: str) -> str:
    return f"{settings.redis.refresh_blacklist_prefix}:{token_jti}"


def build_yandex_oauth_state_key(state: str) -> str:
    return f"{settings.yandex_oauth.state_prefix}:{state}"


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


async def store_yandex_oauth_state(state: str) -> bool:
    try:
        redis_client = await get_redis_client()
        await redis_client.setex(
            build_yandex_oauth_state_key(state),
            settings.yandex_oauth.state_ttl_seconds,
            "1",
        )
        return True
    except RedisError:
        return False


async def consume_yandex_oauth_state(state: str) -> bool:
    try:
        redis_client = await get_redis_client()
        deleted_keys = await redis_client.delete(build_yandex_oauth_state_key(state))
        return deleted_keys == 1
    except RedisError:
        return False
