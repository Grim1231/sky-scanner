"""Parse Air France-KLM Aviato GraphQL responses into NormalizedFlight objects.

The GraphQL ``SearchResultAvailableOffersQuery`` response contains
``offerItineraries`` each with an ``activeConnection`` holding segments
and ``upsellCabinProducts`` holding prices per cabin class.

Response structure (simplified)::

    {
        "data": {
            "availableOffers": {
                "offerItineraries": [
                    {
                        "activeConnection": {
                            "duration": 720,
                            "isDirect": true,
                            "segments": [
                                {
                                    "marketingFlight": {
                                        "carrier": {"code": "KL"},
                                        "number": "0855",
                                        "operatingFlight": {
                                            "carrier": {"code": "KL", "name": "KLM"}
                                        },
                                    },
                                    "origin": {
                                        "code": "AMS",
                                        "city": {"name": "Amsterdam"},
                                    },
                                    "destination": {
                                        "code": "ICN",
                                        "city": {"name": "Seoul"},
                                    },
                                    "departureDateTime": "2026-04-15T21:25:00",
                                    "arrivalDateTime": "2026-04-16T16:25:00",
                                    "duration": 720,
                                    "equipmentName": "Boeing 787-9",
                                }
                            ],
                        },
                        "upsellCabinProducts": [
                            {
                                "connections": [
                                    {
                                        "cabinClass": "ECONOMY",
                                        "fareFamily": {"code": "LIGHTLH"},
                                        "price": {
                                            "amount": 1509.5,
                                            "currencyCode": "USD",
                                        },
                                        "numberOfSeatsAvailable": 9,
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        }
    }
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

from .sputnik_client import AIRLINE_NAMES

logger = logging.getLogger(__name__)

# Map GraphQL cabinClass strings to our CabinClass enum.
_CABIN_MAP: dict[str, CabinClass] = {
    "ECONOMY": CabinClass.ECONOMY,
    "PREMIUM": CabinClass.PREMIUM_ECONOMY,
    "PREMIUM_ECONOMY": CabinClass.PREMIUM_ECONOMY,
    "BUSINESS": CabinClass.BUSINESS,
    "FIRST": CabinClass.FIRST,
}


def _parse_dt(dt_str: str) -> datetime:
    """Parse an ISO datetime string to a timezone-aware UTC datetime.

    The Aviato API returns local times without timezone info
    (e.g. ``2026-04-15T21:25:00``).  We treat them as UTC for
    consistency across crawlers.
    """
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return datetime.now(tz=UTC)


def parse_available_offers(
    data: dict[str, Any],
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse ``SearchResultAvailableOffersQuery`` response into NormalizedFlights."""
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    available = data.get("data", {}).get("availableOffers", {})
    itineraries = available.get("offerItineraries", [])

    for itin in itineraries:
        conn = itin.get("activeConnection", {})
        segments: list[dict[str, Any]] = conn.get("segments", [])
        if not segments:
            continue

        first_seg = segments[0]
        last_seg = segments[-1]

        # Origin / destination from first/last segment.
        origin = first_seg.get("origin", {}).get("code", "")
        destination = last_seg.get("destination", {}).get("code", "")

        # Departure / arrival times.
        dep_str = first_seg.get("departureDateTime", "")
        arr_str = last_seg.get("arrivalDateTime", "")
        dep_time = _parse_dt(dep_str)
        arr_time = _parse_dt(arr_str)

        # Duration from connection level (in minutes).
        duration_minutes: int = conn.get("duration", 0)
        if not duration_minutes and dep_time and arr_time:
            duration_minutes = int((arr_time - dep_time).total_seconds() / 60)

        # Flight identity from first segment marketing flight.
        mkt_flight = first_seg.get("marketingFlight", {})
        carrier_code = mkt_flight.get("carrier", {}).get("code", "")
        flight_num = mkt_flight.get("number", "")
        flight_number = f"{carrier_code}{flight_num}"

        # Operating carrier.
        op_flight = mkt_flight.get("operatingFlight", {})
        op_carrier = op_flight.get("carrier", {}).get("code", carrier_code)
        op_carrier_name = op_flight.get("carrier", {}).get("name")

        # Equipment.
        equipment = first_seg.get("equipmentName")

        # Stops.
        stops = len(segments) - 1

        airline_name = op_carrier_name or AIRLINE_NAMES.get(carrier_code)

        # Prices from upsellCabinProducts (preferred) or flightProducts.
        prices: list[NormalizedPrice] = []
        products = itin.get("upsellCabinProducts", itin.get("flightProducts", []))

        for product in products:
            conns = product.get("connections", [])
            if not conns:
                continue
            conn_info = conns[0]

            amount_data = conn_info.get("price", {})
            amount = amount_data.get("amount")
            if amount is None:
                continue

            currency = amount_data.get("currencyCode", "USD")

            fare_family = conn_info.get("fareFamily", {})
            fare_code = fare_family.get("code") if fare_family else None

            # Only include prices matching the requested cabin class
            # or any cabin class (we provide multi-cabin data).
            prices.append(
                NormalizedPrice(
                    amount=float(amount),
                    currency=currency,
                    source=DataSource.DIRECT_CRAWL,
                    fare_class=fare_code,
                    crawled_at=now,
                )
            )

        # Determine the primary cabin from the first matching product.
        primary_cabin = cabin_class
        for product in products:
            conns = product.get("connections", [])
            if conns:
                product_cabin = conns[0].get("cabinClass", "")
                mapped = _CABIN_MAP.get(product_cabin.upper())
                if mapped == cabin_class:
                    primary_cabin = mapped
                    break

        flights.append(
            NormalizedFlight(
                flight_number=flight_number,
                airline_code=carrier_code,
                airline_name=airline_name,
                operator=op_carrier,
                origin=origin,
                destination=destination,
                departure_time=dep_time,
                arrival_time=arr_time,
                duration_minutes=duration_minutes,
                cabin_class=primary_cabin,
                aircraft_type=equipment,
                stops=stops,
                prices=prices,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    logger.info(
        "Parsed %d flights from AF-KLM GraphQL available-offers",
        len(flights),
    )
    return flights
