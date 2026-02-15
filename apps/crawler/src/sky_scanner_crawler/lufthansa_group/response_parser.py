"""Parse Lufthansa flight-schedules response into NormalizedFlight objects.

The Lufthansa flight-schedules API returns SSIM-style schedule data with
departure/arrival times encoded as **minutes from midnight** (e.g. 590 =
09:50 UTC).  Each schedule entry contains one or more ``legs`` (flight
segments).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sky_scanner_core.schemas import (
    CabinClass,
    DataSource,
    NormalizedFlight,
)

from .client import AIRLINE_NAMES

if TYPE_CHECKING:
    from datetime import date

logger = logging.getLogger(__name__)


def _minutes_to_time(
    base_date: date,
    minutes_from_midnight: int,
    date_diff: int = 0,
) -> datetime:
    """Convert minutes-from-midnight + day-offset into a UTC datetime."""
    dt = datetime(
        base_date.year,
        base_date.month,
        base_date.day,
        tzinfo=UTC,
    )
    dt += timedelta(days=date_diff, minutes=minutes_from_midnight)
    return dt


def parse_flight_schedules(
    schedules: list[dict[str, Any]],
    departure_date: date,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Lufthansa flight-schedules JSON into NormalizedFlight list.

    Parameters
    ----------
    schedules:
        Raw schedule objects returned by the flight-schedules API.
    departure_date:
        The requested departure date (used to build absolute datetimes).
    cabin_class:
        Requested cabin class (schedules don't carry price data, so we
        set this from the search request).
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    for sched in schedules:
        airline_code = sched.get("airline", "")
        flight_num_raw = sched.get("flightNumber", 0)
        suffix = sched.get("suffix", "")
        flight_number = f"{airline_code}{flight_num_raw}{suffix}"

        legs: list[dict[str, Any]] = sched.get("legs", [])
        if not legs:
            continue

        first_leg = legs[0]
        last_leg = legs[-1]

        origin = first_leg.get("origin", "")
        destination = last_leg.get("destination", "")

        # Departure: minutes-from-midnight UTC + day offset
        dep_minutes = first_leg.get("aircraftDepartureTimeUTC", 0)
        dep_day_diff = first_leg.get("aircraftDepartureTimeDateDiffUTC", 0)
        dep_time = _minutes_to_time(departure_date, dep_minutes, dep_day_diff)

        # Arrival: minutes-from-midnight UTC + day offset
        arr_minutes = last_leg.get("aircraftArrivalTimeUTC", 0)
        arr_day_diff = last_leg.get("aircraftArrivalTimeDateDiffUTC", 0)
        arr_time = _minutes_to_time(departure_date, arr_minutes, arr_day_diff)

        # Duration in minutes.
        duration_minutes = int((arr_time - dep_time).total_seconds() / 60)
        if duration_minutes < 0:
            # Safety: if times look bogus, skip.
            logger.warning("Negative duration for %s, skipping", flight_number)
            continue

        # Number of stops = number of legs - 1.
        stops = len(legs) - 1

        # Operating carrier from first leg.
        operator = first_leg.get("aircraftOwner", airline_code)

        # Aircraft type from first leg.
        aircraft_type = first_leg.get("aircraftType")

        airline_name = AIRLINE_NAMES.get(airline_code)

        # Schedules API does not return pricing, so we create the flight
        # without prices. Prices can be enriched later via Amadeus/other
        # sources.
        flights.append(
            NormalizedFlight(
                flight_number=flight_number,
                airline_code=airline_code,
                airline_name=airline_name,
                operator=operator,
                origin=origin,
                destination=destination,
                departure_time=dep_time,
                arrival_time=arr_time,
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
        "Parsed %d flights from Lufthansa schedules API",
        len(flights),
    )
    return flights
