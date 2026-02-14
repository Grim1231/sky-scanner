"""Parse Air Premia low-fare response into NormalizedFlight objects."""

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

_PREMIA_CODE = "YP"
_PREMIA_NAME = "Air Premia"

# Air Premia cabin class mapping
_CABIN_MAP: dict[str, CabinClass] = {
    "EY": CabinClass.ECONOMY,
    "PE": CabinClass.PREMIUM_ECONOMY,
    "PF": CabinClass.BUSINESS,  # Premia First ≈ Business
}


def parse_low_fares(
    raw: dict,
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Air Premia low-fares response into NormalizedFlight list.

    The low-fares API returns per-day, per-cabin-class lowest fares.
    Each day+cabin combination is mapped to a ``NormalizedFlight`` with:
    - ``flight_number`` = ``YP-{origin}{destination}``
    - ``departure_time`` set to the date at 00:00 UTC
    - ``price`` = baseFareAndTax (includes taxes and fees)
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    results: list[dict] = raw.get("results", [])
    if not results:
        return flights

    for result in results:
        api_origin = result.get("origin", origin)
        api_dest = result.get("destination", destination)
        availabilities: list[dict] = result.get("dailyLowFareAvailabilities", [])

        for day in availabilities:
            if day.get("soldOut") or day.get("noFlights"):
                continue

            date_str = day.get("date", "")
            try:
                dep_dt = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except (ValueError, TypeError):
                logger.warning("Invalid date: %s", date_str)
                continue

            low_fares: list[dict] = day.get("lowFares", [])
            for fare in low_fares:
                product_class_type = fare.get("productClassType", "EY")
                fare_cabin = _CABIN_MAP.get(product_class_type, CabinClass.ECONOMY)

                # Filter by requested cabin class
                if fare_cabin != cabin_class:
                    continue

                total_price = fare.get("baseFareAndTax", 0)
                if total_price <= 0:
                    continue

                price_obj = NormalizedPrice(
                    amount=float(total_price),
                    currency="KRW",
                    source=DataSource.DIRECT_CRAWL,
                    fare_class=fare.get("productClass", ""),
                    crawled_at=now,
                )

                flights.append(
                    NormalizedFlight(
                        flight_number=f"{_PREMIA_CODE}-{api_origin}{api_dest}",
                        airline_code=_PREMIA_CODE,
                        airline_name=_PREMIA_NAME,
                        operator=_PREMIA_CODE,
                        origin=api_origin,
                        destination=api_dest,
                        departure_time=dep_dt,
                        arrival_time=dep_dt,
                        duration_minutes=0,
                        cabin_class=fare_cabin,
                        stops=0,
                        prices=[price_obj],
                        source=DataSource.DIRECT_CRAWL,
                        crawled_at=now,
                    ),
                )

    logger.info(
        "Parsed %d daily lowest fares for %s→%s from Air Premia",
        len(flights),
        origin,
        destination,
    )
    return flights
