"""Price history schemas."""

from __future__ import annotations

from datetime import date  # noqa: TC003

from pydantic import BaseModel, Field

from sky_scanner_core.schemas.enums import CabinClass


class PricePoint(BaseModel):
    """Single data point in price history."""

    date: date
    min_price: float
    max_price: float
    avg_price: float
    currency: str = "KRW"
    sample_count: int


class PriceHistoryRequest(BaseModel):
    """Request body for price history query."""

    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    start_date: date
    end_date: date
    cabin_class: CabinClass = CabinClass.ECONOMY
    currency: str = "KRW"


class PriceHistoryResponse(BaseModel):
    """Response for price history query."""

    origin: str
    destination: str
    cabin_class: CabinClass
    currency: str
    price_points: list[PricePoint]
    total_points: int
