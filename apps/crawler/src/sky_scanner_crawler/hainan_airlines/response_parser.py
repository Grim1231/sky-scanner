"""Parse Hainan Airlines fare-trends response into NormalizedFlight objects."""

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

_HAINAN_CODE = "HU"
_HAINAN_NAME = "Hainan Airlines"


def parse_fare_trends(
    raw: dict,
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Hainan Airlines fare-trends response into NormalizedFlight list.

    The fare-trends API returns one fare per day (the cheapest available)
    over a ~136-day window.  Each day is mapped to a single
    ``NormalizedFlight`` with:

    - ``flight_number`` = ``HU-{origin}{destination}`` (synthetic; no
      individual flight info from the calendar API)
    - ``departure_time`` / ``arrival_time`` set to the departure date at
      00:00 UTC
    - ``duration_minutes`` = 0 (not provided by the calendar API)
    - ``price`` in **CNY** (the only currency returned by this endpoint)

    Parameters
    ----------
    raw:
        Full JSON response from ``airFareTrends``.
    origin:
        3-letter IATA origin code.
    destination:
        3-letter IATA destination code.
    cabin_class:
        Cabin class for the search.

    Returns
    -------
    list[NormalizedFlight]
        One flight per day with the lowest fare.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    inner = raw.get("data", {})
    # Note: the API misspells "calendar" as "calandar".
    calendar: list[dict] = inner.get("priceCalandar", [])

    api_origin = inner.get("orgCode", origin)
    api_dest = inner.get("dstCode", destination)

    for entry in calendar:
        day_str = entry.get("day", "")
        price_str = entry.get("price", "")

        if not day_str or not price_str:
            continue

        try:
            price_amount = float(price_str)
        except (ValueError, TypeError):
            logger.warning("Invalid price value: %s", price_str)
            continue

        if price_amount <= 0:
            continue

        # day format: "YYYYMMDD" -> parse to datetime
        try:
            dep_dt = datetime.strptime(day_str, "%Y%m%d").replace(tzinfo=UTC)
        except ValueError:
            logger.warning("Invalid date format: %s", day_str)
            continue

        price_obj = NormalizedPrice(
            amount=price_amount,
            currency="CNY",
            source=DataSource.DIRECT_CRAWL,
            fare_class="lowest",
            crawled_at=now,
        )

        flights.append(
            NormalizedFlight(
                flight_number=f"{_HAINAN_CODE}-{api_origin}{api_dest}",
                airline_code=_HAINAN_CODE,
                airline_name=_HAINAN_NAME,
                operator=_HAINAN_CODE,
                origin=api_origin,
                destination=api_dest,
                departure_time=dep_dt,
                arrival_time=dep_dt,  # not available from calendar API
                duration_minutes=0,
                cabin_class=cabin_class,
                stops=0,  # fare-trends doesn't indicate stops
                prices=[price_obj],
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            ),
        )

    logger.info(
        "Parsed %d daily lowest fares for %s->%s from Hainan Airlines",
        len(flights),
        origin,
        destination,
    )
    return flights
