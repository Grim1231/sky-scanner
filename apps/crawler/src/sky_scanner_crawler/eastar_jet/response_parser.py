"""Parse Eastar Jet daily low fare response into NormalizedFlight objects."""

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

_EASTAR_CODE = "ZE"
_EASTAR_NAME = "Eastar Jet"


def parse_daily_low_fares(
    raw: dict,
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Eastar Jet dailyLowFare response into NormalizedFlight list.

    The daily-low-fare API returns one fare per day (the cheapest available).
    Each day is mapped to a single ``NormalizedFlight`` with:
    - ``flight_number`` = ``ZE-{origin}{destination}`` (synthetic, no individual flight)
    - ``departure_time`` / ``arrival_time`` set to the departure date at 00:00 UTC
    - ``duration_minutes`` = 0 (not provided by the calendar API)
    - ``price`` = totalPrice (includes taxes and fees)
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    fare_data = raw.get("data", {})
    if not fare_data:
        return flights

    currency = fare_data.get("currencyCode", "KRW")
    api_origin = fare_data.get("origin", origin)
    api_dest = fare_data.get("destination", destination)
    amounts: list[dict] = fare_data.get("lowFareAmounts", [])

    for entry in amounts:
        total_price = entry.get("totalPrice", 0)
        if not total_price or total_price <= 0:
            continue

        dept_date_str = entry.get("deptDate", "")
        try:
            dep_dt = datetime.fromisoformat(dept_date_str).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            logger.warning("Invalid departure date: %s", dept_date_str)
            continue

        price_obj = NormalizedPrice(
            amount=float(total_price),
            currency=currency,
            source=DataSource.DIRECT_CRAWL,
            fare_class="lowest",
            crawled_at=now,
        )

        flights.append(
            NormalizedFlight(
                flight_number=f"{_EASTAR_CODE}-{api_origin}{api_dest}",
                airline_code=_EASTAR_CODE,
                airline_name=_EASTAR_NAME,
                operator=_EASTAR_CODE,
                origin=api_origin,
                destination=api_dest,
                departure_time=dep_dt,
                arrival_time=dep_dt,  # not available from calendar API
                duration_minutes=0,
                cabin_class=cabin_class,
                stops=0,  # Eastar Jet operates direct flights
                prices=[price_obj],
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            ),
        )

    logger.info(
        "Parsed %d daily lowest fares for %s→%s from Eastar Jet",
        len(flights),
        origin,
        destination,
    )
    return flights
