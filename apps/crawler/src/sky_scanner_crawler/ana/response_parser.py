"""Parse ANA flight search results into NormalizedFlight objects.

ANA's booking engine (aswbe.ana.co.jp) returns flight data in JSON format
when the search form is submitted.  The exact response schema varies, but
typically includes itinerary segments with:
- Flight number (e.g. NH211)
- Origin/destination IATA codes
- Departure/arrival times (ISO 8601 or ``HH:MM`` local)
- Duration
- Aircraft type
- Fare/price information

This parser also handles DOM-scraped flight cards as a fallback when
API interception does not capture structured JSON.
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

_ANA_CODE = "NH"
_ANA_NAME = "All Nippon Airways"

# ANA cabin class mapping.
_CABIN_MAP: dict[str, CabinClass] = {
    "Y": CabinClass.ECONOMY,
    "W": CabinClass.PREMIUM_ECONOMY,
    "C": CabinClass.BUSINESS,
    "F": CabinClass.FIRST,
    "ECONOMY": CabinClass.ECONOMY,
    "PREMIUM_ECONOMY": CabinClass.PREMIUM_ECONOMY,
    "PREMIUM ECONOMY": CabinClass.PREMIUM_ECONOMY,
    "BUSINESS": CabinClass.BUSINESS,
    "FIRST": CabinClass.FIRST,
}


def _parse_time(
    time_str: str | None,
    dep_date: str,
) -> datetime | None:
    """Parse a time string into a timezone-aware datetime.

    Handles formats: ``HH:MM``, ``YYYY-MM-DDTHH:MM``, ISO 8601.
    Falls back to midnight UTC on the departure date.
    """
    if not time_str:
        return None

    # Full ISO 8601.
    try:
        dt = datetime.fromisoformat(time_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        pass

    # HH:MM format -- combine with departure date.
    match = re.match(r"(\d{1,2}):(\d{2})", time_str)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        try:
            base = datetime.fromisoformat(dep_date).replace(tzinfo=UTC)
            return base.replace(hour=hour, minute=minute)
        except (ValueError, TypeError):
            pass

    return None


def _parse_duration_minutes(
    dep_dt: datetime,
    arr_dt: datetime,
) -> int:
    """Calculate flight duration in minutes."""
    delta = arr_dt - dep_dt
    minutes = int(delta.total_seconds() / 60)
    # Handle next-day arrivals producing negative durations.
    if minutes < 0:
        minutes += 24 * 60
    return max(minutes, 0)


def _extract_price(raw: Any) -> float | None:
    """Extract a numeric price from various formats."""
    if isinstance(raw, int | float) and raw > 0:
        return float(raw)
    if isinstance(raw, str):
        cleaned = re.sub(r"[^\d.]", "", raw)
        if cleaned:
            try:
                val = float(cleaned)
                return val if val > 0 else None
            except ValueError:
                pass
    return None


def parse_api_responses(
    api_responses: list[dict[str, Any]],
    origin: str,
    destination: str,
    departure_date: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse flights from intercepted API JSON responses.

    Looks for flight data in various response structures that the ANA
    booking engine may return.  The exact keys are best-effort since
    the API is not publicly documented.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    for resp in api_responses:
        # Try common response structures.
        _extract_from_dict(
            resp,
            flights,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            cabin_class=cabin_class,
            now=now,
        )

    logger.info(
        "ANA API parser: extracted %d flights from %d responses for %s->%s",
        len(flights),
        len(api_responses),
        origin,
        destination,
    )
    return flights


def _extract_from_dict(
    data: dict[str, Any],
    flights: list[NormalizedFlight],
    *,
    origin: str,
    destination: str,
    departure_date: str,
    cabin_class: CabinClass,
    now: datetime,
) -> None:
    """Recursively search a dict for flight segment data."""
    # Pattern 1: ANA booking engine "flightList" / "flights" / "segments".
    for key in ("flightList", "flights", "segments", "itineraries", "results"):
        items = data.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    flight = _try_parse_segment(
                        item,
                        origin=origin,
                        destination=destination,
                        departure_date=departure_date,
                        cabin_class=cabin_class,
                        now=now,
                    )
                    if flight:
                        flights.append(flight)

    # Pattern 2: nested "data" wrapper.
    nested_data = data.get("data")
    if isinstance(nested_data, dict):
        _extract_from_dict(
            nested_data,
            flights,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            cabin_class=cabin_class,
            now=now,
        )
    elif isinstance(nested_data, list):
        for item in nested_data:
            if isinstance(item, dict):
                _extract_from_dict(
                    item,
                    flights,
                    origin=origin,
                    destination=destination,
                    departure_date=departure_date,
                    cabin_class=cabin_class,
                    now=now,
                )

    # Pattern 3: "outbound" / "inbound" structure.
    for direction in ("outbound", "inbound", "outboundFlights", "inboundFlights"):
        direction_data = data.get(direction)
        if isinstance(direction_data, list):
            for item in direction_data:
                if isinstance(item, dict):
                    flight = _try_parse_segment(
                        item,
                        origin=origin,
                        destination=destination,
                        departure_date=departure_date,
                        cabin_class=cabin_class,
                        now=now,
                    )
                    if flight:
                        flights.append(flight)


def _try_parse_segment(
    seg: dict[str, Any],
    *,
    origin: str,
    destination: str,
    departure_date: str,
    cabin_class: CabinClass,
    now: datetime,
) -> NormalizedFlight | None:
    """Try to parse a single flight segment dict into a NormalizedFlight."""
    # Extract flight number.
    flight_number = None
    for fn_key in (
        "flightNumber",
        "flight_number",
        "flightNo",
        "flightNum",
        "number",
    ):
        fn_val = seg.get(fn_key)
        if fn_val:
            fn_str = str(fn_val)
            # Ensure it starts with NH.
            if not fn_str.startswith("NH"):
                fn_str = f"NH{fn_str}"
            flight_number = fn_str
            break

    # Also check "carrier" + "number" pattern.
    if not flight_number:
        carrier = seg.get("carrier", seg.get("airlineCode", ""))
        num = seg.get("number", seg.get("flightNo", ""))
        if carrier and num:
            flight_number = f"{carrier}{num}"

    if not flight_number:
        return None

    # Extract origin/destination.
    seg_origin = (
        seg.get("departureAirport")
        or seg.get("departure", {}).get("airport")
        or seg.get("origin")
        or seg.get("dep")
        or origin
    )
    seg_dest = (
        seg.get("arrivalAirport")
        or seg.get("arrival", {}).get("airport")
        or seg.get("destination")
        or seg.get("arr")
        or destination
    )

    # Extract times.
    dep_time_str = (
        seg.get("departureTime")
        or seg.get("departure", {}).get("time")
        or seg.get("depTime")
        or seg.get("departureDateTime")
    )
    arr_time_str = (
        seg.get("arrivalTime")
        or seg.get("arrival", {}).get("time")
        or seg.get("arrTime")
        or seg.get("arrivalDateTime")
    )

    dep_dt = _parse_time(str(dep_time_str) if dep_time_str else None, departure_date)
    arr_dt = _parse_time(str(arr_time_str) if arr_time_str else None, departure_date)

    # Default to midnight if we can't parse times.
    if dep_dt is None:
        try:
            dep_dt = datetime.fromisoformat(departure_date).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            dep_dt = now

    if arr_dt is None:
        arr_dt = dep_dt

    duration = _parse_duration_minutes(dep_dt, arr_dt)

    # Extract aircraft type.
    aircraft = (
        seg.get("aircraftType") or seg.get("aircraft") or seg.get("equipmentType")
    )

    # Extract cabin class from segment.
    seg_cabin_str = (
        seg.get("cabinClass") or seg.get("cabin") or seg.get("bookingClass") or ""
    )
    seg_cabin = _CABIN_MAP.get(str(seg_cabin_str).upper(), cabin_class)

    # Extract stops.
    stops = seg.get("stops", seg.get("numberOfStops", 0))
    if isinstance(stops, str):
        stops = int(stops) if stops.isdigit() else 0

    # Extract price.
    prices: list[NormalizedPrice] = []
    price_val = (
        seg.get("totalPrice")
        or seg.get("price")
        or seg.get("fare")
        or seg.get("amount")
    )
    # Check nested price structures.
    if price_val is None:
        price_spec = seg.get("priceSpecification", seg.get("pricing", {}))
        if isinstance(price_spec, dict):
            price_val = price_spec.get("totalPrice") or price_spec.get("amount")

    amount = _extract_price(price_val)
    currency = str(
        seg.get("currency")
        or seg.get("currencyCode")
        or seg.get("priceSpecification", {}).get("currencyCode")
        or "JPY"
    )

    if amount:
        fare_class = seg.get("fareClass") or seg.get("bookingClass")
        prices.append(
            NormalizedPrice(
                amount=amount,
                currency=currency,
                source=DataSource.DIRECT_CRAWL,
                fare_class=str(fare_class) if fare_class else None,
                crawled_at=now,
            )
        )

    return NormalizedFlight(
        flight_number=flight_number,
        airline_code=_ANA_CODE,
        airline_name=_ANA_NAME,
        operator=_ANA_CODE,
        origin=str(seg_origin),
        destination=str(seg_dest),
        departure_time=dep_dt,
        arrival_time=arr_dt,
        duration_minutes=duration,
        cabin_class=seg_cabin,
        aircraft_type=str(aircraft) if aircraft else None,
        stops=int(stops),
        prices=prices,
        source=DataSource.DIRECT_CRAWL,
        crawled_at=now,
    )


def parse_dom_flights(
    dom_flights: list[dict[str, Any]],
    origin: str,
    destination: str,
    departure_date: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse flights from DOM-scraped card data.

    Each ``dom_flight`` dict has keys: ``flight_number``, ``departure_time``,
    ``arrival_time``, ``price``, ``raw_text``.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    for card in dom_flights:
        fn = card.get("flight_number")
        if not fn:
            # Try extracting from raw_text.
            raw = card.get("raw_text", "")
            match = re.search(r"NH\s*(\d{1,4})", raw)
            if match:
                fn = f"NH{match.group(1)}"
            else:
                continue

        dep_dt = _parse_time(card.get("departure_time"), departure_date)
        arr_dt = _parse_time(card.get("arrival_time"), departure_date)

        if dep_dt is None:
            try:
                dep_dt = datetime.fromisoformat(departure_date).replace(tzinfo=UTC)
            except (ValueError, TypeError):
                dep_dt = now

        if arr_dt is None:
            arr_dt = dep_dt

        duration = _parse_duration_minutes(dep_dt, arr_dt)

        prices: list[NormalizedPrice] = []
        amount = _extract_price(card.get("price"))
        if amount:
            prices.append(
                NormalizedPrice(
                    amount=amount,
                    currency="JPY",
                    source=DataSource.DIRECT_CRAWL,
                    crawled_at=now,
                )
            )

        flights.append(
            NormalizedFlight(
                flight_number=fn,
                airline_code=_ANA_CODE,
                airline_name=_ANA_NAME,
                operator=_ANA_CODE,
                origin=origin,
                destination=destination,
                departure_time=dep_dt,
                arrival_time=arr_dt,
                duration_minutes=duration,
                cabin_class=cabin_class,
                stops=0,
                prices=prices,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    logger.info(
        "ANA DOM parser: extracted %d flights from %d cards for %s->%s",
        len(flights),
        len(dom_flights),
        origin,
        destination,
    )
    return flights
