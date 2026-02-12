"""Normalized flight and price DTOs for cross-source data exchange."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, computed_field

if TYPE_CHECKING:
    from datetime import datetime

    from .enums import CabinClass, DataSource


class NormalizedPrice(BaseModel):
    """Price information from a single source."""

    amount: float
    currency: str = "KRW"
    source: DataSource
    fare_class: str | None = None
    booking_url: str | None = None
    includes_baggage: bool = False
    includes_meal: bool = False
    seat_selection_included: bool = False
    crawled_at: datetime


class NormalizedFlight(BaseModel):
    """Unified flight representation across all data sources."""

    # Flight identification
    flight_number: str
    airline_code: str
    airline_name: str | None = None
    operator: str | None = None

    # Route
    origin: str = Field(description="IATA airport code")
    destination: str = Field(description="IATA airport code")

    # Schedule (timezone-aware)
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int

    # Flight details
    cabin_class: CabinClass
    aircraft_type: str | None = None
    stops: int = 0

    # Prices from various sources
    prices: list[NormalizedPrice] = Field(default_factory=list)

    # Source metadata
    source: DataSource
    crawled_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dedup_key(self) -> str:
        """Key for deduplicating flights across sources."""
        dep_date = self.departure_time.strftime("%Y-%m-%d")
        return f"{self.flight_number}:{dep_date}:{self.cabin_class.value}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def lowest_price(self) -> float | None:
        """Lowest price across all sources."""
        if not self.prices:
            return None
        return min(p.amount for p in self.prices)
