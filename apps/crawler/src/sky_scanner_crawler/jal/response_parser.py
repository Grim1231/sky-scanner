"""Parse Japan Airlines Sputnik fare search response into NormalizedFlight objects."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sky_scanner_core.schemas import (
    CabinClass,
    DataSource,
    NormalizedFlight,
    NormalizedPrice,
)

logger = logging.getLogger(__name__)

_JL_CODE = "JL"
_JL_NAME = "Japan Airlines"

# Map Sputnik fareClass strings to CabinClass enum values.
_FARE_CLASS_MAP: dict[str, CabinClass] = {
    "ECONOMY": CabinClass.ECONOMY,
    "PREMIUM_ECONOMY": CabinClass.PREMIUM_ECONOMY,
    "PREMIUMECONOMY": CabinClass.PREMIUM_ECONOMY,
    "BUSINESS": CabinClass.BUSINESS,
    "FIRST": CabinClass.FIRST,
}


def _map_cabin_class(fare_class_str: str) -> CabinClass:
    """Convert Sputnik fareClass to CabinClass, defaulting to ECONOMY."""
    return _FARE_CLASS_MAP.get(fare_class_str.upper(), CabinClass.ECONOMY)


def parse_fares(
    raw: list[dict[str, Any]],
    *,
    origin_filter: str | None = None,
    destination_filter: str | None = None,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Japan Airlines Sputnik fare entries into NormalizedFlight list.

    Each entry in the raw list looks like::

        {
            "airline": {"iataCode": "JL"},
            "departureDate": "2026-04-15",
            "flightType": "INTERNATIONAL",
            "journeyType": "ONE_WAY",
            "outboundFlight": {
                "departureAirportIataCode": "NRT",
                "arrivalAirportIataCode": "ICN",
                "fareClass": "ECONOMY",
                "fareClassInput": "seat",
                ...
            },
            "priceSpecification": {
                "totalPrice": 150000.0,
                "currencyCode": "KRW",
                "soldOut": false,
                ...
            },
            "searchDate": "2026-02-15T10:00:00.000+0000",
            ...
        }

    Parameters
    ----------
    raw:
        List of fare entries from the Sputnik API.
    origin_filter:
        If set, only include fares departing from this IATA code.
    destination_filter:
        If set, only include fares arriving at this IATA code.
    cabin_class:
        Default cabin class if not specified in the fare entry.

    Returns
    -------
    list[NormalizedFlight]
        One ``NormalizedFlight`` per fare entry with ``price > 0``.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    for entry in raw:
        # Extract price information.
        price_spec = entry.get("priceSpecification", {})
        price_val = price_spec.get("totalPrice", 0)
        if not price_val or price_val <= 0:
            continue
        if price_spec.get("soldOut", False):
            continue

        currency: str = price_spec.get("currencyCode", "KRW")

        # Extract route information.
        outbound = entry.get("outboundFlight", {})
        dep_airport: str = outbound.get("departureAirportIataCode", "")
        arr_airport: str = outbound.get("arrivalAirportIataCode", "")
        if not dep_airport or not arr_airport:
            continue

        # Apply route filters.
        if origin_filter and dep_airport.upper() != origin_filter.upper():
            continue
        if destination_filter and arr_airport.upper() != destination_filter.upper():
            continue

        # Parse departure date.
        date_str = entry.get("departureDate", "")
        if not date_str:
            continue
        try:
            dep_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        except (ValueError, TypeError):
            logger.warning("Invalid date in JAL fare: %s", date_str)
            continue

        # Determine cabin class from fare entry or fallback.
        fare_class_str = outbound.get("fareClass", "")
        resolved_cabin = (
            _map_cabin_class(fare_class_str) if fare_class_str else cabin_class
        )

        # Build fare class label.
        fare_class_input = outbound.get("fareClassInput", "")
        fare_label = fare_class_str.lower()
        if fare_class_input:
            fare_label = f"{fare_label}-{fare_class_input}"

        price_obj = NormalizedPrice(
            amount=float(price_val),
            currency=currency,
            source=DataSource.DIRECT_CRAWL,
            fare_class=fare_label or "lowest",
            crawled_at=now,
        )

        flights.append(
            NormalizedFlight(
                flight_number=f"{_JL_CODE}-{dep_airport}{arr_airport}",
                airline_code=_JL_CODE,
                airline_name=_JL_NAME,
                operator=_JL_CODE,
                origin=dep_airport,
                destination=arr_airport,
                departure_time=dep_dt,
                arrival_time=dep_dt,
                duration_minutes=0,
                cabin_class=resolved_cabin,
                stops=0,
                prices=[price_obj],
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            ),
        )

    logger.info(
        "Parsed %d daily lowest fares for %s->%s from Japan Airlines",
        len(flights),
        origin_filter or "*",
        destination_filter or "*",
    )
    return flights
