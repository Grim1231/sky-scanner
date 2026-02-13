"""FastAPI dependency injection providers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sky_scanner_api.cache.redis_client import get_redis_pool
from sky_scanner_api.config import settings
from sky_scanner_db.database import get_db as _db_dependency

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from uuid import UUID

    import redis.asyncio as redis

# Re-export the DB dependency unchanged.
get_db = _db_dependency

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_redis() -> AsyncGenerator[redis.Redis]:
    """Yield the shared Redis connection."""
    pool = await get_redis_pool()
    yield pool


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
) -> dict | None:
    """Decode a JWT and return a minimal user dict, or *None* if unauthenticated."""
    if credentials is None:
        return None
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.PyJWTError:
        return None


async def require_current_user(
    user: Annotated[dict | None, Depends(get_current_user)],
) -> dict:
    """Same as :func:`get_current_user` but raises 401 when absent."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def user_id_from_token(user: dict | None) -> UUID | None:
    """Extract the user UUID from a decoded JWT payload."""
    if user is None:
        return None
    from uuid import UUID as _UUID

    raw = user.get("sub") or user.get("user_id")
    if raw is None:
        return None
    return _UUID(str(raw))
