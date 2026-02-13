"""Natural language search service."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from sky_scanner_api.cache.cache_keys import nl_search_key
from sky_scanner_api.cache.redis_client import cache_get, cache_set
from sky_scanner_api.config import settings
from sky_scanner_api.services.personalization_service import PersonalizationService
from sky_scanner_api.services.search_service import SearchService
from sky_scanner_core.schemas.enums import CabinClass, TripType
from sky_scanner_core.schemas.search import PassengerCount
from sky_scanner_ml.nlp import parse_natural_query

if TYPE_CHECKING:
    from uuid import UUID

    import redis.asyncio as redis
    from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


class NaturalSearchService:
    """Parses natural language queries and dispatches flight searches."""

    def __init__(self, db: AsyncSession, redis: redis.Redis) -> None:
        self._db = db
        self._redis = redis

    async def search(self, query: str, user_id: UUID | None = None) -> dict:
        """Parse a natural language query and execute a flight search."""
        # Cache check
        key = nl_search_key(query)
        cached = await cache_get(key)
        if cached is not None:
            cached["cached"] = True
            return cached

        # Parse query with Claude
        try:
            constraints = await parse_natural_query(
                query, api_key=settings.anthropic_api_key
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not understand query: {exc}",
            ) from exc

        # Validate required fields
        if not constraints.origin or not constraints.destination:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not determine origin or destination from query",
            )

        # Convert constraints to FlightSearchRequest
        from sky_scanner_api.schemas.search import FlightSearchRequest

        departure = constraints.departure_date or date.today()
        cabin = (
            CabinClass(constraints.cabin_class)
            if constraints.cabin_class
            else CabinClass.ECONOMY
        )
        trip_type = (
            TripType(constraints.trip_type)
            if constraints.trip_type
            else TripType.ONE_WAY
        )

        passengers = PassengerCount()
        if constraints.passengers_adults is not None:
            passengers = PassengerCount(
                adults=constraints.passengers_adults,
                children=constraints.passengers_children or 0,
            )

        request = FlightSearchRequest(
            origin=constraints.origin,
            destination=constraints.destination,
            departure_date=departure,
            return_date=constraints.return_date,
            cabin_class=cabin,
            trip_type=trip_type,
            passengers=passengers,
            currency=constraints.currency,
            include_alternatives=True,
        )

        # Execute search
        search_service = SearchService(self._db, self._redis)
        response = await search_service.search_flights(request, user_id=user_id)
        flights = response.flights

        # Apply personalization scoring if user is authenticated
        if user_id:
            personalization = PersonalizationService(self._db)
            flights = await personalization.score_results(flights, user_id)

        result = {
            "parsed_constraints": constraints.to_search_params(),
            "flights": [f.model_dump(mode="json") for f in flights],
            "total": len(flights),
            "cached": False,
        }

        # Cache the result
        await cache_set(key, result, settings.nl_search_cache_ttl)
        return result
