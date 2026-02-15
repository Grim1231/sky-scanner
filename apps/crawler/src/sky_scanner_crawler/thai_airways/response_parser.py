"""Parse Thai Airways intercepted API responses into NormalizedFlight objects.

Thai Airways uses Amadeus OSCI (Open Shopping for Certified Intermediaries)
as its booking backend.  The intercepted responses may contain:

1. **AirShopping/OfferPrice responses** (Amadeus NDC-style):
   Flight offers with segments, fares, and pricing.

2. **Legacy availability responses**:
   Flight schedules with fare classes and prices.

3. **Calendar/low-fare responses**:
   Daily lowest fares for a date range.

The parser attempts to normalise all three response types into
``NormalizedFlight`` objects.

Response structure (Amadeus NDC-style, simplified)::

    {
        "data": {
            "offers": [
                {
                    "offerId": "...",
                    "price": {"total": 450000, "currency": "KRW"},
                    "segments": [
                        {
                            "flightNumber": "TG658",
                            "origin": "ICN",
                            "destination": "BKK",
                            "departureTime": "2026-04-15T10:30:00",
                            "arrivalTime": "2026-04-15T14:30:00",
                            "duration": "PT4H0M",
                            "aircraft": "B777",
                            "cabinClass": "Y",
                        }
                    ],
                }
            ]
        }
    }
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

_TG_CODE = "TG"
_TG_NAME = "Thai Airways"

# Cabin class mapping for Thai Airways / Amadeus OSCI.
_CABIN_MAP: dict[str, CabinClass] = {
    "Y": CabinClass.ECONOMY,
    "W": CabinClass.PREMIUM_ECONOMY,
    "C": CabinClass.BUSINESS,
    "J": CabinClass.BUSINESS,
    "F": CabinClass.FIRST,
    "ECONOMY": CabinClass.ECONOMY,
    "PREMIUM_ECONOMY": CabinClass.PREMIUM_ECONOMY,
    "PREMIUM": CabinClass.PREMIUM_ECONOMY,
    "BUSINESS": CabinClass.BUSINESS,
    "FIRST": CabinClass.FIRST,
    "M": CabinClass.ECONOMY,
    "P": CabinClass.PREMIUM_ECONOMY,
}


def _parse_dt(dt_str: str) -> datetime | None:
    """Parse an ISO datetime string to a timezone-aware UTC datetime."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return None


def _parse_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration (``PT4H30M``) to minutes."""
    if not duration_str:
        return 0
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration_str)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        return hours * 60 + minutes
    # Try plain integer (minutes).
    try:
        return int(duration_str)
    except (ValueError, TypeError):
        return 0


def parse_intercepted_responses(
    responses: list[dict[str, Any]],
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse all intercepted TG API responses into NormalizedFlights.

    Tries multiple parsing strategies based on response structure.
    """
    flights: list[NormalizedFlight] = []

    for resp in responses:
        # Strategy 1: NDC-style offers (data.offers or data.flightOffers).
        flights.extend(_parse_ndc_offers(resp, origin, destination, cabin_class))

        # Strategy 2: Amadeus OSCI availability (flightAvailability).
        flights.extend(_parse_osci_availability(resp, origin, destination, cabin_class))

        # Strategy 3: Low-fare calendar (dailyFares or lowFares).
        flights.extend(_parse_low_fare_calendar(resp, origin, destination, cabin_class))

        # Strategy 4: Generic flight data (look for common keys).
        flights.extend(
            _parse_generic_flight_data(resp, origin, destination, cabin_class)
        )

    # Deduplicate by flight number + date.
    seen: set[str] = set()
    unique: list[NormalizedFlight] = []
    for f in flights:
        key = f"{f.flight_number}:{f.departure_time.isoformat()}"
        if key not in seen:
            seen.add(key)
            unique.append(f)

    logger.info(
        "TG: parsed %d unique flights from %d intercepted responses",
        len(unique),
        len(responses),
    )
    return unique


