"""Price prediction and best-time schemas."""

from __future__ import annotations

from datetime import date  # noqa: TC003

from pydantic import BaseModel, Field


class PricePredictionResponse(BaseModel):
    """Price prediction API response."""

    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    departure_date: date
    cabin_class: str
    current_avg_price: float
    predicted_direction: str
    confidence: float
    recommendation: str
    reason: str
    best_price_seen: float
    worst_price_seen: float
    percentile_current: float
    days_until_departure: int


class BestTimeResponse(BaseModel):
    """Best time to buy API response."""

    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    optimal_days_before: int
    estimated_price_at_optimal: float | None = None
    confidence: float
    current_days_before: int
    recommendation: str
