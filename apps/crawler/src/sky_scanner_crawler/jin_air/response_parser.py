"""Parse Jin Air S3 fare bucket data into NormalizedFlight objects."""

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

_JIN_AIR_CODE = "LJ"
_JIN_AIR_NAME = "Jin Air"


def parse_total_fares(
    raw: list[dict[str, int]],
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
    currency: str = "KRW",
) -> list[NormalizedFlight]:
    """Convert Jin Air S3 fare data into NormalizedFlight list.

    The S3 bucket stores pre-computed daily lowest fares as
    ``[{"YYYYMMDD": price}, ...]``.  Each entry becomes one
    ``NormalizedFlight`` (synthetic — no individual flight info).
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    for entry in raw:
        for date_str, price_val in entry.items():
            if not date_str or not isinstance(price_val, (int, float)):
                continue
            if price_val <= 0:
                continue

            try:
                dep_dt = datetime(
                    int(date_str[:4]),
                    int(date_str[4:6]),
                    int(date_str[6:8]),
                    tzinfo=UTC,
                )
            except (ValueError, IndexError):
                logger.warning("Invalid date in Jin Air fare: %s", date_str)
                continue

            price_obj = NormalizedPrice(
                amount=float(price_val),
                currency=currency,
                source=DataSource.DIRECT_CRAWL,
                fare_class="lowest",
                crawled_at=now,
            )

            flights.append(
                NormalizedFlight(
                    flight_number=f"{_JIN_AIR_CODE}-{origin}{destination}",
                    airline_code=_JIN_AIR_CODE,
                    airline_name=_JIN_AIR_NAME,
                    operator=_JIN_AIR_CODE,
                    origin=origin,
                    destination=destination,
                    departure_time=dep_dt,
                    arrival_time=dep_dt,
                    duration_minutes=0,
                    cabin_class=cabin_class,
                    stops=0,
                    prices=[price_obj],
                    source=DataSource.DIRECT_CRAWL,
                    crawled_at=now,
                ),
            )

    logger.info(
        "Parsed %d daily lowest fares for %s→%s from Jin Air",
        len(flights),
        origin,
        destination,
    )
    return flights
