"""Parse Thai Airways L2 API responses into NormalizedFlight objects.

Handles two response formats:

1. **Sputnik fares** -- same EveryMundo format used by JL/NZ/ET crawlers.
   Each entry contains ``outboundFlight``, ``priceSpecification``, and
   ``departureDate`` fields.

2. **Popular-fares** -- the ``/common/calendarPricing/popular-fares``
   endpoint returns a ``prices`` list with route/date/fare entries.
   This reuses the same parsing logic from the L3 ``response_parser.py``
   Strategy 0.
"""

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

_TG_CODE = "TG"
_TG_NAME = "Thai Airways"

# Map Sputnik fareClass strings to CabinClass enum values.
_FARE_CLASS_MAP: dict[str, CabinClass] = {
    "ECONOMY": CabinClass.ECONOMY,
    "PREMIUM_ECONOMY": CabinClass.PREMIUM_ECONOMY,
    "PREMIUMECONOMY": CabinClass.PREMIUM_ECONOMY,
    "BUSINESS": CabinClass.BUSINESS,
    "FIRST": CabinClass.FIRST,
}

# Cabin class mapping for popular-fares responses.
_CABIN_MAP: dict[str, CabinClass] = {
    "Y": CabinClass.ECONOMY,
    "W": CabinClass.PREMIUM_ECONOMY,
    "C": CabinClass.BUSINESS,
    "J": CabinClass.BUSINESS,
    "F": CabinClass.FIRST,
    "ECONOMY": CabinClass.ECONOMY,
    "PREMIUM_ECONOMY": CabinClass.PREMIUM_ECONOMY,
    "PREMIUM": CabinClass.PREMIUM_ECONOMY,
    "BUSINESS": CabinClass.BUSINESS,
    "FIRST": CabinClass.FIRST,
    "M": CabinClass.ECONOMY,
    "P": CabinClass.PREMIUM_ECONOMY,
}


def _map_cabin_class(fare_class_str: str) -> CabinClass:
    """Convert Sputnik fareClass to CabinClass, defaulting to ECONOMY."""
    return _FARE_CLASS_MAP.get(fare_class_str.upper(), CabinClass.ECONOMY)


def _parse_price_string(price_str: str) -> float:
    """Parse a formatted price string like ``"317,300"`` to float."""
    cleaned = price_str.replace(",", "").replace(" ", "").strip()
    return float(cleaned)


# ------------------------------------------------------------------
# Sputnik fare parsing
# ------------------------------------------------------------------


def parse_sputnik_fares(
    raw: list[dict[str, Any]],
    *,
    origin_filter: str | None = None,
    destination_filter: str | None = None,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Thai Airways Sputnik fare entries into NormalizedFlight list.

    Each entry in the raw list looks like::

        {
            "airline": {"iataCode": "TG"},
            "departureDate": "2026-04-15",
            "flightType": "INTERNATIONAL",
            "journeyType": "ONE_WAY",
            "outboundFlight": {
                "departureAirportIataCode": "ICN",
                "arrivalAirportIataCode": "BKK",
                "fareClass": "ECONOMY",
                "fareClassInput": "seat",
                ...
            },
            "priceSpecification": {
                "totalPrice": 317300.0,
                "currencyCode": "KRW",
                "soldOut": false,
                ...
            },
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
            logger.warning("Invalid date in TG Sputnik fare: %s", date_str)
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
                flight_number=f"{_TG_CODE}-{dep_airport}{arr_airport}",
                airline_code=_TG_CODE,
                airline_name=_TG_NAME,
                operator=_TG_CODE,
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
        "Parsed %d Sputnik fares for %s->%s from Thai Airways",
        len(flights),
        origin_filter or "*",
        destination_filter or "*",
    )
    return flights


# ------------------------------------------------------------------
# Popular-fares parsing
# ------------------------------------------------------------------


def parse_popular_fares(
    data: dict[str, Any],
    *,
    origin_filter: str | None = None,
    destination_filter: str | None = None,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse the ``/common/calendarPricing/popular-fares`` response.

    Each entry in ``prices`` represents the cheapest fare for a route
    on a specific date.  Optionally filters to entries matching the
    requested origin and destination.

    Parameters
    ----------
    data:
        Raw JSON response from the popular-fares endpoint.
    origin_filter:
        If set, only include fares departing from this IATA code.
    destination_filter:
        If set, only include fares arriving at this IATA code.
    cabin_class:
        Default cabin class if not specified in the fare entry.

    Returns
    -------
    list[NormalizedFlight]
        One ``NormalizedFlight`` per price entry with valid amount.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    prices = data.get("prices")
    if not isinstance(prices, list) or not prices:
        return flights

    for entry in prices:
        if not isinstance(entry, dict):
            continue

        dep_iata = entry.get("departureAirportIataCode", "")
        arr_iata = entry.get("arrivalAirportIataCode", "")

        # Apply route filters.
        if origin_filter and dep_iata.upper() != origin_filter.upper():
            continue
        if destination_filter and arr_iata.upper() != destination_filter.upper():
            continue

        date_str = entry.get("date", "")
        if not date_str:
            continue
        try:
            dep_time = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        except (ValueError, TypeError):
            logger.warning("Invalid date in TG popular-fares: %s", date_str)
            continue

        fare = entry.get("fare")
        if not isinstance(fare, dict):
            continue

        total_price_str = fare.get("totalPrice", "")
        if not total_price_str:
            continue

        try:
            amount = _parse_price_string(str(total_price_str))
        except (ValueError, TypeError):
            continue

        if amount <= 0:
            continue

        currency = fare.get("currencyCode", "KRW")
        fare_class_str = fare.get("fareClass", "")
        parsed_cabin = _CABIN_MAP.get(fare_class_str.upper(), cabin_class)

        flights.append(
            NormalizedFlight(
                flight_number=f"{_TG_CODE}-{dep_iata}{arr_iata}",
                airline_code=_TG_CODE,
                airline_name=_TG_NAME,
                operator=_TG_CODE,
                origin=dep_iata,
                destination=arr_iata,
                departure_time=dep_time,
                arrival_time=dep_time,
                duration_minutes=0,
                cabin_class=parsed_cabin,
                stops=0,
                prices=[
                    NormalizedPrice(
                        amount=amount,
                        currency=currency,
                        source=DataSource.DIRECT_CRAWL,
                        fare_class=fare_class_str or None,
                        crawled_at=now,
                    )
                ],
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    if flights:
        logger.debug(
            "TG: parsed %d popular-fares entries for %s->%s",
            len(flights),
            origin_filter or "*",
            destination_filter or "*",
        )

    return flights
