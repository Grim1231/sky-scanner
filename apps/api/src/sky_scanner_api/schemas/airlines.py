"""Airline schemas."""

from __future__ import annotations

from pydantic import BaseModel


class AirlineItem(BaseModel):
    """Single airline entry."""

    code: str
    name: str
    type: str
    alliance: str
    base_country: str
    website_url: str | None = None


class AirlineListResponse(BaseModel):
    """Response for airline listing."""

    airlines: list[AirlineItem]
    total: int
