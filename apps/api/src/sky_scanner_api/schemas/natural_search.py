"""Natural language search schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from sky_scanner_api.schemas.search import FlightResult  # noqa: TC001


class NaturalSearchRequest(BaseModel):
    """Natural language search request."""

    query: str = Field(
        min_length=1,
        max_length=500,
        description="Natural language search query",
    )


class NaturalSearchResponse(BaseModel):
    """Natural language search response."""

    parsed_constraints: dict
    flights: list[FlightResult]
    total: int
    cached: bool = False
