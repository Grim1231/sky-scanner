"""Redis connection pool and basic cache helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)

redis_pool: redis.Redis | None = None


async def init_redis(url: str) -> None:
    """Create the shared Redis connection pool."""
    global redis_pool
    redis_pool = redis.from_url(url, decode_responses=True)
    logger.info("Redis pool initialised: %s", url)


async def close_redis() -> None:
    """Gracefully close the Redis pool."""
    global redis_pool
    if redis_pool is not None:
        await redis_pool.aclose()
        redis_pool = None
        logger.info("Redis pool closed")


async def get_redis_pool() -> redis.Redis:
    """Return the active Redis connection (raises if not initialised)."""
    if redis_pool is None:
        msg = "Redis pool has not been initialised"
        raise RuntimeError(msg)
    return redis_pool


async def cache_get(key: str) -> Any | None:
    """Retrieve a JSON-deserialised value from Redis."""
    pool = await get_redis_pool()
    raw = await pool.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_set(key: str, value: Any, ttl: int) -> None:
    """Store a JSON-serialised value in Redis with a TTL."""
    pool = await get_redis_pool()
    await pool.set(key, json.dumps(value, default=str), ex=ttl)
