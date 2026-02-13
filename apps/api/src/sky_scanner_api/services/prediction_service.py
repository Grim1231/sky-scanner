"""Price prediction service."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import cast, select
from sqlalchemy.types import Date

from sky_scanner_api.cache.cache_keys import best_time_key, prediction_key
from sky_scanner_api.cache.redis_client import cache_get, cache_set
from sky_scanner_api.config import settings
from sky_scanner_db.models import Airport, BookingTimeAnalysis, Flight, Price
from sky_scanner_ml.price_prediction import HeuristicPredictor

if TYPE_CHECKING:
    import redis.asyncio as redis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PredictionService:
    """Handles price prediction and best-time analysis."""

    def __init__(self, db: AsyncSession, redis: redis.Redis) -> None:
        self._db = db
        self._redis = redis

    async def predict_price(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "ECONOMY",
    ) -> dict:
        """Predict price direction and give buy/wait recommendation."""
        key = prediction_key(origin, destination, str(departure_date))
        cached = await cache_get(key)
        if cached is not None:
            return cached

        # Query last 90 days of prices for this route
        cutoff = date.today() - timedelta(days=90)

        origin_ids = select(Airport.id).where(Airport.code == origin)
        dest_ids = select(Airport.id).where(Airport.code == destination)

        stmt = (
            select(Price.price_amount)
            .join(Flight, Price.flight_id == Flight.id)
            .where(
                Flight.origin_airport_id.in_(origin_ids),
                Flight.destination_airport_id.in_(dest_ids),
                Flight.cabin_class == cabin_class,
                cast(Flight.departure_time, Date) >= cutoff,
            )
            .order_by(Price.crawled_at)
        )

        result = await self._db.execute(stmt)
        prices = [float(row[0]) for row in result.all()]

        if not prices:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No price data available for this route",
            )

        days_until = (departure_date - date.today()).days
        predictor = HeuristicPredictor(prices, max(days_until, 0))
        prediction = predictor.predict()

        response = {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date.isoformat(),
            "cabin_class": cabin_class,
            **prediction.model_dump(),
        }

        await cache_set(key, response, settings.prediction_cache_ttl)
        return response

    async def best_time(self, origin: str, destination: str) -> dict:
        """Analyze the best time to buy for a route."""
        key = best_time_key(origin, destination)
        cached = await cache_get(key)
        if cached is not None:
            return cached

        route = f"{origin}-{destination}"

        # Get latest BookingTimeAnalysis for this route
        stmt = (
            select(BookingTimeAnalysis)
            .where(BookingTimeAnalysis.route == route)
            .order_by(BookingTimeAnalysis.analyzed_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        analysis = result.scalar_one_or_none()

        # Also get recent prices for the heuristic predictor
        cutoff = date.today() - timedelta(days=90)
        origin_ids = select(Airport.id).where(Airport.code == origin)
        dest_ids = select(Airport.id).where(Airport.code == destination)

        price_stmt = (
            select(Price.price_amount)
            .join(Flight, Price.flight_id == Flight.id)
            .where(
                Flight.origin_airport_id.in_(origin_ids),
                Flight.destination_airport_id.in_(dest_ids),
                cast(Flight.departure_time, Date) >= cutoff,
            )
            .order_by(Price.crawled_at)
        )
        price_result = await self._db.execute(price_stmt)
        prices = [float(row[0]) for row in price_result.all()]

        # Use 30 days as default reference period
        days_until = 30

        if analysis is not None:
            days_until = max(analysis.optimal_days_before, 1)

        predictor = HeuristicPredictor(prices or [0], days_until)
        best = predictor.best_time()

        response = {
            "origin": origin,
            "destination": destination,
            **best.model_dump(),
        }

        await cache_set(key, response, settings.prediction_cache_ttl)
        return response
