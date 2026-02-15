"""Parse EVA Air getBestPrices response into NormalizedFlight objects."""

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

_EVA_CODE = "BR"
_EVA_NAME = "EVA Air"


def parse_best_prices(
    raw: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert EVA Air getBestPrices response into NormalizedFlight list.

    The API returns up to ~300 days of daily lowest one-way fares::

        {
            "Data": {
                "currency": "TWD",
                "data": [
                    {"date": "2026-02-15T00:00:00", "price": 16825, "highlight": false},
                    ...,
                ],
            }
        }

    Each entry with ``price > 0`` becomes one ``NormalizedFlight``
    (synthetic -- no individual flight details, only daily lowest).
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    data_wrapper = raw.get("Data")
    if not data_wrapper:
        return flights

    currency: str = data_wrapper.get("currency", "TWD")
    entries: list[dict[str, Any]] = data_wrapper.get("data", [])

    for entry in entries:
        price_val = entry.get("price", 0)
        if not price_val or price_val <= 0:
            continue

        date_str = entry.get("date", "")
        if not date_str:
            continue

        try:
            # Format: "2026-02-15T00:00:00"
            dep_dt = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            logger.warning("Invalid date in EVA fare: %s", date_str)
            continue

        fare_class = "lowest-highlight" if entry.get("highlight") else "lowest"

        price_obj = NormalizedPrice(
            amount=float(price_val),
            currency=currency,
            source=DataSource.DIRECT_CRAWL,
            fare_class=fare_class,
            crawled_at=now,
        )

        flights.append(
            NormalizedFlight(
                flight_number=f"{_EVA_CODE}-{origin}{destination}",
                airline_code=_EVA_CODE,
                airline_name=_EVA_NAME,
                operator=_EVA_CODE,
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
        "Parsed %d daily lowest fares for %s->%s from EVA Air (%s)",
        len(flights),
        origin,
        destination,
        currency,
    )
    return flights
