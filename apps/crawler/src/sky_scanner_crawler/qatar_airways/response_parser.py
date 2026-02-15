"""Parse Qatar Airways qoreservices API responses into NormalizedFlight objects.

Qatar Airways uses the ``qoreservices.qatarairways.com`` API which returns
JSON flight offers from its Amadeus-based backend.

Observed response structures:

1. **Offer search response** (``/api/offer/search``)::

    {
        "data": {
            "offers": [
                {
                    "offerId": "OF-...",
                    "totalPrice": {"amount": 850000, "currency": "KRW"},
                    "journeys": [
                        {
                            "segments": [
                                {
                                    "flightNumber": "QR859",
                                    "carrierCode": "QR",
                                    "origin": {"code": "ICN"},
                                    "destination": {"code": "DOH"},
                                    "departureDateTime": "2026-04-15T01:10:00",
                                    "arrivalDateTime": "2026-04-15T06:30:00",
                                    "duration": "PT10H20M",
                                    "aircraftCode": "77W",
                                    "cabinClass": "ECONOMY",
                                    "bookingClass": "Y",
                                }
                            ]
                        }
                    ],
                    "fareDetails": {
                        "fareType": "PUBLISHED",
                        "fareClass": "Y",
                    },
                }
            ]
        }
    }

2. **Flight list response** (alternative structure)::

    {
        "flights": [
            {
                "flightNumber": "QR859",
                "departure": {"airport": "ICN", "time": "01:10"},
                "arrival": {"airport": "DOH", "time": "06:30"},
                "duration": 620,
                "fares": [{"cabin": "Economy", "price": 850000, "currency": "KRW"}],
            }
        ]
    }

3. **Calendar/lowest fare response**::

    {"calendar": [{"date": "2026-04-15", "lowestFare": 850000, "currency": "KRW"}]}
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

_QR_CODE = "QR"
_QR_NAME = "Qatar Airways"

# Cabin class mapping for Qatar Airways.
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
    "Economy": CabinClass.ECONOMY,
    "Business": CabinClass.BUSINESS,
    "First": CabinClass.FIRST,
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
    """Parse ISO 8601 duration (``PT10H20M``) to minutes."""
    if not duration_str:
        return 0
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", str(duration_str))
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
    """Parse all intercepted QR API responses into NormalizedFlights.

    Tries multiple parsing strategies based on response structure.
    """
    flights: list[NormalizedFlight] = []

    for resp in responses:
        # Strategy 1: qoreservices offer search (data.offers with journeys).
        flights.extend(_parse_qore_offers(resp, origin, destination, cabin_class))

        # Strategy 2: Simple flight list (flights array).
        flights.extend(_parse_flight_list(resp, origin, destination, cabin_class))

        # Strategy 3: Calendar/lowest fare response.
        flights.extend(_parse_calendar_fares(resp, origin, destination, cabin_class))

        # Strategy 4: NDC-style offers (data.flightOffers).
        flights.extend(_parse_ndc_offers(resp, origin, destination, cabin_class))

        # Strategy 5: Generic fallback.
        flights.extend(_parse_generic_data(resp, origin, destination, cabin_class))

    # Deduplicate by flight number + date.
    seen: set[str] = set()
    unique: list[NormalizedFlight] = []
    for f in flights:
        key = f"{f.flight_number}:{f.departure_time.isoformat()}"
        if key not in seen:
            seen.add(key)
            unique.append(f)

    logger.info(
        "QR: parsed %d unique flights from %d intercepted responses",
        len(unique),
        len(responses),
    )
    return unique


def _parse_qore_offers(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass,
) -> list[NormalizedFlight]:
    """Parse qoreservices offer search response.

    Expected structure: ``data.offers[].journeys[].segments[]``
    with ``totalPrice`` at the offer level.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    offers = data.get("data", {}).get("offers", []) or data.get("offers", [])

    if not offers:
        return flights

    for offer in offers:
        if not isinstance(offer, dict):
            continue

        # Price at offer level.
        price_data = offer.get("totalPrice", {}) or offer.get("price", {})
        total_amount = (
            price_data.get("amount")
            or price_data.get("total")
            or price_data.get("grandTotal")
        )
        currency = price_data.get("currency", "KRW") or price_data.get(
            "currencyCode", "KRW"
        )

        journeys = offer.get("journeys", [])
        if not journeys:
            # Try segments directly.
            journeys = [{"segments": offer.get("segments", [])}]

        for journey in journeys:
            if not isinstance(journey, dict):
                continue

            segments = journey.get("segments", [])
            if not segments:
                continue

            first_seg = segments[0] if isinstance(segments[0], dict) else {}
            last_seg = segments[-1] if isinstance(segments[-1], dict) else {}

            # Origin/destination.
            seg_origin = _extract_airport_code(first_seg, "origin", origin)
            seg_dest = _extract_airport_code(last_seg, "destination", destination)

            # Departure/arrival times.
            dep_str = (
                first_seg.get("departureDateTime")
                or first_seg.get("departureTime")
                or first_seg.get("departure", {}).get("dateTime", "")
                if isinstance(first_seg.get("departure"), dict)
                else first_seg.get("departureDateTime", "")
            )
            arr_str = (
                last_seg.get("arrivalDateTime")
                or last_seg.get("arrivalTime")
                or last_seg.get("arrival", {}).get("dateTime", "")
                if isinstance(last_seg.get("arrival"), dict)
                else last_seg.get("arrivalDateTime", "")
            )

            dep_time = _parse_dt(dep_str) if isinstance(dep_str, str) else None
            arr_time = _parse_dt(arr_str) if isinstance(arr_str, str) else None

            if not dep_time:
                continue
            if not arr_time:
                arr_time = dep_time

            # Flight number.
            flight_num = first_seg.get("flightNumber", "") or first_seg.get(
                "number", ""
            )
            carrier = first_seg.get("carrierCode", _QR_CODE) or first_seg.get(
                "carrier", _QR_CODE
            )
            if isinstance(carrier, dict):
                carrier = carrier.get("code", _QR_CODE)
            if flight_num and not flight_num.startswith(carrier):
                flight_num = f"{carrier}{flight_num}"
            elif not flight_num:
                flight_num = f"{_QR_CODE}-{seg_origin}{seg_dest}"

            # Duration.
            duration_str = first_seg.get("duration", "") or journey.get("duration", "")
            duration_minutes = _parse_duration(duration_str)
            if not duration_minutes and arr_time > dep_time:
                duration_minutes = int((arr_time - dep_time).total_seconds() / 60)

            # Cabin class.
            cabin_str = (
                first_seg.get("cabinClass", "")
                or first_seg.get("cabin", "")
                or first_seg.get("bookingClass", "")
            )
            seg_cabin = _CABIN_MAP.get(cabin_str, cabin_class)

            # Aircraft.
            aircraft = (
                first_seg.get("aircraftCode", "")
                or first_seg.get("aircraft", "")
                or first_seg.get("equipmentType", "")
            )
            if isinstance(aircraft, dict):
                aircraft = aircraft.get("code", "")

            # Build prices.
            prices: list[NormalizedPrice] = []
            if total_amount is not None:
                try:
                    amount_f = float(total_amount)
                    if amount_f > 0:
                        fare_details = offer.get("fareDetails", {})
                        prices.append(
                            NormalizedPrice(
                                amount=amount_f,
                                currency=currency,
                                source=DataSource.DIRECT_CRAWL,
                                fare_class=fare_details.get("fareClass")
                                or fare_details.get("fareType"),
                                crawled_at=now,
                            )
                        )
                except (ValueError, TypeError):
                    pass

            flights.append(
                NormalizedFlight(
                    flight_number=flight_num,
                    airline_code=carrier if len(carrier) == 2 else _QR_CODE,
                    airline_name=_QR_NAME,
                    operator=carrier if len(carrier) == 2 else _QR_CODE,
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


def _parse_flight_list(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass,
) -> list[NormalizedFlight]:
    """Parse a simple flights array response."""
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    flight_list = data.get("flights", []) or data.get("data", {}).get("flights", [])

    if not flight_list:
        return flights

    for item in flight_list:
        if not isinstance(item, dict):
            continue

        flight_num = item.get("flightNumber", "")
        if not flight_num:
            continue

        # Departure/arrival.
        dep_info = item.get("departure", {})
        arr_info = item.get("arrival", {})

        if isinstance(dep_info, dict):
            dep_str = dep_info.get("dateTime") or dep_info.get("time", "")
            seg_origin = dep_info.get("airport", dep_info.get("code", origin))
        else:
            dep_str = item.get("departureDateTime", "")
            seg_origin = origin

        if isinstance(arr_info, dict):
            arr_str = arr_info.get("dateTime") or arr_info.get("time", "")
            seg_dest = arr_info.get("airport", arr_info.get("code", destination))
        else:
            arr_str = item.get("arrivalDateTime", "")
            seg_dest = destination

        dep_time = _parse_dt(dep_str)
        arr_time = _parse_dt(arr_str)
        if not dep_time:
            continue
        if not arr_time:
            arr_time = dep_time

        duration = item.get("duration", 0)
        if isinstance(duration, str):
            duration = _parse_duration(duration)
        if not duration and arr_time > dep_time:
            duration = int((arr_time - dep_time).total_seconds() / 60)

        if not flight_num.startswith(_QR_CODE):
            flight_num = f"{_QR_CODE}{flight_num}"

        # Fares.
        prices: list[NormalizedPrice] = []
        fares = item.get("fares", item.get("prices", []))
        for fare in fares:
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
                                fare_class=fare.get("cabin") or fare.get("fareClass"),
                                crawled_at=now,
                            )
                        )
                except (ValueError, TypeError):
                    pass

        flights.append(
            NormalizedFlight(
                flight_number=flight_num,
                airline_code=_QR_CODE,
                airline_name=_QR_NAME,
                operator=_QR_CODE,
                origin=seg_origin,
                destination=seg_dest,
                departure_time=dep_time,
                arrival_time=arr_time,
                duration_minutes=duration,
                cabin_class=cabin_class,
                aircraft_type=item.get("aircraft") or None,
                stops=item.get("stops", 0),
                prices=prices,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    return flights


def _parse_calendar_fares(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass,
) -> list[NormalizedFlight]:
    """Parse calendar/lowest fare responses."""
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    calendar = (
        data.get("calendar", [])
        or data.get("data", {}).get("calendar", [])
        or data.get("dailyFares", [])
        or data.get("data", {}).get("dailyFares", [])
        or data.get("lowFares", [])
    )

    if not calendar:
        return flights

    for entry in calendar:
        if not isinstance(entry, dict):
            continue

        date_str = entry.get("date", "")
        dep_time = _parse_dt(date_str)
        if not dep_time:
            continue

        amount = (
            entry.get("lowestFare")
            or entry.get("price")
            or entry.get("amount")
            or entry.get("total")
        )
        if amount is None:
            continue

        try:
            amount_f = float(amount)
        except (ValueError, TypeError):
            continue

        if amount_f <= 0:
            continue

        currency = entry.get("currency", "KRW")

        flights.append(
            NormalizedFlight(
                flight_number=f"{_QR_CODE}-{origin}{destination}",
                airline_code=_QR_CODE,
                airline_name=_QR_NAME,
                operator=_QR_CODE,
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
                        fare_class=entry.get("fareClass"),
                        crawled_at=now,
                    )
                ],
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    return flights


def _parse_ndc_offers(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass,
) -> list[NormalizedFlight]:
    """Parse NDC-style flight offers (flightOffers array)."""
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    offers = data.get("data", {}).get("flightOffers", []) or data.get(
        "flightOffers", []
    )

    if not offers:
        return flights

    for offer in offers:
        if not isinstance(offer, dict):
            continue

        itineraries = offer.get("itineraries", [])
        if not itineraries:
            continue

        price_data = offer.get("price", {})
        total_amount = price_data.get("total") or price_data.get("grandTotal")
        currency = price_data.get("currency", "KRW")

        for itin in itineraries:
            segments = itin.get("segments", [])
            if not segments:
                continue

            first_seg = segments[0]
            last_seg = segments[-1]

            seg_origin = _extract_airport_code(first_seg, "departure", origin)
            seg_dest = _extract_airport_code(last_seg, "arrival", destination)

            dep_str = first_seg.get("departure", {}).get("at", "")
            arr_str = last_seg.get("arrival", {}).get("at", "")
            dep_time = _parse_dt(dep_str)
            arr_time = _parse_dt(arr_str)

            if not dep_time:
                continue
            if not arr_time:
                arr_time = dep_time

            carrier = first_seg.get("carrierCode", _QR_CODE)
            number = first_seg.get("number", "")
            flight_num = (
                f"{carrier}{number}" if number else f"{_QR_CODE}-{seg_origin}{seg_dest}"
            )

            duration_str = itin.get("duration", first_seg.get("duration", ""))
            duration_minutes = _parse_duration(duration_str)
            if not duration_minutes and arr_time > dep_time:
                duration_minutes = int((arr_time - dep_time).total_seconds() / 60)

            cabin_str = first_seg.get("cabin", "")
            seg_cabin = _CABIN_MAP.get(cabin_str, cabin_class)

            aircraft = first_seg.get("aircraft", {})
            if isinstance(aircraft, dict):
                aircraft = aircraft.get("code", "")

            prices: list[NormalizedPrice] = []
            if total_amount is not None:
                try:
                    amount_f = float(total_amount)
                    if amount_f > 0:
                        prices.append(
                            NormalizedPrice(
                                amount=amount_f,
                                currency=currency,
                                source=DataSource.DIRECT_CRAWL,
                                crawled_at=now,
                            )
                        )
                except (ValueError, TypeError):
                    pass

            flights.append(
                NormalizedFlight(
                    flight_number=flight_num,
                    airline_code=carrier if len(carrier) == 2 else _QR_CODE,
                    airline_name=_QR_NAME,
                    operator=carrier if len(carrier) == 2 else _QR_CODE,
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


def _parse_generic_data(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass,
) -> list[NormalizedFlight]:
    """Fallback: try to extract flight data from generic dict structures.

    Looks for keys like ``results``, ``journeys``, ``trips`` in the response.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    items = None
    for key in ("results", "journeys", "trips", "itineraries", "boundList"):
        candidate = data.get(key) or data.get("data", {}).get(key)
        if isinstance(candidate, list) and candidate:
            items = candidate
            break

    if not items:
        return flights

    for item in items:
        if not isinstance(item, dict):
            continue

        dep_str = (
            item.get("departureTime")
            or item.get("departureDateTime")
            or item.get("departure", {}).get("dateTime", "")
            if isinstance(item.get("departure"), dict)
            else item.get("departureTime", "")
        )
        dep_time = _parse_dt(dep_str) if isinstance(dep_str, str) else None
        if not dep_time:
            continue

        arr_str = (
            item.get("arrivalTime")
            or item.get("arrivalDateTime")
            or item.get("arrival", {}).get("dateTime", "")
            if isinstance(item.get("arrival"), dict)
            else item.get("arrivalTime", "")
        )
        arr_time = _parse_dt(arr_str) if isinstance(arr_str, str) else dep_time

        flight_num = item.get("flightNumber", f"{_QR_CODE}-{origin}{destination}")
        if not flight_num.startswith(_QR_CODE) and not flight_num.startswith(origin):
            flight_num = f"{_QR_CODE}{flight_num}"

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
                airline_code=_QR_CODE,
                airline_name=_QR_NAME,
                operator=_QR_CODE,
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


def _extract_airport_code(
    segment: dict[str, Any],
    field: str,
    default: str,
) -> str:
    """Extract IATA airport code from a segment field.

    Handles both ``{"origin": "ICN"}`` and ``{"origin": {"code": "ICN"}}``
    patterns.
    """
    value = segment.get(field, default)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return (
            value.get("code", "")
            or value.get("iataCode", "")
            or value.get("airport", "")
            or default
        )
    return default
