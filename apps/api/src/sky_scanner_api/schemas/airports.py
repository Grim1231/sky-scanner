"""Airport schemas."""

from __future__ import annotations

from pydantic import BaseModel


class AirportItem(BaseModel):
    """Single airport entry."""

    code: str
    name: str
    city: str
    country: str
    timezone: str
    latitude: float
    longitude: float


class AirportSearchResponse(BaseModel):
    """Response for airport search."""

    query: str
    airports: list[AirportItem]
    total: int
