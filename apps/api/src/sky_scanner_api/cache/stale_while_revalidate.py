"""Stale-while-revalidate (SWR) cache pattern on top of Redis."""

from __future__ import annotations

import json
import time
from typing import Any, Literal, TypedDict

from .redis_client import get_redis_pool


class SWREnvelope(TypedDict):
    """Wrapper stored in Redis containing data + freshness timestamps."""

    data: Any
    fresh_until: float
    stale_until: float


async def swr_get(key: str) -> tuple[Any | None, Literal["fresh", "stale", "miss"]]:
    """Read from cache with SWR semantics.

    Returns ``(data, status)`` where *status* is one of:
    - ``"fresh"``  -- data is within the fresh window
    - ``"stale"``  -- data is past fresh but within the stale grace window
    - ``"miss"``   -- no data or fully expired
    """
    pool = await get_redis_pool()
    raw = await pool.get(key)
    if raw is None:
        return None, "miss"

    envelope: SWREnvelope = json.loads(raw)
    now = time.time()

    if now < envelope["fresh_until"]:
        return envelope["data"], "fresh"
    if now < envelope["stale_until"]:
        return envelope["data"], "stale"
    return None, "miss"


async def swr_set(key: str, data: Any, fresh_ttl: int, stale_ttl: int) -> None:
    """Write data into Redis wrapped in an SWR envelope.

    *fresh_ttl* seconds of "fresh" cache, then an additional
    *stale_ttl* seconds where the data is considered stale but still usable.
    """
    now = time.time()
    envelope = SWREnvelope(
        data=data,
        fresh_until=now + fresh_ttl,
        stale_until=now + fresh_ttl + stale_ttl,
    )
    total_ttl = fresh_ttl + stale_ttl
    pool = await get_redis_pool()
    await pool.set(key, json.dumps(envelope, default=str), ex=total_ttl)
