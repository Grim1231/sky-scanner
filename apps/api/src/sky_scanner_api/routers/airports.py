"""Airport search router."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query

from ..cache.cache_keys import airport_search_key
from ..cache.redis_client import cache_get, cache_set
from ..dependencies import get_db
from ..schemas.airports import AirportSearchResponse
from ..services.airport_service import AirportService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/airports", tags=["airports"])

_AIRPORT_CACHE_TTL = 3600  # 1 hour

DbDep = Annotated["AsyncSession", Depends(get_db)]


@router.get("/search", response_model=AirportSearchResponse)
async def search_airports(
    db: DbDep,
    q: Annotated[str, Query(min_length=1, max_length=50)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> AirportSearchResponse:
    key = airport_search_key(q.lower())
    cached = await cache_get(key)
    if cached is not None:
        return AirportSearchResponse.model_validate(cached)

    service = AirportService(db)
    airports = await service.search_airports(q, limit)
    response = AirportSearchResponse(
        query=q,
        airports=airports,
        total=len(airports),
    )
    await cache_set(key, response.model_dump(mode="json"), _AIRPORT_CACHE_TTL)
    return response
