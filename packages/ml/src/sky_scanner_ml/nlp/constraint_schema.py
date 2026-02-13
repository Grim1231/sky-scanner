"""Pydantic schema for natural language search constraints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class NaturalSearchConstraints(BaseModel):
    """Constraints extracted from a natural language flight search query."""

    # Route
    origin: str | None = None
    destination: str | None = None

    # Dates
    departure_date: date | None = None
    return_date: date | None = None

    # Price
    max_price: float | None = None
    currency: str = "KRW"

    # Stops
    max_stops: int | None = None

    # Airlines
    preferred_airlines: list[str] | None = None
    excluded_airlines: list[str] | None = None
    preferred_alliance: str | None = None

    # Cabin
    cabin_class: str | None = None  # ECONOMY, BUSINESS, FIRST

    # Time preferences
    departure_time_start: str | None = None  # HH:MM format
    departure_time_end: str | None = None  # HH:MM format
    preferred_days: list[str] | None = None  # MON, TUE, WED, THU, FRI, SAT, SUN

    # Comfort
    min_seat_width: float | None = None
    min_seat_pitch: float | None = None

    # Services
    baggage_required: bool | None = None
    meal_required: bool | None = None

    # Sorting & trip type
    sort_by: str | None = None  # PRICE, TIME, COMFORT
    trip_type: str | None = None  # ONE_WAY, ROUND_TRIP

    # Passengers
    passengers_adults: int | None = None
    passengers_children: int | None = None

    def to_search_params(self) -> dict:
        """Convert non-None fields to a dict suitable for API consumption."""
        result: dict = {}
        for field_name, value in self:
            if value is not None:
                if isinstance(value, date):
                    result[field_name] = value.isoformat()
                else:
                    result[field_name] = value
        return result
