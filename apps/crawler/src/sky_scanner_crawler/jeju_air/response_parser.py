"""Parse Jeju Air lowest-fare calendar response into NormalizedFlight objects."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sky_scanner_core.schemas import (
    CabinClass,
    DataSource,
    NormalizedFlight,
    NormalizedPrice,
)

logger = logging.getLogger(__name__)

_JEJU_AIR_CODE = "7C"
_JEJU_AIR_NAME = "Jeju Air"


def parse_lowest_fares(
    raw: dict,
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Jeju Air lowest-fare calendar response into NormalizedFlight list.

    The lowest-fare API returns one fare per day (the cheapest available).
    Each day is mapped to a single ``NormalizedFlight`` with:
    - ``flight_number`` = ``7C-{origin}{destination}`` (synthetic, no individual flight)
    - ``departure_time`` / ``arrival_time`` set to the departure date at 00:00 UTC
    - ``duration_minutes`` = 0 (not provided by the calendar API)
    - ``price`` = fareAmount + taxesAndFeesAmount

    This gives our system daily price signals for Jeju Air routes.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    lowfares = raw.get("data", {}).get("lowfares", {})
    currency = lowfares.get("currencyCode", "KRW")
    markets: list[dict] = lowfares.get("lowFareDateMarkets", [])

    for market in markets:
        if market.get("noFlights"):
            continue

        fare_info = market.get("lowestFareAmount", {})
        fare_amount = fare_info.get("fareAmount", 0)
        tax_amount = fare_info.get("taxesAndFeesAmount", 0)
        total_price = fare_amount + tax_amount

        if total_price <= 0:
            continue

        # Parse departure date (format: "2026-03-01T00:00:00")
        dep_date_str = market.get("departureDate", "")
        try:
            dep_dt = datetime.fromisoformat(dep_date_str).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            logger.warning("Invalid departure date: %s", dep_date_str)
            continue

        mkt_origin = market.get("origin", origin)
        mkt_dest = market.get("destination", destination)

        price_obj = NormalizedPrice(
            amount=float(total_price),
            currency=currency,
            source=DataSource.DIRECT_CRAWL,
            fare_class="lowest",
            crawled_at=now,
        )

        flights.append(
            NormalizedFlight(
                flight_number=f"{_JEJU_AIR_CODE}-{mkt_origin}{mkt_dest}",
                airline_code=_JEJU_AIR_CODE,
                airline_name=_JEJU_AIR_NAME,
                operator=_JEJU_AIR_CODE,
                origin=mkt_origin,
                destination=mkt_dest,
                departure_time=dep_dt,
                arrival_time=dep_dt,  # not available from calendar API
                duration_minutes=0,
                cabin_class=cabin_class,
                stops=0,  # Jeju Air operates direct flights
                prices=[price_obj],
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            ),
        )

    logger.info(
        "Parsed %d daily lowest fares for %s→%s from Jeju Air",
        len(flights),
        origin,
        destination,
    )
    return flights
