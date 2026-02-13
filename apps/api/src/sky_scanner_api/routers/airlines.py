"""Airline listing router."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query

from ..cache.cache_keys import airlines_list_key
from ..cache.redis_client import cache_get, cache_set
from ..dependencies import get_db
from ..schemas.airlines import AirlineListResponse
from ..services.airline_service import AirlineService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/airlines", tags=["airlines"])

_AIRLINES_CACHE_TTL = 3600  # 1 hour

DbDep = Annotated["AsyncSession", Depends(get_db)]


@router.get("", response_model=AirlineListResponse)
async def list_airlines(
    db: DbDep,
    type: Annotated[str | None, Query()] = None,
    alliance: Annotated[str | None, Query()] = None,
) -> AirlineListResponse:
    key = airlines_list_key(type, alliance)
    cached = await cache_get(key)
    if cached is not None:
        return AirlineListResponse.model_validate(cached)

    service = AirlineService(db)
    airlines = await service.list_airlines(type, alliance)
    response = AirlineListResponse(
        airlines=airlines,
        total=len(airlines),
    )
    await cache_set(key, response.model_dump(mode="json"), _AIRLINES_CACHE_TTL)
    return response
