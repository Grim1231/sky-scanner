"""Parse LOT Polish Airlines price box response into NormalizedFlight objects."""

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

_LOT_CODE = "LO"
_LOT_NAME = "LOT Polish Airlines"

# Map LOT cabin class codes to our CabinClass enum
_CABIN_MAP: dict[str, CabinClass] = {
    "E": CabinClass.ECONOMY,
    "P": CabinClass.PREMIUM_ECONOMY,
    "B": CabinClass.BUSINESS,
}


def parse_price_boxes(
    raw: dict[str, Any],
    origin: str,
    destination: str,
) -> list[NormalizedFlight]:
    """Convert LOT watchlistPriceBoxesSearch response into NormalizedFlight list.

    Each price box entry contains::

        {
            "originAirportIATA": "WAW",
            "destinationAirportIATA": "ICN",
            "cabinClassCode": "E",
            "cabinClassLabel": "Economy",
            "priceValue": "2485",
            "priceCurrency": "PLN",
            "tripTypeCode": "R",
            "tripTypeLabel": "RoundTrip",
            "bookerDepartureTime": "15-03-2026",
            "bookerReturnTime": "25-03-2026",
            "baggageCode": "H",
            "baggageLabel": "HandLuggage",
        }

    We create one ``NormalizedFlight`` per price box entry.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    boxes: list[dict[str, Any]] = raw.get("priceBoxes", [])

    for box in boxes:
        price_str = box.get("priceValue", "")
        if not price_str:
            continue

        try:
            price_val = float(price_str.replace(",", ""))
        except (ValueError, TypeError):
            logger.warning("Invalid price in LOT box: %s", price_str)
            continue

        if price_val <= 0:
            continue

        currency = box.get("priceCurrency", "PLN")
        dep_iata = box.get("originAirportIATA", origin)
        arr_iata = box.get("destinationAirportIATA", destination)
        cabin_code = box.get("cabinClassCode", "E")
        cabin_class = _CABIN_MAP.get(cabin_code, CabinClass.ECONOMY)
        trip_type = box.get("tripTypeCode", "R")
        dep_date_str = box.get("bookerDepartureTime", "")

        # Parse date: "15-03-2026" -> datetime
        try:
            dep_dt = datetime.strptime(dep_date_str, "%d-%m-%Y").replace(
                tzinfo=UTC,
            )
        except (ValueError, TypeError):
            logger.warning("Invalid date in LOT box: %s", dep_date_str)
            # Fall back to today
            dep_dt = datetime.now(tz=UTC).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )

        fare_class_parts = [
            box.get("cabinClassLabel", ""),
            box.get("baggageLabel", ""),
        ]
        fare_class = " / ".join(p for p in fare_class_parts if p) or "standard"

        # Indicate round-trip in fare class if applicable
        if trip_type == "R":
            fare_class = f"RT-{fare_class}"

        price_obj = NormalizedPrice(
            amount=price_val,
            currency=currency,
            source=DataSource.DIRECT_CRAWL,
            fare_class=fare_class,
            crawled_at=now,
        )

        flights.append(
            NormalizedFlight(
                flight_number=f"{_LOT_CODE}-{dep_iata}{arr_iata}",
                airline_code=_LOT_CODE,
                airline_name=_LOT_NAME,
                operator=_LOT_CODE,
                origin=dep_iata,
                destination=arr_iata,
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
        "Parsed %d price boxes for %s->%s from LOT Polish Airlines",
        len(flights),
        origin,
        destination,
    )
    return flights
