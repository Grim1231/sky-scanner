"""Price history router."""

from __future__ import annotations

import logging
from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query

from sky_scanner_core.schemas.enums import CabinClass

from ..cache.cache_keys import price_history_key
from ..cache.redis_client import cache_get, cache_set
from ..dependencies import get_db
from ..schemas.prices import PriceHistoryResponse
from ..services.price_service import PriceService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prices", tags=["prices"])

_PRICE_CACHE_TTL = 600  # 10 minutes

DbDep = Annotated["AsyncSession", Depends(get_db)]


@router.get("/history", response_model=PriceHistoryResponse)
async def get_price_history(
    db: DbDep,
    origin: Annotated[str, Query(min_length=3, max_length=3)],
    destination: Annotated[str, Query(min_length=3, max_length=3)],
    start_date: Annotated[date, Query()],
    end_date: Annotated[date, Query()],
    cabin_class: Annotated[CabinClass, Query()] = CabinClass.ECONOMY,
    currency: Annotated[str, Query()] = "KRW",
) -> PriceHistoryResponse:
    key = price_history_key(origin, destination, str(start_date), str(end_date))
    cached = await cache_get(key)
    if cached is not None:
        return PriceHistoryResponse.model_validate(cached)

    service = PriceService(db)
    points = await service.get_price_history(
        origin, destination, start_date, end_date, cabin_class, currency
    )
    response = PriceHistoryResponse(
        origin=origin,
        destination=destination,
        cabin_class=cabin_class,
        currency=currency,
        price_points=points,
        total_points=len(points),
    )
    await cache_set(key, response.model_dump(mode="json"), _PRICE_CACHE_TTL)
    return response
