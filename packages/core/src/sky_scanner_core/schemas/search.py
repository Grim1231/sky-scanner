"""Search request and passenger schemas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from .enums import CabinClass, TripType

if TYPE_CHECKING:
    from datetime import date


class PassengerCount(BaseModel):
    """Number of passengers by type."""

    adults: int = Field(default=1, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    infants_in_seat: int = Field(default=0, ge=0, le=4)
    infants_on_lap: int = Field(default=0, ge=0, le=4)

    @model_validator(mode="after")
    def _validate_totals(self) -> PassengerCount:
        total = self.adults + self.children + self.infants_in_seat + self.infants_on_lap
        if total > 9:
            msg = f"Total passengers ({total}) exceeds maximum of 9"
            raise ValueError(msg)
        if self.infants_on_lap > self.adults:
            msg = "Each infant on lap requires at least one adult"
            raise ValueError(msg)
        return self


class SearchRequest(BaseModel):
    """Flight search parameters."""

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

    @model_validator(mode="after")
    def _validate_dates(self) -> SearchRequest:
        if self.trip_type == TripType.ROUND_TRIP and self.return_date is None:
            msg = "return_date is required for round-trip"
            raise ValueError(msg)
        if self.return_date and self.return_date < self.departure_date:
            msg = "return_date must be after departure_date"
            raise ValueError(msg)
        return self
