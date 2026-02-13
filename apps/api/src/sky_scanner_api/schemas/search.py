"""Search request / response schemas."""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003

from pydantic import BaseModel, Field

from sky_scanner_core.schemas.enums import CabinClass, TripType
from sky_scanner_core.schemas.search import PassengerCount


class FlightSearchRequest(BaseModel):
    """Inbound search parameters from the client."""

    origin: str = Field(min_length=3, max_length=3, description="IATA airport code")
    destination: str = Field(
        min_length=3, max_length=3, description="IATA airport code"
    )
    departure_date: date
    return_date: date | None = None
    cabin_class: CabinClass = CabinClass.ECONOMY
    trip_type: TripType = TripType.ONE_WAY
    passengers: PassengerCount = Field(default_factory=PassengerCount)
    currency: str = Field(default="KRW", min_length=3, max_length=3)
    include_alternatives: bool = True


class PriceInfo(BaseModel):
    """Single price entry for a flight."""

    amount: float
    currency: str
    source: str
    fare_class: str | None = None
    booking_url: str | None = None
    includes_baggage: bool = False
    includes_meal: bool = False
    crawled_at: datetime


class FlightResult(BaseModel):
    """One flight in the search results."""

    flight_number: str
    airline_code: str
    airline_name: str
    origin: str
    destination: str
    origin_city: str
    destination_city: str
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    cabin_class: str
    aircraft_type: str | None = None
    prices: list[PriceInfo]
    lowest_price: float | None = None
    source: str
    score: float | None = None
    score_breakdown: dict | None = None


class FlightSearchResponse(BaseModel):
    """Full search response envelope."""

    flights: list[FlightResult]
    total: int
    cached: bool = False
    background_crawl_dispatched: bool = False
