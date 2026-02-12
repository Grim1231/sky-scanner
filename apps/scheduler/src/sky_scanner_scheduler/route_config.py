"""Airline-source routing table and route tiers."""

from __future__ import annotations

from sky_scanner_core.schemas import DataSource

# Airline code → list of data sources to crawl
AIRLINE_SOURCE_MAP: dict[str, list[DataSource]] = {
    # Korean carriers
    "KE": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # Korean Air
    "OZ": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # Asiana
    "7C": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # Jeju Air
    "TW": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # T'way Air
    "LJ": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # Jin Air
    "ZE": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # Eastar Jet
    "BX": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # Air Busan
    "RS": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # Air Seoul
    # International carriers
    "NH": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # ANA
    "JL": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # JAL
    "CX": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # Cathay Pacific
    "SQ": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # Singapore Airlines
    "TG": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # Thai Airways
    "VN": [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API],  # Vietnam Airlines
}

# Default sources for airlines not in the map
DEFAULT_SOURCES: list[DataSource] = [DataSource.GOOGLE_PROTOBUF, DataSource.KIWI_API]

# Tier 1: Popular routes - crawled every 10 minutes
TIER1_ROUTES: list[tuple[str, str]] = [
    # Japan
    ("ICN", "NRT"),
    ("ICN", "KIX"),
    ("ICN", "FUK"),
    ("GMP", "HND"),
    # Southeast Asia
    ("ICN", "BKK"),
    ("ICN", "SGN"),
    ("ICN", "DPS"),
    ("ICN", "MNL"),
    ("ICN", "CEB"),
    # China
    ("ICN", "PVG"),
    ("ICN", "PEK"),
    # Other
    ("ICN", "HKG"),
    ("ICN", "SIN"),
    ("ICN", "TPE"),
    ("ICN", "KUL"),
]

# Tier 2: Other routes - crawled every 2 hours
TIER2_ROUTES: list[tuple[str, str]] = [
    # Long haul
    ("ICN", "LAX"),
    ("ICN", "JFK"),
    ("ICN", "SFO"),
    ("ICN", "LHR"),
    ("ICN", "CDG"),
    ("ICN", "FRA"),
    ("ICN", "SYD"),
    # Japan secondary
    ("ICN", "CTS"),
    ("ICN", "NGO"),
    ("ICN", "OKA"),
    ("PUS", "NRT"),
    ("PUS", "KIX"),
    ("PUS", "FUK"),
    # SE Asia secondary
    ("ICN", "HAN"),
    ("ICN", "DAD"),
    ("ICN", "CNX"),
    ("PUS", "BKK"),
]


def get_sources_for_airline(airline_code: str) -> list[DataSource]:
    """Get data sources to crawl for a given airline."""
    return AIRLINE_SOURCE_MAP.get(airline_code, DEFAULT_SOURCES)
