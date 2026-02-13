"""Preference-based filter sets for SQL and post-processing."""

from __future__ import annotations

from datetime import time  # noqa: TC003
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from sky_scanner_db.models.user import UserPreference


class SQLFilterSet(BaseModel):
    """Parameters for SQL WHERE clause filtering."""

    max_stops: int | None = None
    preferred_airlines: list[str] | None = None
    excluded_airlines: list[str] | None = None
    preferred_alliance: str | None = None
    departure_time_start: time | None = None
    departure_time_end: time | None = None
    preferred_days: list[int] | None = None
    cabin_class: str | None = None
    min_price: float | None = None
    max_price: float | None = None


class PostFilterConfig(BaseModel):
    """Parameters for Python-side post-processing and scoring."""

    min_seat_pitch: float | None = None
    min_seat_width: float | None = None
    baggage_required: bool = False
    meal_required: bool = False
    priority: str = "BALANCED"
    departure_time_start: time | None = None
    departure_time_end: time | None = None


def build_filters(prefs: UserPreference) -> tuple[SQLFilterSet, PostFilterConfig]:
    """Convert a UserPreference DB model into SQL and post-processing filters."""
    preferred_airlines: list[str] | None = None
    if prefs.preferred_airlines and isinstance(prefs.preferred_airlines, dict):
        codes = prefs.preferred_airlines.get("codes")
        if codes:
            preferred_airlines = list(codes)

    excluded_airlines: list[str] | None = None
    if prefs.excluded_airlines and isinstance(prefs.excluded_airlines, dict):
        codes = prefs.excluded_airlines.get("codes")
        if codes:
            excluded_airlines = list(codes)

    preferred_days: list[int] | None = None
    if prefs.preferred_days and isinstance(prefs.preferred_days, dict):
        days = prefs.preferred_days.get("days")
        if days:
            preferred_days = list(days)

    sql_filters = SQLFilterSet(
        max_stops=prefs.max_stops,
        preferred_airlines=preferred_airlines,
        excluded_airlines=excluded_airlines,
        preferred_alliance=(
            prefs.preferred_alliance.name if prefs.preferred_alliance else None
        ),
        departure_time_start=prefs.preferred_departure_time_start,
        departure_time_end=prefs.preferred_departure_time_end,
        preferred_days=preferred_days,
        cabin_class=(
            prefs.preferred_cabin_class.value if prefs.preferred_cabin_class else None
        ),
    )

    post_config = PostFilterConfig(
        min_seat_pitch=prefs.min_seat_pitch,
        min_seat_width=prefs.min_seat_width,
        baggage_required=prefs.baggage_required,
        meal_required=prefs.meal_required,
        priority=prefs.priority.value if prefs.priority else "BALANCED",
        departure_time_start=prefs.preferred_departure_time_start,
        departure_time_end=prefs.preferred_departure_time_end,
    )

    return sql_filters, post_config
