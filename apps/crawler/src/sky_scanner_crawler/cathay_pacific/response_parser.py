"""Parse Cathay Pacific API responses into NormalizedFlight objects.

Two response formats are supported:

1. **Flight Timetable** (``flightTimetable`` endpoint)
   Returns flight schedule data with segment-level detail::

       {
           "flightScheduleList": [
               {
                   "flightNumber": "CX520",
                   "departureDate": "2026-03-15",
                   "departureTime": "08:15",
                   "arrivalDate": "2026-03-15",
                   "arrivalTime": "13:25",
                   "origin": "HKG",
                   "destination": "NRT",
                   "duration": "PT4H10M",
                   "aircraftType": "A350-900",
                   "operatingCarrier": "CX",
                   "stops": 0,
                   "cabinAvailability": {
                       "Y": {"available": true},
                       "J": {"available": true},
                       "F": {"available": false},
                   },
               }
           ]
       }

2. **Histogram / Fare Calendar** (``histogram`` endpoint)
   Returns daily lowest prices::

       {
           "dates": [
               {
                   "date": "2026-03-15",
                   "lowestPrice": {"amount": 4500.0, "currency": "USD"},
               }
           ]
       }

Note: The exact response structure may vary as Cathay Pacific updates
their API.  Parsers are written defensively to handle missing fields.
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

_CX_AIRLINE_CODE = "CX"
_CX_AIRLINE_NAME = "Cathay Pacific"

# ISO-8601 duration -> minutes.
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")

# CX cabin codes -> our CabinClass enum.
_CABIN_MAP: dict[str, CabinClass] = {
    "Y": CabinClass.ECONOMY,
    "W": CabinClass.PREMIUM_ECONOMY,
    "J": CabinClass.BUSINESS,
    "F": CabinClass.FIRST,
    "ECONOMY": CabinClass.ECONOMY,
    "PREMIUM_ECONOMY": CabinClass.PREMIUM_ECONOMY,
    "BUSINESS": CabinClass.BUSINESS,
    "FIRST": CabinClass.FIRST,
}


def _parse_duration(iso_dur: str) -> int:
    """Convert ISO-8601 duration to minutes (e.g. ``PT4H10M`` -> 250)."""
    m = _DURATION_RE.match(iso_dur)
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return hours * 60 + minutes


def _parse_dt(dt_str: str) -> datetime:
    """Parse a datetime string into a timezone-aware UTC datetime.

    Handles ISO formats like ``2026-03-15T08:15:00`` as well as
    separate date + time fields.
    """
    if not dt_str:
        return datetime.now(tz=UTC)
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        pass
    # Fallback: date-only string.
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(tz=UTC)


def _combine_date_time(date_str: str, time_str: str) -> datetime:
    """Combine separate date and time strings into a UTC datetime.

    Parameters
    ----------
    date_str:
        Date in ``YYYY-MM-DD`` format.
    time_str:
        Time in ``HH:MM`` or ``HH:MM:SS`` format.
    """
    combined = f"{date_str}T{time_str}"
    return _parse_dt(combined)


# ------------------------------------------------------------------
# Timetable parser
# ------------------------------------------------------------------


def parse_timetable(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse the ``flightTimetable`` API response.

    The response may use different field names depending on the API
    version.  This parser tries multiple known structures defensively.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    # Try different known response structures.
    schedule_list: list[dict[str, Any]] = (
        data.get("flightScheduleList", [])
        or data.get("schedules", [])
        or data.get("data", {}).get("flightScheduleList", [])
        or data.get("data", {}).get("schedules", [])
        or data.get("flights", [])
        or data.get("data", {}).get("flights", [])
    )

    # Some responses wrap in a results array.
    if not schedule_list and isinstance(data.get("results"), list):
        schedule_list = data["results"]

    for entry in schedule_list:
        # Flight number.
        flight_number = (
            entry.get("flightNumber", "")
            or entry.get("flightNo", "")
            or entry.get("flight", "")
        )
        if not flight_number:
            carrier = entry.get("operatingCarrier", _CX_AIRLINE_CODE)
            fn = entry.get("number", "")
            flight_number = f"{carrier}{fn}" if fn else ""

        if not flight_number:
            continue

        # Origin / destination.
        flt_origin = (
            entry.get("origin", "")
            or entry.get("departureAirport", "")
            or entry.get("from", "")
            or origin
        )
        flt_dest = (
            entry.get("destination", "")
            or entry.get("arrivalAirport", "")
            or entry.get("to", "")
            or destination
        )

        # Departure / arrival times.
        dep_date = entry.get("departureDate", "")
        dep_time_str = entry.get("departureTime", "")
        arr_date = entry.get("arrivalDate", dep_date)
        arr_time_str = entry.get("arrivalTime", "")

        if dep_date and dep_time_str:
            dep_time = _combine_date_time(dep_date, dep_time_str)
        else:
            dep_dt_str = entry.get("departureDateTime", dep_date)
            dep_time = _parse_dt(dep_dt_str)

        if arr_date and arr_time_str:
            arr_time = _combine_date_time(arr_date, arr_time_str)
        else:
            arr_dt_str = entry.get("arrivalDateTime", arr_date)
            arr_time = _parse_dt(arr_dt_str)

        # Duration.
        duration_str = entry.get("duration", "")
        duration_minutes = _parse_duration(duration_str) if duration_str else 0
        if not duration_minutes and dep_time and arr_time:
            diff = (arr_time - dep_time).total_seconds()
            if diff > 0:
                duration_minutes = int(diff / 60)

        # Carrier info.
        airline_code = entry.get("marketingCarrier", _CX_AIRLINE_CODE)
        operator = entry.get("operatingCarrier", airline_code)
        airline_name = _CX_AIRLINE_NAME
        if operator == "KA":
            airline_name = "Cathay Dragon"
        elif operator == "HX":
            airline_name = "Hong Kong Airlines"

        # Aircraft.
        aircraft = entry.get("aircraftType") or entry.get("equipment")

        # Stops.
        stops = entry.get("stops", entry.get("numberOfStops", 0))
        if isinstance(stops, str):
            try:
                stops = int(stops)
            except ValueError:
                stops = 0

        # Prices -- timetable may or may not include fare data.
        prices: list[NormalizedPrice] = []
        price_data = entry.get("lowestFare") or entry.get("price")
        if price_data and isinstance(price_data, dict):
            amount = price_data.get("amount")
            if amount is not None and float(amount) > 0:
                prices.append(
                    NormalizedPrice(
                        amount=float(amount),
                        currency=price_data.get("currency", "USD"),
                        source=DataSource.DIRECT_CRAWL,
                        fare_class=None,
                        crawled_at=now,
                    )
                )

        # Cabin availability / fare data by cabin.
        cabin_avail = entry.get("cabinAvailability", {})
        if cabin_avail and isinstance(cabin_avail, dict):
            for cab_code, cab_info in cabin_avail.items():
                if not isinstance(cab_info, dict):
                    continue
                fare = cab_info.get("price") or cab_info.get("fare")
                if fare and isinstance(fare, dict):
                    amt = fare.get("amount")
                    if amt is not None and float(amt) > 0:
                        prices.append(
                            NormalizedPrice(
                                amount=float(amt),
                                currency=fare.get("currency", "USD"),
                                source=DataSource.DIRECT_CRAWL,
                                fare_class=cab_code,
                                crawled_at=now,
                            )
                        )

        flights.append(
            NormalizedFlight(
                flight_number=flight_number,
                airline_code=airline_code,
                airline_name=airline_name,
                operator=operator,
                origin=flt_origin,
                destination=flt_dest,
                departure_time=dep_time,
                arrival_time=arr_time,
                duration_minutes=duration_minutes,
                cabin_class=cabin_class,
                aircraft_type=aircraft,
                stops=stops,
                prices=prices,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    logger.info(
        "Parsed %d flights from CX timetable %s->%s",
        len(flights),
        origin,
        destination,
    )
    return flights


# ------------------------------------------------------------------
# Histogram / fare calendar parser
# ------------------------------------------------------------------


def parse_histogram(
    data: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Parse the ``histogram`` API fare calendar response.

    Creates one NormalizedFlight per day with the lowest available price.
    Flight number is synthesized as ``CX-{origin}{destination}`` since
    the histogram does not provide individual flight identity.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    # Try different response structures.
    date_list: list[dict[str, Any]] = (
        data.get("dates", [])
        or data.get("data", {}).get("dates", [])
        or data.get("histogram", [])
        or data.get("data", {}).get("histogram", [])
        or data.get("calendarDates", [])
        or data.get("data", {}).get("calendarDates", [])
    )

    # Some responses use a flat daily prices structure.
    if not date_list:
        daily = data.get("dailyPrices", data.get("data", {}).get("dailyPrices", []))
        if daily:
            date_list = daily

    for entry in date_list:
        date_str = (
            entry.get("date", "")
            or entry.get("departureDate", "")
            or entry.get("day", "")
        )
        if not date_str:
            continue

        # Price extraction -- handle various structures.
        price_data = (
            entry.get("lowestPrice")
            or entry.get("price")
            or entry.get("cheapestPrice")
            or entry.get("startingPrice")
        )

        amount: float | None = None
        currency = "USD"

        if price_data and isinstance(price_data, dict):
            amount = price_data.get("amount")
            currency = price_data.get("currency", price_data.get("currencyCode", "USD"))
        elif isinstance(entry.get("amount"), (int, float)):
            amount = entry["amount"]
            currency = entry.get("currency", entry.get("currencyCode", "USD"))
        elif isinstance(price_data, (int, float)):
            amount = price_data

        if amount is None or float(amount) <= 0:
            continue

        dep_time = _parse_dt(date_str)

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
                flight_number=f"{_CX_AIRLINE_CODE}-{origin}{destination}",
                airline_code=_CX_AIRLINE_CODE,
                airline_name=_CX_AIRLINE_NAME,
                origin=origin,
                destination=destination,
                departure_time=dep_time,
                arrival_time=dep_time,  # Not available from calendar API.
                duration_minutes=0,
                cabin_class=cabin_class,
                stops=0,
                prices=prices,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    logger.info(
        "Parsed %d daily prices from CX histogram %s->%s",
        len(flights),
        origin,
        destination,
    )
    return flights
