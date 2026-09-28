"""Redis client dependency.

In production this connects to `settings.redis_url`. In tests we override
this dependency with `fakeredis` via `app.dependency_overrides[get_redis]`.
"""
from redis.asyncio import Redis

from app.config import settings


async def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)