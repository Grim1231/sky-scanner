"""User-related request/response schemas."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import date, datetime, time  # noqa: TC003

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    """Public user profile."""

    id: uuid.UUID
    email: str
    name: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UserPreferenceResponse(BaseModel):
    """User flight preferences."""

    min_seat_pitch: float | None = None
    min_seat_width: float | None = None
    preferred_departure_time_start: time | None = None
    preferred_departure_time_end: time | None = None
    max_layover_hours: int | None = None
    max_stops: int | None = None
    preferred_alliance: str | None = None
    preferred_airlines: dict | None = None
    excluded_airlines: dict | None = None
    baggage_required: bool = False
    meal_required: bool = False
    preferred_cabin_class: str | None = None
    priority: str = "BALANCED"
    notes: str | None = None
    model_config = ConfigDict(from_attributes=True)


class UpdatePreferenceRequest(BaseModel):
    """Partial update for user preferences."""

    min_seat_pitch: float | None = None
    min_seat_width: float | None = None
    preferred_departure_time_start: time | None = None
    preferred_departure_time_end: time | None = None
    max_layover_hours: int | None = None
    max_stops: int | None = None
    preferred_alliance: str | None = None
    preferred_airlines: dict | None = None
    excluded_airlines: dict | None = None
    baggage_required: bool | None = None
    meal_required: bool | None = None
    preferred_cabin_class: str | None = None
    priority: str | None = None
    notes: str | None = None


class SearchHistoryItem(BaseModel):
    """Single search history entry."""

    id: uuid.UUID
    origin: str
    destination: str
    departure_date: date
    return_date: date | None = None
    passengers: int
    cabin_class: str
    searched_at: datetime
    results_count: int
    model_config = ConfigDict(from_attributes=True)


class SearchHistoryResponse(BaseModel):
    """Paginated search history."""

    history: list[SearchHistoryItem]
    total: int
