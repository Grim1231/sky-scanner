"""Flight search business logic."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from sky_scanner_api.cache.cache_keys import search_key
from sky_scanner_api.cache.stale_while_revalidate import swr_get, swr_set
from sky_scanner_api.config import settings
from sky_scanner_api.crawl.alternative_airports import expand_airports
from sky_scanner_api.crawl.dispatcher import dispatch_crawl
from sky_scanner_api.schemas.search import (
    FlightResult,
    FlightSearchResponse,
    PriceInfo,
)
from sky_scanner_api.services.personalization_service import PersonalizationService
from sky_scanner_db.models import Airline, Airport, Flight

if TYPE_CHECKING:
    from uuid import UUID

    import redis.asyncio as redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from sky_scanner_api.schemas.search import FlightSearchRequest
    from sky_scanner_ml.preference_filter import SQLFilterSet

logger = logging.getLogger(__name__)


class SearchService:
    """Orchestrates cache lookup, DB query, and crawl dispatch."""

    def __init__(self, db: AsyncSession, redis: redis.Redis) -> None:
        self._db = db
        self._redis = redis

    async def search_flights(
        self,
        request: FlightSearchRequest,
        user_id: UUID | None = None,
    ) -> FlightSearchResponse:
        """Execute a flight search with SWR caching."""
        key = search_key(
            request.origin,
            request.destination,
            str(request.departure_date),
            request.cabin_class.value,
        )

        # --- SWR cache check ---
        cached_data, cache_status = await swr_get(key)

        if cache_status == "fresh" and cached_data is not None:
            return FlightSearchResponse(
                flights=[FlightResult(**f) for f in cached_data["flights"]],
                total=cached_data["total"],
                cached=True,
                background_crawl_dispatched=False,
            )

        if cache_status == "stale" and cached_data is not None:
            # Return stale data but trigger a background crawl
            await dispatch_crawl(request.model_dump(mode="json"))
            return FlightSearchResponse(
                flights=[FlightResult(**f) for f in cached_data["flights"]],
                total=cached_data["total"],
                cached=True,
                background_crawl_dispatched=True,
            )

        # --- MISS: query DB ---
        # Load user preference filters if authenticated
        sql_filters: SQLFilterSet | None = None
        if user_id:
            personalization = PersonalizationService(self._db)
            filter_result = await personalization.get_user_filters(user_id)
            if filter_result is not None:
                sql_filters = filter_result[0]

        flights = await self._query_flights(request, sql_filters)

        # Score and sort results based on user preferences
        if user_id:
            personalization = PersonalizationService(self._db)
            flights = await personalization.score_results(flights, user_id)

        # Dispatch crawl for fresh data
        task_id = await dispatch_crawl(request.model_dump(mode="json"))
        dispatched = task_id is not None

        # Cache the result
        response_data = {
            "flights": [f.model_dump(mode="json") for f in flights],
            "total": len(flights),
        }
        await swr_set(
            key,
            response_data,
            fresh_ttl=settings.search_cache_ttl,
            stale_ttl=settings.search_cache_swr,
        )

        return FlightSearchResponse(
            flights=flights,
            total=len(flights),
            cached=False,
            background_crawl_dispatched=dispatched,
        )

    async def _query_flights(
        self,
        request: FlightSearchRequest,
        sql_filters: SQLFilterSet | None = None,
    ) -> list[FlightResult]:
        """Query the database for matching flights."""
        # Resolve airport codes (with optional alternatives)
        if request.include_alternatives:
            origin_codes = expand_airports(request.origin)
            dest_codes = expand_airports(request.destination)
        else:
            origin_codes = [request.origin]
            dest_codes = [request.destination]

        # Subquery: airport IDs from codes
        origin_ids = select(Airport.id).where(Airport.code.in_(origin_codes))
        dest_ids = select(Airport.id).where(Airport.code.in_(dest_codes))

        stmt = (
            select(Flight)
            .options(
                selectinload(Flight.airline),
                selectinload(Flight.origin_airport),
                selectinload(Flight.destination_airport),
                selectinload(Flight.prices),
            )
            .where(
                Flight.origin_airport_id.in_(origin_ids),
                Flight.destination_airport_id.in_(dest_ids),
                func.date(Flight.departure_time) == request.departure_date,
                Flight.cabin_class == request.cabin_class,
            )
        )

        # Apply preference-based SQL filters
        if sql_filters is not None:
            if sql_filters.max_stops is not None:
                stmt = stmt.where(Flight.stops <= sql_filters.max_stops)
            if sql_filters.preferred_airlines:
                stmt = stmt.join(Airline, Flight.airline_id == Airline.id).where(
                    Airline.code.in_(sql_filters.preferred_airlines)
                )
            elif sql_filters.excluded_airlines:
                stmt = stmt.join(Airline, Flight.airline_id == Airline.id).where(
                    Airline.code.notin_(sql_filters.excluded_airlines)
                )
            if sql_filters.preferred_alliance:
                # Only join if not already joined above
                needs_join = (
                    not sql_filters.preferred_airlines
                    and not sql_filters.excluded_airlines
                )
                if needs_join:
                    stmt = stmt.join(Airline, Flight.airline_id == Airline.id)
                stmt = stmt.where(Airline.alliance == sql_filters.preferred_alliance)
            if sql_filters.departure_time_start and sql_filters.departure_time_end:
                stmt = stmt.where(
                    func.extract("hour", Flight.departure_time) * 60
                    + func.extract("minute", Flight.departure_time)
                    >= sql_filters.departure_time_start.hour * 60
                    + sql_filters.departure_time_start.minute,
                    func.extract("hour", Flight.departure_time) * 60
                    + func.extract("minute", Flight.departure_time)
                    <= sql_filters.departure_time_end.hour * 60
                    + sql_filters.departure_time_end.minute,
                )

        stmt = stmt.order_by(Flight.departure_time)

        result = await self._db.execute(stmt)
        db_flights = result.scalars().unique().all()

        return [self._to_flight_result(f) for f in db_flights]

    @staticmethod
    def _to_flight_result(flight: Flight) -> FlightResult:
        """Map a DB Flight (with loaded relations) to the API schema."""
        prices = [
            PriceInfo(
                amount=float(p.price_amount),
                currency=p.currency,
                source=flight.source.value,
                fare_class=p.fare_class,
                booking_url=p.booking_url,
                includes_baggage=p.includes_baggage,
                includes_meal=p.includes_meal,
                crawled_at=p.crawled_at,
            )
            for p in flight.prices
        ]
        lowest = min((p.amount for p in prices), default=None)

        return FlightResult(
            flight_number=flight.flight_number,
            airline_code=flight.airline.code,
            airline_name=flight.airline.name,
            origin=flight.origin_airport.code,
            destination=flight.destination_airport.code,
            origin_city=flight.origin_airport.city,
            destination_city=flight.destination_airport.city,
            departure_time=flight.departure_time,
            arrival_time=flight.arrival_time,
            duration_minutes=flight.duration_minutes,
            cabin_class=flight.cabin_class.value,
            aircraft_type=flight.aircraft_type,
            prices=prices,
            lowest_price=lowest,
            source=flight.source.value,
        )
