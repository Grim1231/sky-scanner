"""Price prediction router."""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query

from sky_scanner_core.schemas.enums import CabinClass

from ..dependencies import get_db, get_redis
from ..schemas.prediction import BestTimeResponse, PricePredictionResponse
from ..services.prediction_service import PredictionService

if TYPE_CHECKING:
    import redis.asyncio as redis
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/prices", tags=["prices"])

DbDep = Annotated["AsyncSession", Depends(get_db)]
RedisDep = Annotated["redis.Redis", Depends(get_redis)]


@router.get("/predict", response_model=PricePredictionResponse)
async def predict_price(
    db: DbDep,
    redis_conn: RedisDep,
    origin: Annotated[str, Query(min_length=3, max_length=3)],
    destination: Annotated[str, Query(min_length=3, max_length=3)],
    departure_date: Annotated[date, Query()],
    cabin_class: Annotated[CabinClass, Query()] = CabinClass.ECONOMY,
) -> PricePredictionResponse:
    """Predict price direction and get buy/wait recommendation."""
    service = PredictionService(db, redis_conn)
    result = await service.predict_price(
        origin, destination, departure_date, cabin_class.value
    )
    return PricePredictionResponse(**result)


@router.get("/best-time", response_model=BestTimeResponse)
async def best_time_to_buy(
    db: DbDep,
    redis_conn: RedisDep,
    origin: Annotated[str, Query(min_length=3, max_length=3)],
    destination: Annotated[str, Query(min_length=3, max_length=3)],
) -> BestTimeResponse:
    """Analyze the best time to buy for a route."""
    service = PredictionService(db, redis_conn)
    result = await service.best_time(origin, destination)
    return BestTimeResponse(**result)
