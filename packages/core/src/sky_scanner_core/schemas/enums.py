"""Pydantic-compatible enums for crawler schemas (DB-independent)."""

from enum import StrEnum


class DataSource(StrEnum):
    """Source of crawled flight data."""

    GOOGLE_PROTOBUF = "GOOGLE_PROTOBUF"
    KIWI_API = "KIWI_API"
    DIRECT_CRAWL = "DIRECT_CRAWL"
    OFFICIAL_API = "OFFICIAL_API"
    GDS = "GDS"


class CabinClass(StrEnum):
    """Cabin class for the flight."""

    ECONOMY = "ECONOMY"
    PREMIUM_ECONOMY = "PREMIUM_ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"


class TripType(StrEnum):
    """Trip type."""

    ONE_WAY = "ONE_WAY"
    ROUND_TRIP = "ROUND_TRIP"
    MULTI_CITY = "MULTI_CITY"
