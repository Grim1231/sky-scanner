"""Redis-based sliding window rate limiter middleware."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import jwt
import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from sky_scanner_api.config import settings

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter backed by Redis sorted sets."""

    def __init__(
        self,
        app: ASGIApp,
        redis_url: str | None = None,
        requests_per_minute: int | None = None,
    ) -> None:
        super().__init__(app)
        self._redis_url = redis_url or settings.redis_url
        self._rpm = requests_per_minute or settings.rate_limit_per_minute
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def dispatch(self, request: Request, call_next) -> Response:
        """Check rate limit, then forward to the next middleware/route."""
        identifier = self._get_identifier(request)
        redis = await self._get_redis()

        key = f"rate_limit:{identifier}"
        now = time.time()
        window_start = now - 60.0

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, "-inf", window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, 120)
        results = await pipe.execute()

        request_count = results[1]

        if request_count >= self._rpm:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": "60"},
            )

        return await call_next(request)

    @staticmethod
    def _get_identifier(request: Request) -> str:
        """Extract user ID from JWT bearer token, or fall back to client IP."""
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            try:
                payload = jwt.decode(
                    token,
                    settings.jwt_secret,
                    algorithms=[settings.jwt_algorithm],
                )
                user_id = payload.get("sub")
                if user_id:
                    return f"user:{user_id}"
            except jwt.InvalidTokenError:
                pass

        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        client = request.client
        if client is not None:
            return f"ip:{client.host}"
        return "ip:unknown"
