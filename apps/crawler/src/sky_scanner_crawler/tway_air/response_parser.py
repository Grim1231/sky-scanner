"""Parse T'way Air getLowestFare response into NormalizedFlight objects."""

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

_TWAY_CODE = "TW"
_TWAY_NAME = "T'way Air"


def parse_lowest_fares(
    raw: dict,
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
    currency: str = "KRW",
) -> list[NormalizedFlight]:
    """Convert T'way getLowestFare response into NormalizedFlight list.

    Each entry in the ``OW`` dict is a pipe-delimited string::

        (
            YYYYMMDD
            | dep
            | arr
            | soldOut
            | bizSoldOut
            | operating
            | bizOp
            | fare
            | totalFare
            | fareClass
        )

    We create one ``NormalizedFlight`` per operating, non-sold-out date.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    ow_data: dict[str, str] = raw.get("OW", {})

    for _date_key, fare_str in ow_data.items():
        if not fare_str:
            continue

        parts = fare_str.split("|")
        if len(parts) < 9:
            continue

        date_str = parts[0]
        dep = parts[1] or origin
        arr = parts[2] or destination
        sold_out = parts[3] == "Y"
        operating = parts[5] == "Y"
        fare_class = parts[9] if len(parts) > 9 else ""

        if not operating or sold_out:
            continue

        try:
            total_fare = float(parts[8])
        except (ValueError, IndexError):
            continue

        if total_fare <= 0:
            continue

        try:
            dep_dt = datetime(
                int(date_str[:4]),
                int(date_str[4:6]),
                int(date_str[6:8]),
                tzinfo=UTC,
            )
        except (ValueError, IndexError):
            logger.warning("Invalid date in T'way fare: %s", date_str)
            continue

        price_obj = NormalizedPrice(
            amount=total_fare,
            currency=currency,
            source=DataSource.DIRECT_CRAWL,
            fare_class=fare_class or "lowest",
            crawled_at=now,
        )

        flights.append(
            NormalizedFlight(
                flight_number=f"{_TWAY_CODE}-{dep}{arr}",
                airline_code=_TWAY_CODE,
                airline_name=_TWAY_NAME,
                operator=_TWAY_CODE,
                origin=dep,
                destination=arr,
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
        "Parsed %d daily lowest fares for %s→%s from T'way Air",
        len(flights),
        origin,
        destination,
    )
    return flights
