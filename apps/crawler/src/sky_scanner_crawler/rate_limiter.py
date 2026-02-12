"""Redis-based sliding window rate limiter."""

from __future__ import annotations

import time

import redis.asyncio as aioredis


class RateLimiter:
    """Per-source rate limiter using Redis sliding window."""

    def __init__(
        self, redis_url: str, source: str, max_requests: int, window: int = 60
    ):
        self._redis = aioredis.from_url(redis_url)
        self._key = f"rate_limit:{source}"
        self._max_requests = max_requests
        self._window = window

    async def acquire(self) -> bool:
        """Try to acquire a rate limit slot. Returns True if allowed."""
        now = time.time()
        window_start = now - self._window

        pipe = self._redis.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(self._key, 0, window_start)
        # Count current window
        pipe.zcard(self._key)
        # Add current request
        pipe.zadd(self._key, {str(now): now})
        # Set expiry on the key
        pipe.expire(self._key, self._window)
        results = await pipe.execute()

        current_count = results[1]
        if current_count >= self._max_requests:
            # Remove the entry we just added
            await self._redis.zrem(self._key, str(now))
            return False
        return True

    async def wait_and_acquire(self) -> None:
        """Block until a rate limit slot is available."""
        import asyncio

        while not await self.acquire():
            await asyncio.sleep(1.0)

    async def close(self) -> None:
        await self._redis.aclose()
