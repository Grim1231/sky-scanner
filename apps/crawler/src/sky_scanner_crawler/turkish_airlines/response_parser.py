"""Parse Turkish Airlines API responses into NormalizedFlight objects.

Supports both L2 website API responses and official developer API responses.

L2 Website API Endpoints
========================

``/api/v1/availability/cheapest-prices``
    Returns a daily price calendar with cheapest economy/business prices.
    Response structure::

        {
            "data": {
                "allPricesCheapest": false,
                "dailyPriceList": [
                    {
                        "date": "2026-04-13",
                        "bestPrice": true,
                        "price": {"amount": 1234.56, "currencyCode": "USD"},
                    },
                    ...,
                ],
            }
        }

``/api/v1/availability/flight-matrix``
    Returns full flight results with segment details, fare categories,
    and prices.  Response structure::

        {
            "data": {
                "originDestinationInformationList": [
                    {
                        "departureDate": "2026-04-15",
                        "originDestinationOptionList": [
                            {
                                "segmentList": [
                                    {
                                        "departureAirportCode": "IST",
                                        "arrivalAirportCode": "ICN",
                                        "departureDateTime": "2026-04-15T01:20:00",
                                        "arrivalDateTime": "2026-04-15T18:30:00",
                                        "duration": "PT10H10M",
                                        "marketingAirlineCode": "TK",
                                        "marketingFlightNumber": "90",
                                        "operatingAirlineCode": "TK",
                                        "operatingFlightNumber": "90",
                                        "equipmentCode": "77W"
                                    }
                                ],
                                "fareCategory": {
                                    "ECONOMY": {
                                        "status": "AVAILABLE",
                                        "startingPrice": {
                                            "amount": 1234.56,
                                            "currencyCode": "USD"
                                        },
                                        "brandList": [
                                            {
                                                "brandCode": "EP",
                                                "brandName": "EcoFly",
                                                "price": {
                                                    "amount": 1234.56,
                                                    "currencyCode": "USD"
                                                },
                                                "fareClass": "Y"
                                            }
                                        ]
                                    },
                                    "BUSINESS": {
                                        "status": "AVAILABLE",
                                        ...
                                    }
                                },
                                "totalDuration": "PT10H10M",
                                "stopCount": 0,
                                "cheapest": true
                            }
                        ]
                    }
                ],
                "priceType": "PER_PASSENGER",
                "economyStartingPrice": { ... },
                "businessStartingPrice": { ... }
            }
        }

Official Developer API Endpoints
=================================

``POST /getTimeTable``
    Returns flight schedule data.  Response structure varies but
    typically includes flight segments with departure/arrival info,
    flight numbers, aircraft types, and operation day flags.

``POST /getAvailability``
    Returns availability with fare families and pricing.
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

# ISO-8601 duration -> minutes.
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")

# TK fare category keys -> our cabin class enum.
_CABIN_MAP: dict[str, CabinClass] = {
    "ECONOMY": CabinClass.ECONOMY,
    "BUSINESS": CabinClass.BUSINESS,
}


def _parse_duration(iso_dur: str) -> int:
    """Convert ISO-8601 duration to minutes (e.g. ``PT10H30M`` -> 630)."""
    m = _DURATION_RE.match(iso_dur)
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return hours * 60 + minutes


def _parse_dt(dt_str: str) -> datetime:
    """Parse a datetime string to timezone-aware UTC datetime."""
    if not dt_str:
        return datetime.now(tz=UTC)
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        pass
    # Fallback formats used by TK.
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(tz=UTC)


# ------------------------------------------------------------------
# Cheapest-prices parser
# ------------------------------------------------------------------


def parse_cheapest_prices(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse ``/api/v1/availability/cheapest-prices`` response.

    Since the cheapest-prices endpoint only returns daily prices
    (no flight-level detail), we create one NormalizedFlight per day
    with the cheapest price.  Flight number is synthesized as
    ``TK-{origin}{destination}`` since individual flights are unknown.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    api_data = data.get("data")
    if not api_data:
        return flights

    daily_prices: list[dict[str, Any]] = api_data.get("dailyPriceList", [])

    for entry in daily_prices:
        price_obj = entry.get("price")
        if not price_obj:
            continue

        amount = price_obj.get("amount")
        if amount is None or float(amount) <= 0:
            continue

        date_str = entry.get("date", "")
        if not date_str:
            continue

        departure_dt = _parse_dt(date_str)
        # Cheapest-prices has no arrival time; estimate as departure + 10h.
        arrival_dt = _parse_dt(date_str)

        currency = price_obj.get("currencyCode", "USD")

        prices = [
            NormalizedPrice(
                amount=float(amount),
                currency=currency,
                source=DataSource.DIRECT_CRAWL,
                fare_class=None,
                crawled_at=now,
            )
        ]

        flights.append(
            NormalizedFlight(
                flight_number=f"TK-{origin}{destination}",
                airline_code="TK",
                airline_name="Turkish Airlines",
                origin=origin,
                destination=destination,
                departure_time=departure_dt,
                arrival_time=arrival_dt,
                duration_minutes=0,
                cabin_class=cabin_class,
                stops=0,
                prices=prices,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    logger.info(
        "Parsed %d daily prices from TK cheapest-prices %s->%s",
        len(flights),
        origin,
        destination,
    )
    return flights


# ------------------------------------------------------------------
# Flight-matrix parser
# ------------------------------------------------------------------


def _extract_prices_from_fare_category(
    fare_cat: dict[str, Any],
    cabin_key: str,
    now: datetime,
) -> list[NormalizedPrice]:
    """Extract prices from a single fare category (ECONOMY or BUSINESS)."""
    prices: list[NormalizedPrice] = []

    cabin_data = fare_cat.get(cabin_key, {})
    if not cabin_data:
        return prices

    status = cabin_data.get("status", "")
    if status != "AVAILABLE":
        return prices

    # Starting price (lowest for this cabin).
    starting = cabin_data.get("startingPrice", {})
    if starting and starting.get("amount") is not None:
        prices.append(
            NormalizedPrice(
                amount=float(starting["amount"]),
                currency=starting.get("currencyCode", "USD"),
                source=DataSource.DIRECT_CRAWL,
                fare_class=None,
                crawled_at=now,
            )
        )

    # Brand-level prices (EcoFly, ExtraFly, PrimeFly, etc.).
    brand_list: list[dict[str, Any]] = cabin_data.get("brandList", [])
    for brand in brand_list:
        brand_price = brand.get("price", {})
        if not brand_price or brand_price.get("amount") is None:
            continue
        fare_class = brand.get("fareClass") or brand.get("brandCode")
        prices.append(
            NormalizedPrice(
                amount=float(brand_price["amount"]),
                currency=brand_price.get("currencyCode", "USD"),
                source=DataSource.DIRECT_CRAWL,
                fare_class=fare_class,
                crawled_at=now,
            )
        )

    return prices


def parse_flight_matrix(
    data: dict[str, Any],
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse ``/api/v1/availability/flight-matrix`` response.

    Returns one NormalizedFlight per flight option with full segment
    details, fare categories, and prices.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    api_data = data.get("data")
    if not api_data:
        return flights

    od_info_list: list[dict[str, Any]] = api_data.get(
        "originDestinationInformationList", []
    )

    for od_info in od_info_list:
        options: list[dict[str, Any]] = od_info.get("originDestinationOptionList", [])

        for option in options:
            segments: list[dict[str, Any]] = option.get("segmentList", [])
            if not segments:
                continue

            first_seg = segments[0]
            last_seg = segments[-1]

            # Route.
            origin = first_seg.get("departureAirportCode", "")
            destination = last_seg.get("arrivalAirportCode", "")

            # Times.
            dep_str = first_seg.get("departureDateTime", "")
            arr_str = last_seg.get("arrivalDateTime", "")
            dep_time = _parse_dt(dep_str)
            arr_time = _parse_dt(arr_str)

            # Duration.
            duration_str = option.get("totalDuration", first_seg.get("duration", ""))
            duration_minutes = _parse_duration(duration_str)
            if not duration_minutes and dep_time and arr_time:
                diff = (arr_time - dep_time).total_seconds()
                if diff > 0:
                    duration_minutes = int(diff / 60)

            # Flight identity.
            carrier_code = first_seg.get("marketingAirlineCode", "TK")
            flight_num = first_seg.get("marketingFlightNumber", "")
            flight_number = f"{carrier_code}{flight_num}"

            # Operating carrier.
            operator = first_seg.get("operatingAirlineCode", carrier_code)

            # Aircraft.
            aircraft_type = first_seg.get("equipmentCode")

            # Stops.
            stops = option.get("stopCount", len(segments) - 1)

            # Determine the target cabin key based on requested cabin.
            cabin_key = (
                "ECONOMY"
                if cabin_class in (CabinClass.ECONOMY, CabinClass.PREMIUM_ECONOMY)
                else "BUSINESS"
            )

            # Extract prices.
            fare_cat: dict[str, Any] = option.get("fareCategory", {})
            prices = _extract_prices_from_fare_category(fare_cat, cabin_key, now)

            # If requested cabin has no prices, try the other cabin.
            if not prices:
                alt_key = "BUSINESS" if cabin_key == "ECONOMY" else "ECONOMY"
                prices = _extract_prices_from_fare_category(fare_cat, alt_key, now)
                if prices:
                    cabin_key = alt_key

            mapped_cabin = _CABIN_MAP.get(cabin_key, cabin_class)

            flights.append(
                NormalizedFlight(
                    flight_number=flight_number,
                    airline_code=carrier_code,
                    airline_name="Turkish Airlines",
                    operator=operator,
                    origin=origin,
                    destination=destination,
                    departure_time=dep_time,
                    arrival_time=arr_time,
                    duration_minutes=duration_minutes,
                    cabin_class=mapped_cabin,
                    aircraft_type=aircraft_type,
                    stops=stops,
                    prices=prices,
                    source=DataSource.DIRECT_CRAWL,
                    crawled_at=now,
                )
            )

    logger.info(
        "Parsed %d flights from TK flight-matrix",
        len(flights),
    )
    return flights


# ------------------------------------------------------------------
# Official API timetable parser
# ------------------------------------------------------------------


def parse_official_timetable(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse the official ``/getTimeTable`` API response.

    The timetable endpoint returns schedule data (no prices).  We
    create one NormalizedFlight per flight entry with zero prices.

    The response format may vary; this parser handles multiple
    common structures returned by the TK official API.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    # The official API may wrap data in various envelopes.
    # Try common keys: "data", "timetableList", "flights", or root-level list.
    flight_list: list[dict[str, Any]] = []
    if isinstance(data, list):
        flight_list = data
    elif isinstance(data, dict):
        for key in ("data", "timetableList", "flights", "scheduleList"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                flight_list = candidate
                break
            if isinstance(candidate, dict):
                # Nested envelope (e.g. data -> timetableList).
                for inner_key in ("timetableList", "flights", "scheduleList"):
                    inner = candidate.get(inner_key)
                    if isinstance(inner, list):
                        flight_list = inner
                        break
                if flight_list:
                    break

    for entry in flight_list:
        # Extract flight identity.
        flight_num = entry.get("flightNumber", entry.get("flightNo", ""))
        carrier = entry.get("airlineCode", entry.get("marketingAirlineCode", "TK"))
        if flight_num:
            flight_number = f"{carrier}{flight_num}"
        else:
            flight_number = f"TK-{origin}{destination}"

        # Times.
        dep_str = entry.get("departureDateTime", entry.get("departureTime", ""))
        arr_str = entry.get("arrivalDateTime", entry.get("arrivalTime", ""))
        dep_time = _parse_dt(dep_str)
        arr_time = _parse_dt(arr_str)

        # Duration.
        duration_str = entry.get("duration", entry.get("totalDuration", ""))
        duration_minutes = _parse_duration(duration_str) if duration_str else 0
        if not duration_minutes and dep_time and arr_time:
            diff = (arr_time - dep_time).total_seconds()
            if diff > 0:
                duration_minutes = int(diff / 60)

        # Ports (prefer entry-level, fall back to function args).
        dep_port = entry.get(
            "departureAirportCode", entry.get("originAirportCode", origin)
        )
        arr_port = entry.get(
            "arrivalAirportCode", entry.get("destinationAirportCode", destination)
        )

        # Aircraft.
        aircraft_type = entry.get("aircraftType", entry.get("equipmentCode"))

        # Operating carrier.
        operator = entry.get("operatingAirlineCode", carrier)

        # Stops.
        stops = entry.get("stopCount", entry.get("stops", 0))

        flights.append(
            NormalizedFlight(
                flight_number=flight_number,
                airline_code=carrier,
                airline_name="Turkish Airlines",
                operator=operator,
                origin=dep_port,
                destination=arr_port,
                departure_time=dep_time,
                arrival_time=arr_time,
                duration_minutes=duration_minutes,
                cabin_class=cabin_class,
                aircraft_type=aircraft_type,
                stops=stops,
                prices=[],  # Timetable has no pricing.
                source=DataSource.OFFICIAL_API,
                crawled_at=now,
            )
        )

    logger.info(
        "Parsed %d flights from TK official timetable %s->%s",
        len(flights),
        origin,
        destination,
    )
    return flights


def parse_official_availability(
    data: dict[str, Any],
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse the official ``/getAvailability`` API response.

    The availability endpoint returns flight options with fare families
    and pricing.  The exact response format will be determined once the
    API key is obtained; this parser provides best-effort handling of
    the expected structure.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    # Try common response envelopes.
    flight_list: list[dict[str, Any]] = []
    if isinstance(data, list):
        flight_list = data
    elif isinstance(data, dict):
        for key in ("data", "availabilityList", "flights", "flightList"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                flight_list = candidate
                break
            if isinstance(candidate, dict):
                for inner_key in ("availabilityList", "flights", "flightList"):
                    inner = candidate.get(inner_key)
                    if isinstance(inner, list):
                        flight_list = inner
                        break
                if flight_list:
                    break

    for entry in flight_list:
        flight_num = entry.get("flightNumber", entry.get("flightNo", ""))
        carrier = entry.get("airlineCode", entry.get("marketingAirlineCode", "TK"))
        flight_number = f"{carrier}{flight_num}" if flight_num else ""

        dep_str = entry.get("departureDateTime", entry.get("departureTime", ""))
        arr_str = entry.get("arrivalDateTime", entry.get("arrivalTime", ""))
        dep_time = _parse_dt(dep_str)
        arr_time = _parse_dt(arr_str)

        duration_str = entry.get("duration", entry.get("totalDuration", ""))
        duration_minutes = _parse_duration(duration_str) if duration_str else 0
        if not duration_minutes and dep_time and arr_time:
            diff = (arr_time - dep_time).total_seconds()
            if diff > 0:
                duration_minutes = int(diff / 60)

        origin = entry.get("departureAirportCode", entry.get("originAirportCode", ""))
        destination = entry.get(
            "arrivalAirportCode", entry.get("destinationAirportCode", "")
        )
        aircraft_type = entry.get("aircraftType", entry.get("equipmentCode"))
        operator = entry.get("operatingAirlineCode", carrier)
        stops = entry.get("stopCount", entry.get("stops", 0))

        # Extract prices from fare families.
        prices: list[NormalizedPrice] = []
        fare_families: list[dict[str, Any]] = entry.get("fareFamilyList", [])
        for ff in fare_families:
            amount = ff.get("price", ff.get("amount"))
            if amount is not None:
                prices.append(
                    NormalizedPrice(
                        amount=float(amount),
                        currency=ff.get("currency", ff.get("currencyCode", "USD")),
                        source=DataSource.OFFICIAL_API,
                        fare_class=ff.get("fareClass", ff.get("fareFamilyCode")),
                        crawled_at=now,
                    )
                )

        # Fallback: single price at entry level.
        if not prices:
            entry_price = entry.get("price", entry.get("totalPrice"))
            if entry_price is not None:
                currency = entry.get("currency", entry.get("currencyCode", "USD"))
                if isinstance(entry_price, dict):
                    amount_val = entry_price.get("amount")
                    currency = entry_price.get("currencyCode", currency)
                else:
                    amount_val = entry_price
                if amount_val is not None:
                    prices.append(
                        NormalizedPrice(
                            amount=float(amount_val),
                            currency=currency,
                            source=DataSource.OFFICIAL_API,
                            fare_class=None,
                            crawled_at=now,
                        )
                    )

        if flight_number:
            flights.append(
                NormalizedFlight(
                    flight_number=flight_number,
                    airline_code=carrier,
                    airline_name="Turkish Airlines",
                    operator=operator,
                    origin=origin,
                    destination=destination,
                    departure_time=dep_time,
                    arrival_time=arr_time,
                    duration_minutes=duration_minutes,
                    cabin_class=cabin_class,
                    aircraft_type=aircraft_type,
                    stops=stops,
                    prices=prices,
                    source=DataSource.OFFICIAL_API,
                    crawled_at=now,
                )
            )

    logger.info(
        "Parsed %d flights from TK official availability",
        len(flights),
    )
    return flights
