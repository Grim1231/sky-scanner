"""Parse Emirates featured-fares API response into NormalizedFlight objects.

The ``/service/featured-fares`` endpoint returns promotional fare cards
grouped by origin airport.  Each fare card contains:

- Origin and destination airport codes
- Fare price (formatted string, e.g. ``KRW 881,700*``)
- Currency code
- Cabin class code (Y/W/J/F)
- Travel period (from/until dates)
- Booking window (from/until dates)
- Ticket type (Return / One Way)

Since the featured-fares API returns promotional fares (not specific
flight availability), we create one ``NormalizedFlight`` per fare card
with a synthetic flight number ``EK-{origin}{destination}``.

Response structure::

    {
        "results": {
            "data": {
                "defaultAirport": {"code": "ICN", "title": "Seoul"},
                "fares": [
                    {
                        "code": "ICN",
                        "destinations": [
                            {
                                "code": "DXB",
                                "cityTitle": "Dubai",
                                "callOutPrice": "KRW 957,500",
                                "currencycode": "KRW",
                                "travelClassCode": "Y",
                                "travelClassTitle": "Economy",
                                "travelFrom": "09 Feb 26",
                                "travelUntil": "31 Aug 26",
                                "bookFrom": "2026-02-09",
                                "bookUntil": "2026-08-31",
                                "ticketType": "Return",
                                ...
                            }
                        ]
                    }
                ]
            }
        }
    }
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from sky_scanner_core.schemas import (
    CabinClass,
    DataSource,
    NormalizedFlight,
    NormalizedPrice,
)

logger = logging.getLogger(__name__)

_AIRLINE_CODE = "EK"
_AIRLINE_NAME = "Emirates"

# Map EK travelClassCode -> our CabinClass enum.
_CABIN_MAP: dict[str, CabinClass] = {
    "Y": CabinClass.ECONOMY,
    "W": CabinClass.PREMIUM_ECONOMY,
    "J": CabinClass.BUSINESS,
    "F": CabinClass.FIRST,
}

# Regex to extract numeric price from formatted strings like "KRW 881,700*"
_PRICE_RE = re.compile(r"[\d,.]+")


def _parse_price(price_str: str) -> float:
    """Extract numeric price from formatted price string.

    Handles formats like:
    - ``KRW 881,700*``
    - ``881,700*``
    - ``1,234.56``
    """
    match = _PRICE_RE.search(price_str.replace(",", ""))
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return 0.0


def _parse_travel_date(date_str: str) -> datetime:
    """Parse Emirates travel date format to UTC datetime.

    Handles formats:
    - ``09 Feb 26`` (DD MMM YY)
    - ``2026-02-09`` (ISO format)
    """
    if not date_str:
        return datetime.now(tz=UTC)

    # Try ISO format first
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        pass

    # Try "DD MMM YY" format
    for fmt in ("%d %b %y", "%d %b %Y"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue

    return datetime.now(tz=UTC)


def parse_featured_fares(
    data: dict[str, Any],
    *,
    origin_filter: str | None = None,
    destination_filter: str | None = None,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse Emirates featured-fares API response into NormalizedFlight list.

    Parameters
    ----------
    data:
        Raw API response JSON.
    origin_filter:
        If set, only include fares from this origin airport (IATA code).
    destination_filter:
        If set, only include fares to this destination airport (IATA code).
    cabin_class:
        Default cabin class if not determinable from fare data.

    Returns
    -------
    list[NormalizedFlight]
        One NormalizedFlight per fare card.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    results_data = data.get("results", {}).get("data", {})
    fares_by_origin: list[dict[str, Any]] = results_data.get("fares", [])

    for origin_group in fares_by_origin:
        origin = origin_group.get("code", "")
        if not origin:
            continue

        if origin_filter and origin.upper() != origin_filter.upper():
            continue

        destinations: list[dict[str, Any]] = origin_group.get("destinations", [])

        for dest in destinations:
            dest_code = dest.get("code", "")
            if not dest_code:
                continue

            if destination_filter and dest_code.upper() != destination_filter.upper():
                continue

            # Extract price.
            call_out_price = dest.get("callOutPrice", "")
            fare_price = dest.get("farePrice", call_out_price)
            price_amount = _parse_price(fare_price)

            if price_amount <= 0:
                continue

            currency = dest.get("currencycode", "KRW")

            # Cabin class from fare data.
            travel_class_code = dest.get("travelClassCode", "Y")
            mapped_cabin = _CABIN_MAP.get(travel_class_code, cabin_class)

            # Travel period.
            travel_from = _parse_travel_date(dest.get("travelFrom", ""))

            # Fare class from ticket type.
            ticket_type = dest.get("ticketType", "")
            fare_class = (
                f"featured-{ticket_type.lower()}" if ticket_type else "featured"
            )

            price_obj = NormalizedPrice(
                amount=price_amount,
                currency=currency,
                source=DataSource.DIRECT_CRAWL,
                fare_class=fare_class,
                crawled_at=now,
            )

            flights.append(
                NormalizedFlight(
                    flight_number=f"{_AIRLINE_CODE}-{origin}{dest_code}",
                    airline_code=_AIRLINE_CODE,
                    airline_name=_AIRLINE_NAME,
                    operator=_AIRLINE_CODE,
                    origin=origin,
                    destination=dest_code,
                    departure_time=travel_from,
                    arrival_time=travel_from,  # Not available from featured fares
                    duration_minutes=0,  # Not available from featured fares
                    cabin_class=mapped_cabin,
                    stops=0,  # Emirates operates direct from hubs
                    prices=[price_obj],
                    source=DataSource.DIRECT_CRAWL,
                    crawled_at=now,
                ),
            )

    logger.info(
        "Parsed %d featured fare entries from Emirates",
        len(flights),
    )
    return flights