def _parse_ndc_offers(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass,
) -> list[NormalizedFlight]:
    """Parse Amadeus NDC-style flight offers."""
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    # Look for offers in various locations.
    offers = (
        data.get("data", {}).get("offers", [])
        or data.get("data", {}).get("flightOffers", [])
        or data.get("offers", [])
        or data.get("flightOffers", [])
    )

    if not offers:
        return flights

    for offer in offers:
        if not isinstance(offer, dict):
            continue

        segments = (
            offer.get("segments", [])
            or offer.get("itineraries", [{}])[0].get("segments", [])
            if offer.get("itineraries")
            else offer.get("segments", [])
        )

        if not segments:
            continue

        first_seg = segments[0] if isinstance(segments[0], dict) else {}
        last_seg = segments[-1] if isinstance(segments[-1], dict) else {}

        seg_origin = (
            first_seg.get("origin", origin)
            if isinstance(first_seg.get("origin"), str)
            else first_seg.get("origin", {}).get("iataCode", origin)
        )
        seg_dest = (
            last_seg.get("destination", destination)
            if isinstance(last_seg.get("destination"), str)
            else last_seg.get("destination", {}).get("iataCode", destination)
        )

        dep_str = first_seg.get("departureTime") or first_seg.get("departure", {}).get(
            "at", ""
        )
        arr_str = last_seg.get("arrivalTime") or last_seg.get("arrival", {}).get(
            "at", ""
        )
        dep_time = _parse_dt(dep_str)
        arr_time = _parse_dt(arr_str)

        if not dep_time:
            continue

        if not arr_time:
            arr_time = dep_time

        duration_str = first_seg.get("duration", "")
        duration_minutes = _parse_duration(duration_str)
        if not duration_minutes and dep_time and arr_time:
            duration_minutes = max(0, int((arr_time - dep_time).total_seconds() / 60))

        flight_num = first_seg.get("flightNumber", "") or first_seg.get("number", "")
        carrier = first_seg.get("carrier", _TG_CODE) or first_seg.get(
            "carrierCode", _TG_CODE
        )
        if isinstance(carrier, dict):
            carrier = carrier.get("code", _TG_CODE)
        if not flight_num.startswith(carrier):
            flight_num = f"{carrier}{flight_num}"

        cabin_str = first_seg.get("cabinClass", "") or first_seg.get("cabin", "")
        seg_cabin = _CABIN_MAP.get(cabin_str.upper(), cabin_class)

        aircraft = first_seg.get("aircraft", "") or first_seg.get("aircraftType", "")
        if isinstance(aircraft, dict):
            aircraft = aircraft.get("code", "")

        # Price extraction.
        price_data = offer.get("price", {})
        total = (
            price_data.get("total")
            or price_data.get("grandTotal")
            or price_data.get("amount")
        )
        currency = price_data.get("currency", "KRW") or price_data.get(
            "currencyCode", "KRW"
        )

        prices: list[NormalizedPrice] = []
        if total is not None:
            try:
                amount = float(total)
                if amount > 0:
                    prices.append(
                        NormalizedPrice(
                            amount=amount,
                            currency=currency,
                            source=DataSource.DIRECT_CRAWL,
                            fare_class=offer.get("fareClass"),
                            crawled_at=now,
                        )
                    )
            except (ValueError, TypeError):
                pass

        flights.append(
            NormalizedFlight(
                flight_number=flight_num,
                airline_code=carrier if len(carrier) == 2 else _TG_CODE,
                airline_name=_TG_NAME,
                operator=carrier if len(carrier) == 2 else _TG_CODE,
                origin=seg_origin,
                destination=seg_dest,
                departure_time=dep_time,
                arrival_time=arr_time,
                duration_minutes=duration_minutes,
                cabin_class=seg_cabin,
                aircraft_type=aircraft or None,
                stops=max(0, len(segments) - 1),
                prices=prices,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    return flights


def _parse_osci_availability(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass,
) -> list[NormalizedFlight]:
    """Parse Amadeus OSCI-style flight availability."""
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    avail = (
        data.get("flightAvailability", [])
        or data.get("availability", [])
        or data.get("data", {}).get("flightAvailability", [])
    )

    if not avail:
        return flights

    for entry in avail:
        if not isinstance(entry, dict):
            continue

        seg_origin = entry.get("origin", origin)
        seg_dest = entry.get("destination", destination)

        dep_str = entry.get("departureDateTime", "") or entry.get("departureTime", "")
        arr_str = entry.get("arrivalDateTime", "") or entry.get("arrivalTime", "")
        dep_time = _parse_dt(dep_str)
        arr_time = _parse_dt(arr_str)

        if not dep_time:
            continue
        if not arr_time:
            arr_time = dep_time

        flight_num = entry.get("flightNumber", "")
        if not flight_num.startswith(_TG_CODE):
            flight_num = f"{_TG_CODE}{flight_num}"

        duration_minutes = entry.get("durationMinutes", 0)
        if not duration_minutes:
            duration_minutes = _parse_duration(entry.get("duration", ""))
        if not duration_minutes and arr_time > dep_time:
            duration_minutes = int((arr_time - dep_time).total_seconds() / 60)

        aircraft = entry.get("aircraft", entry.get("equipmentType", ""))

        # Price from fare classes.
        prices: list[NormalizedPrice] = []
        fare_classes = entry.get("fareClasses", entry.get("fares", []))
        for fare in fare_classes:
            if not isinstance(fare, dict):
                continue
            amount = fare.get("price") or fare.get("amount") or fare.get("total")
            if amount is not None:
                try:
                    amount_f = float(amount)
                    if amount_f > 0:
                        prices.append(
                            NormalizedPrice(
                                amount=amount_f,
                                currency=fare.get("currency", "KRW"),
                                source=DataSource.DIRECT_CRAWL,
                                fare_class=fare.get("code") or fare.get("fareClass"),
                                crawled_at=now,
                            )
                        )
                except (ValueError, TypeError):
                    pass

        flights.append(
            NormalizedFlight(
                flight_number=flight_num,
                airline_code=_TG_CODE,
                airline_name=_TG_NAME,
                operator=_TG_CODE,
                origin=seg_origin,
                destination=seg_dest,
                departure_time=dep_time,
                arrival_time=arr_time,
                duration_minutes=duration_minutes,
                cabin_class=cabin_class,
                aircraft_type=aircraft or None,
                stops=0,
                prices=prices,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    return flights


def _parse_low_fare_calendar(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass,
) -> list[NormalizedFlight]:
    """Parse low-fare calendar responses (daily lowest fares)."""
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    fares = (
        data.get("dailyFares", [])
        or data.get("lowFares", [])
        or data.get("data", {}).get("dailyFares", [])
        or data.get("data", {}).get("lowFares", [])
        or data.get("calendarFares", [])
    )

    if not fares:
        return flights

    for fare in fares:
        if not isinstance(fare, dict):
            continue

        date_str = fare.get("date", "")
        dep_time = _parse_dt(date_str)
        if not dep_time:
            continue

        amount = (
            fare.get("price")
            or fare.get("amount")
            or fare.get("total")
            or fare.get("lowestFare")
        )
        if amount is None:
            continue

        try:
            amount_f = float(amount)
        except (ValueError, TypeError):
            continue

        if amount_f <= 0:
            continue

        currency = fare.get("currency", "KRW")

        flights.append(
            NormalizedFlight(
                flight_number=f"{_TG_CODE}-{origin}{destination}",
                airline_code=_TG_CODE,
                airline_name=_TG_NAME,
                operator=_TG_CODE,
                origin=origin,
                destination=destination,
                departure_time=dep_time,
                arrival_time=dep_time,
                duration_minutes=0,
                cabin_class=cabin_class,
                stops=0,
                prices=[
                    NormalizedPrice(
                        amount=amount_f,
                        currency=currency,
                        source=DataSource.DIRECT_CRAWL,
                        fare_class=fare.get("fareClass"),
                        crawled_at=now,
                    )
                ],
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    return flights


def _parse_generic_flight_data(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass,
) -> list[NormalizedFlight]:
    """Fallback: try to extract flight data from generic dict structures.

    Looks for common patterns like ``flights``, ``results``, ``journeys``
    keys in the response data.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    # Check various top-level keys.
    flight_lists = None
    for key in ("flights", "results", "journeys", "trips", "itineraries"):
        candidate = data.get(key) or data.get("data", {}).get(key)
        if isinstance(candidate, list) and candidate:
            flight_lists = candidate
            break

    if not flight_lists:
        return flights

    for item in flight_lists:
        if not isinstance(item, dict):
            continue

        # Try to extract essential fields.
        dep_str = (
            item.get("departureTime")
            or item.get("departureDateTime")
            or item.get("departure", {}).get("time", "")
            if isinstance(item.get("departure"), dict)
            else item.get("departureTime", "")
        )
        dep_time = _parse_dt(dep_str) if isinstance(dep_str, str) else None
        if not dep_time:
            continue

        arr_str = (
            item.get("arrivalTime")
            or item.get("arrivalDateTime")
            or item.get("arrival", {}).get("time", "")
            if isinstance(item.get("arrival"), dict)
            else item.get("arrivalTime", "")
        )
        arr_time = _parse_dt(arr_str) if isinstance(arr_str, str) else dep_time

        flight_num = item.get("flightNumber", f"{_TG_CODE}-{origin}{destination}")
        if not flight_num.startswith(_TG_CODE) and not flight_num.startswith(origin):
            flight_num = f"{_TG_CODE}{flight_num}"

        duration = _parse_duration(str(item.get("duration", "")))
        if not duration and arr_time and dep_time and arr_time > dep_time:
            duration = int((arr_time - dep_time).total_seconds() / 60)

        amount = item.get("price") or item.get("fare") or item.get("amount")
        prices_list: list[NormalizedPrice] = []
        if amount is not None:
            try:
                amount_f = float(amount)
                if amount_f > 0:
                    prices_list.append(
                        NormalizedPrice(
                            amount=amount_f,
                            currency=item.get("currency", "KRW"),
                            source=DataSource.DIRECT_CRAWL,
                            crawled_at=now,
                        )
                    )
            except (ValueError, TypeError):
                pass

        flights.append(
            NormalizedFlight(
                flight_number=flight_num,
                airline_code=_TG_CODE,
                airline_name=_TG_NAME,
                operator=_TG_CODE,
                origin=item.get("origin", origin),
                destination=item.get("destination", destination),
                departure_time=dep_time,
                arrival_time=arr_time or dep_time,
                duration_minutes=duration,
                cabin_class=cabin_class,
                stops=item.get("stops", 0),
                prices=prices_list,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    return flights
