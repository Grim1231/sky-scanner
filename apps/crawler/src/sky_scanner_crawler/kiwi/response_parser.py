"""Parse a Kiwi Tequila /v2/search response into NormalizedFlight objects."""

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


def _epoch_to_utc(ts: int | float) -> datetime:
    """Convert a Unix epoch timestamp to a timezone-aware UTC datetime."""
    return datetime.fromtimestamp(ts, tz=UTC)


def _duration_minutes(dep_ts: int | float, arr_ts: int | float) -> int:
    return max(int((arr_ts - dep_ts) / 60), 0)


def parse_kiwi_response(
    raw: dict,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Kiwi ``data[]`` items into a flat list of :class:`NormalizedFlight`.

    Each *route segment* within an itinerary becomes its own NormalizedFlight
    so that per-leg data is preserved.  The itinerary-level price is attached
    to every segment (Kiwi only gives one price for the whole itinerary).
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    for itinerary in raw.get("data", []):
        itinerary_price = itinerary.get("price")
        deep_link: str | None = itinerary.get("deep_link")
        bags_price: dict = itinerary.get("bags_price", {})
        includes_baggage = bool(bags_price.get("1") == 0 or bags_price.get(1) == 0)

        price_obj = NormalizedPrice(
            amount=float(itinerary_price),
            currency=itinerary.get("countryTo", {}).get("cur", "KRW")
            if isinstance(itinerary.get("countryTo"), dict)
            else "KRW",
            source=DataSource.KIWI_API,
            booking_url=deep_link,
            includes_baggage=includes_baggage,
            crawled_at=now,
        )

        route: list[dict] = itinerary.get("route", [])
        if not route:
            # Fallback: treat the whole itinerary as a single flight
            airlines = itinerary.get("airlines", [""])
            airline_code = airlines[0] if airlines else ""
            route = [
                {
                    "flyFrom": itinerary.get("flyFrom", ""),
                    "flyTo": itinerary.get("flyTo", ""),
                    "dTime": itinerary.get("dTime", 0),
                    "aTime": itinerary.get("aTime", 0),
                    "airline": airline_code,
                    "flight_no": 0,
                    "operating_carrier": airline_code,
                },
            ]

        for seg in route:
            airline_code = seg.get("airline", "")
            flight_no_raw = seg.get("flight_no", 0)
            flight_number = f"{airline_code}{flight_no_raw}"

            dep_ts = seg.get("dTime", 0)
            arr_ts = seg.get("aTime", 0)

            flights.append(
                NormalizedFlight(
                    flight_number=flight_number,
                    airline_code=airline_code,
                    operator=seg.get("operating_carrier") or airline_code,
                    origin=seg.get("flyFrom", ""),
                    destination=seg.get("flyTo", ""),
                    departure_time=_epoch_to_utc(dep_ts),
                    arrival_time=_epoch_to_utc(arr_ts),
                    duration_minutes=_duration_minutes(dep_ts, arr_ts),
                    cabin_class=cabin_class,
                    prices=[price_obj],
                    source=DataSource.KIWI_API,
                    crawled_at=now,
                ),
            )

    logger.info("Parsed %d flight segments from Kiwi response", len(flights))
    return flights
