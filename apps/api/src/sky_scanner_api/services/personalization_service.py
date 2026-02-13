"""Personalization service - user preferences, scoring, seat specs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sky_scanner_db.models.airline import Airline
from sky_scanner_db.models.seat_spec import SeatSpec
from sky_scanner_db.models.user import UserPreference
from sky_scanner_ml.preference_filter import build_filters
from sky_scanner_ml.scoring import FlightScorer

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from sky_scanner_api.schemas.search import FlightResult
    from sky_scanner_ml.preference_filter import PostFilterConfig, SQLFilterSet

logger = logging.getLogger(__name__)


class PersonalizationService:
    """Handles user preference loading, flight scoring, and seat specs."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_user_filters(
        self, user_id: UUID
    ) -> tuple[SQLFilterSet, PostFilterConfig] | None:
        """Load user preferences and convert to SQL + post-processing filters.

        Returns None if the user has no saved preferences.
        """
        result = await self._db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        pref = result.scalar_one_or_none()
        if pref is None:
            return None

        return build_filters(pref)

    async def score_results(
        self,
        flights: list[FlightResult],
        user_id: UUID | None,
    ) -> list[FlightResult]:
        """Score and re-sort flights based on user preferences.

        If no user_id or no preferences, returns flights unchanged.
        """
        if not user_id or not flights:
            return flights

        result = await self._db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        pref = result.scalar_one_or_none()
        if pref is None:
            return flights

        _, post_config = build_filters(pref)

        # Collect airline codes and cabin classes for seat spec lookup
        airline_codes = list({f.airline_code for f in flights})
        cabin_classes = list({f.cabin_class for f in flights})
        seat_specs = await self.get_seat_specs(airline_codes, cabin_classes)

        # Convert FlightResult list to dicts for FlightScorer
        flight_dicts = [f.model_dump(mode="json") for f in flights]

        scorer = FlightScorer(post_config)
        breakdowns = scorer.score_flights(flight_dicts, seat_specs)

        # Attach scores to flights
        scored_flights: list[FlightResult] = []
        for flight, breakdown in zip(flights, breakdowns, strict=True):
            flight.score = breakdown.total_score
            flight.score_breakdown = breakdown.model_dump()
            scored_flights.append(flight)

        # Sort by total_score descending
        scored_flights.sort(key=lambda f: f.score or 0, reverse=True)
        return scored_flights

    async def get_seat_specs(
        self,
        airline_codes: list[str],
        cabin_classes: list[str],
    ) -> dict[str, dict]:
        """Query seat specs for given airlines and cabin classes.

        Returns dict keyed by "{airline_code}_{cabin_class}" with spec values.
        """
        if not airline_codes:
            return {}

        stmt = (
            select(SeatSpec)
            .join(Airline, SeatSpec.airline_id == Airline.id)
            .where(
                Airline.code.in_(airline_codes),
                SeatSpec.cabin_class.in_(cabin_classes),
            )
            .options(selectinload(SeatSpec.airline))
        )

        result = await self._db.execute(stmt)
        specs = result.scalars().all()

        spec_map: dict[str, dict] = {}
        for spec in specs:
            key = f"{spec.airline.code}_{spec.cabin_class.value}"
            spec_map[key] = {
                "seat_pitch_inches": spec.seat_pitch_inches,
                "seat_width_inches": spec.seat_width_inches,
            }
        return spec_map
