"""Parse Vietnam Airlines middleware API responses into NormalizedFlight objects.

The VN middleware exposes two complementary endpoints:

1. **Schedule table** (``/public/flight/schedule-table``)::

    data.departureFlight
      dictionaries  {aircraft, airline, location}
      scheduleItems[]
        connectedFlights[]          <-- array of legs; len>1 = connecting
          flightInfo
            marketingAirlineCode, marketingFlightNumber
            operatingAirlineCode, operatingAirlineName
            airEquipmentCode
            departureLocation {locationCode, dateTime, dateTimeZoneGmtOffset, terminal}
            arrivalLocation   {locationCode, dateTime, dateTimeZoneGmtOffset, terminal}
            duration (seconds)
          numberOfStops
          operatingDays ["monday", "tuesday", ...]
          validityPeriod {start, end}

2. **Air best price** (``/public/booking/air-best-price``)::

    data.dictionaries.currency  {code: {decimalPlaces, name}}
    data.prices[]
      departureDate
      returnDate  (present only for round-trip)
      price[]
        base, total, totalTaxes, currencyCode

This module provides parsers for both responses and a combiner that
merges schedule flights with per-day prices.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sky_scanner_core.schemas import (
    CabinClass,
    DataSource,
    NormalizedFlight,
    NormalizedPrice,
)

logger = logging.getLogger(__name__)

_VN_CODE = "VN"
_VN_NAME = "Vietnam Airlines"

# Aircraft dictionary fallback (supplement API dictionaries).
_EQUIPMENT_NAMES: dict[str, str] = {
    "320": "Airbus A320",
    "321": "Airbus A321",
    "350": "Airbus A350",
    "359": "Airbus A350-900",
    "787": "Boeing 787",
    "789": "Boeing 787-9",
    "333": "Airbus A330-300",
    "77W": "Boeing 777-300ER",
}

_DAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def _parse_local_datetime(dt_str: str, gmt_offset: float = 7.0) -> datetime:
    """Parse VN API datetime string into a UTC-aware datetime.

    The API returns local airport times (e.g. ``2026-03-01T09:25:00``)
    with a ``dateTimeZoneGmtOffset`` (e.g. ``7.0`` for Vietnam,
    ``9.0`` for Korea).  We convert to UTC for storage consistency.
    """
    try:
        dt = datetime.fromisoformat(dt_str)
    except ValueError:
        dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")

    # Apply GMT offset to convert local -> UTC
    utc_dt = dt - timedelta(hours=gmt_offset)
    return utc_dt.replace(tzinfo=UTC)


def _itinerary_matches_date(
    item: dict[str, Any],
    target_date: str,
    target_day_name: str,
) -> bool:
    """Check if a schedule item (itinerary) departs on the target date.

    An itinerary matches if the *first* leg's departure datetime starts
    with the target date, OR the first leg's validity period spans the
    target date AND the target day is in its ``operatingDays``.
    """
    legs: list[dict[str, Any]] = item.get("connectedFlights", [])
    if not legs:
        return False

    first_leg = legs[0]
    info = first_leg.get("flightInfo", {})
    dep = info.get("departureLocation", {})
    dep_dt = dep.get("dateTime", "")

    if dep_dt.startswith(target_date):
        return True

    if target_day_name:
        validity = first_leg.get("validityPeriod", {})
        start = validity.get("start", "")
        end = validity.get("end", "")
        operating_days: list[str] = first_leg.get("operatingDays", [])
        if (
            start
            and end
            and start[:10] <= target_date <= end[:10]
            and target_day_name in operating_days
        ):
            return True

    return False


def _resolve_aircraft(
    equipment_code: str,
    aircraft_dict: dict[str, str],
) -> str | None:
    """Resolve equipment code to a human-readable aircraft name."""
    return (
        aircraft_dict.get(equipment_code)
        or _EQUIPMENT_NAMES.get(equipment_code)
        or equipment_code
        or None
    )


def parse_flight_schedule(
    raw: dict[str, Any],
    target_date: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse flight schedule response into NormalizedFlight list.

    Each ``scheduleItem`` is one itinerary that may contain 1 leg
    (direct) or multiple legs (connecting via a hub like HAN).

    For direct flights, we produce a ``NormalizedFlight`` with
    ``stops=0``.  For connecting itineraries, we produce one
    ``NormalizedFlight`` spanning the full origin-to-destination
    journey with ``stops`` equal to the number of intermediate points.
    The flight number is taken from the first leg.

    Parameters
    ----------
    raw:
        Full ``schedule-table`` API response.
    target_date:
        ISO date string to filter flights (e.g. ``"2026-03-01"``).
    cabin_class:
        Cabin class from the search request (schedule API
        does not include cabin info).

    Returns
    -------
    list[NormalizedFlight]
        Flights with schedule data but no pricing.
    """
    from datetime import date as date_type

    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    departure_data = raw.get("data", {}).get("departureFlight", {})
    if not departure_data:
        return flights

    dictionaries = departure_data.get("dictionaries", {})
    aircraft_dict: dict[str, str] = dictionaries.get("aircraft", {})
    airline_dict: dict[str, str] = dictionaries.get("airline", {})

    # Determine target day name for validity-period matching
    try:
        target_dt = date_type.fromisoformat(target_date)
        target_day_name = _DAY_NAMES[target_dt.weekday()]
    except (ValueError, IndexError):
        target_day_name = ""

    schedule_items: list[dict[str, Any]] = departure_data.get("scheduleItems", [])
    seen_flights: set[str] = set()

    for item in schedule_items:
        if not _itinerary_matches_date(item, target_date, target_day_name):
            continue

        legs: list[dict[str, Any]] = item.get("connectedFlights", [])
        if not legs:
            continue

        first_leg = legs[0]
        last_leg = legs[-1]

        first_info = first_leg.get("flightInfo", {})
        last_info = last_leg.get("flightInfo", {})

        # Overall departure from first leg, arrival from last leg
        dep_loc = first_info.get("departureLocation", {})
        arr_loc = last_info.get("arrivalLocation", {})

        dep_dt_str = dep_loc.get("dateTime", "")
        arr_dt_str = arr_loc.get("dateTime", "")
        if not dep_dt_str or not arr_dt_str:
            continue

        dep_offset = dep_loc.get("dateTimeZoneGmtOffset", 7.0)
        arr_offset = arr_loc.get("dateTimeZoneGmtOffset", 7.0)

        try:
            departure_dt = _parse_local_datetime(dep_dt_str, dep_offset)
            arrival_dt = _parse_local_datetime(arr_dt_str, arr_offset)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid datetime in VN schedule: dep=%s arr=%s",
                dep_dt_str,
                arr_dt_str,
            )
            continue

        # Total duration: sum of all leg durations, or compute from endpoints
        total_duration_secs = sum(
            leg.get("flightInfo", {}).get("duration", 0) for leg in legs
        )
        if total_duration_secs:
            duration_minutes = int(total_duration_secs) // 60
        else:
            delta = arrival_dt - departure_dt
            duration_minutes = max(int(delta.total_seconds() / 60), 0)

        # For connecting flights, total duration includes layover time
        if len(legs) > 1:
            delta = arrival_dt - departure_dt
            duration_minutes = max(int(delta.total_seconds() / 60), 0)

        if duration_minutes <= 0:
            continue

        # Flight number from first leg
        mkt_airline = first_info.get("marketingAirlineCode", _VN_CODE)
        mkt_number = first_info.get("marketingFlightNumber", "")
        flight_number = f"{mkt_airline}{mkt_number}"

        # For connecting flights, append all leg numbers
        if len(legs) > 1:
            all_numbers = []
            for leg in legs:
                leg_info = leg.get("flightInfo", {})
                code = leg_info.get("marketingAirlineCode", "")
                num = leg_info.get("marketingFlightNumber", "")
                all_numbers.append(f"{code}{num}")
            flight_number = "/".join(all_numbers)

        # Dedup by itinerary flight number(s) + first departure datetime
        dedup = f"{flight_number}:{dep_dt_str}"
        if dedup in seen_flights:
            continue
        seen_flights.add(dedup)

        op_airline = first_info.get("operatingAirlineCode", mkt_airline)
        op_name = first_info.get("operatingAirlineName", "")
        airline_name = airline_dict.get(mkt_airline, op_name or _VN_NAME)

        equipment_code = first_info.get("airEquipmentCode", "")
        aircraft_type = _resolve_aircraft(equipment_code, aircraft_dict)

        origin = dep_loc.get("locationCode", "")
        destination = arr_loc.get("locationCode", "")

        # Stops = number of intermediate connection points
        stops = len(legs) - 1

        flights.append(
            NormalizedFlight(
                flight_number=flight_number,
                airline_code=mkt_airline,
                airline_name=airline_name,
                operator=op_airline,
                origin=origin,
                destination=destination,
                departure_time=departure_dt,
                arrival_time=arrival_dt,
                duration_minutes=duration_minutes,
                cabin_class=cabin_class,
                aircraft_type=aircraft_type,
                stops=stops,
                prices=[],
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    logger.info(
        "Parsed %d VN schedule flights for %s",
        len(flights),
        target_date,
    )
    return flights


def parse_best_prices(
    raw: dict[str, Any],
) -> dict[str, NormalizedPrice]:
    """Parse air-best-price response into a per-date price map.

    Parameters
    ----------
    raw:
        Full ``air-best-price`` API response.

    Returns
    -------
    dict[str, NormalizedPrice]
        Mapping of departure date (ISO string) to the lowest
        NormalizedPrice for that date.
    """
    now = datetime.now(tz=UTC)
    price_map: dict[str, NormalizedPrice] = {}

    data = raw.get("data", {})
    prices: list[dict[str, Any]] = data.get("prices", [])
    currency_dict: dict[str, Any] = data.get("dictionaries", {}).get("currency", {})

    for entry in prices:
        dep_date = entry.get("departureDate", "")
        if not dep_date:
            continue

        price_list: list[dict[str, Any]] = entry.get("price", [])
        if not price_list:
            continue

        price_info = price_list[0]
        currency_code = price_info.get("currencyCode", "KRW")
        total_raw = price_info.get("total", "0")

        # Apply decimal places from dictionary
        decimal_places = currency_dict.get(currency_code, {}).get("decimalPlaces", 0)
        total = int(total_raw)
        if decimal_places > 0:
            total = total / (10**decimal_places)

        price_map[dep_date] = NormalizedPrice(
            amount=float(total),
            currency=currency_code,
            source=DataSource.DIRECT_CRAWL,
            fare_class=None,
            crawled_at=now,
        )

    return price_map


def merge_schedule_with_prices(
    flights: list[NormalizedFlight],
    price_map: dict[str, NormalizedPrice],
    target_date: str | None = None,
) -> list[NormalizedFlight]:
    """Attach prices from the fare calendar to schedule flights.

    The fare calendar gives the lowest price per departure date
    (in *local* airport time).  We attach this price to every
    flight on that date.

    Since ``NormalizedFlight.departure_time`` is stored in UTC,
    directly formatting it may produce a different date than the
    fare calendar uses.  If ``target_date`` is provided, all
    flights are assumed to depart on that local date and matched
    accordingly.  Otherwise we try both the UTC date and one day
    ahead (to cover UTC-behind-local timezone differences).

    Parameters
    ----------
    flights:
        Flights parsed from the schedule-table endpoint.
    price_map:
        Per-date prices from ``parse_best_prices``.
    target_date:
        The local departure date (ISO string) used in the
        original search.  If provided, used as the primary
        price lookup key.

    Returns
    -------
    list[NormalizedFlight]
        Same flights with prices attached where available.
    """
    for flight in flights:
        if flight.prices:
            continue

        # Try target_date first (the local date the user searched)
        if target_date:
            price = price_map.get(target_date)
            if price:
                flight.prices.append(price)
                continue

        # Fallback: try UTC date and adjacent dates
        dep_date_utc = flight.departure_time.strftime("%Y-%m-%d")
        price = price_map.get(dep_date_utc)
        if price:
            flight.prices.append(price)
            continue

        # Try next day (handles UTC being behind local time)
        from datetime import timedelta

        next_day = (flight.departure_time + timedelta(days=1)).strftime("%Y-%m-%d")
        price = price_map.get(next_day)
        if price:
            flight.prices.append(price)

    n_priced = sum(1 for f in flights if f.prices)
    logger.info(
        "Merged prices: %d/%d flights have pricing",
        n_priced,
        len(flights),
    )
    return flights
