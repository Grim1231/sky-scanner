"""Parse Lufthansa Operations/Schedules response into NormalizedFlight objects.

The ``/v1/operations/schedules`` endpoint returns schedule data with
local departure/arrival times in ISO format.  Each schedule entry has
either a single ``Flight`` dict (direct) or a list of ``Flight`` dicts
(connection with multiple segments).

Response envelope::

    {
      "ScheduleResource": {
        "Schedule": [
          {
            "TotalJourney": {"Duration": "PT11H40M"},
            "Flight": {
              "Departure": {"AirportCode": "FRA", ...},
              "Arrival":   {"AirportCode": "ICN", ...},
              "MarketingCarrier": {"AirlineID": "LH", ...},
              "Equipment": {"AircraftCode": "359"},
              "Details": {"Stops": {"StopQuantity": 0}}
            }
          },
          ...
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
)

from .client import AIRLINE_NAMES

logger = logging.getLogger(__name__)

# Regex to parse ISO 8601 duration like "PT11H40M" or "PT1H5M".
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")


def _parse_duration_minutes(duration_str: str) -> int:
    """Parse an ISO 8601 duration string into total minutes."""
    m = _DURATION_RE.match(duration_str)
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return hours * 60 + minutes


def _parse_local_datetime(dt_str: str) -> datetime:
    """Parse a local datetime string like '2026-02-22T15:10' to UTC-naive datetime.

    The API returns local times without timezone info.  We store them
    as-is (local schedule time) and mark as UTC-aware for consistency
    with the NormalizedFlight schema.  True timezone conversion would
    require airport timezone data.
    """
    # Handle both "2026-02-22T15:10" and "2026-02-22T15:10:00" formats.
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(dt_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    # Fallback: return epoch and log warning.
    logger.warning("Could not parse datetime: %s", dt_str)
    return datetime(2000, 1, 1, tzinfo=UTC)


def parse_flight_schedules(
    schedules: list[dict[str, Any]],
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Lufthansa Operations/Schedules JSON into NormalizedFlight list.

    Parameters
    ----------
    schedules:
        Raw schedule objects from ``ScheduleResource.Schedule``.
    cabin_class:
        Requested cabin class (schedules don't carry price data, so we
        set this from the search request).
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    for sched in schedules:
        try:
            flight_data = sched.get("Flight", {})

            # Normalise to list of segments.
            if isinstance(flight_data, dict):
                segments: list[dict[str, Any]] = [flight_data]
            elif isinstance(flight_data, list):
                segments = flight_data
            else:
                continue

            if not segments:
                continue

            first_seg = segments[0]
            last_seg = segments[-1]

            # Origin / Destination
            origin = first_seg.get("Departure", {}).get("AirportCode", "")
            destination = last_seg.get("Arrival", {}).get("AirportCode", "")

            # Departure / Arrival times (local schedule times)
            dep_dt_str = (
                first_seg.get("Departure", {})
                .get("ScheduledTimeLocal", {})
                .get("DateTime", "")
            )
            arr_dt_str = (
                last_seg.get("Arrival", {})
                .get("ScheduledTimeLocal", {})
                .get("DateTime", "")
            )
            if not dep_dt_str or not arr_dt_str:
                continue

            dep_time = _parse_local_datetime(dep_dt_str)
            arr_time = _parse_local_datetime(arr_dt_str)

            # Duration from TotalJourney (more reliable than computing from
            # local times which may cross timezones).
            total_journey = sched.get("TotalJourney", {})
            duration_str = total_journey.get("Duration", "")
            duration_minutes = _parse_duration_minutes(duration_str)
            if duration_minutes <= 0:
                # Fallback: compute from times.
                duration_minutes = max(
                    0, int((arr_time - dep_time).total_seconds() / 60)
                )

            # Marketing carrier from first segment.
            carrier = first_seg.get("MarketingCarrier", {})
            airline_code = carrier.get("AirlineID", "")
            flight_num = carrier.get("FlightNumber", "")
            flight_number = f"{airline_code}{flight_num}"

            # For connections, build a combined flight number.
            if len(segments) > 1:
                all_nums = []
                for seg in segments:
                    c = seg.get("MarketingCarrier", {})
                    aid = c.get("AirlineID", "")
                    fnum = c.get("FlightNumber", "")
                    all_nums.append(f"{aid}{fnum}")
                flight_number = " / ".join(all_nums)

            # Number of stops.
            if len(segments) == 1:
                stops = (
                    first_seg.get("Details", {}).get("Stops", {}).get("StopQuantity", 0)
                )
            else:
                # Connection: stops = number of intermediate airports.
                stops = len(segments) - 1

            # Aircraft type from first segment.
            aircraft_type = first_seg.get("Equipment", {}).get("AircraftCode")

            airline_name = AIRLINE_NAMES.get(airline_code)

            flights.append(
                NormalizedFlight(
                    flight_number=flight_number,
                    airline_code=airline_code,
                    airline_name=airline_name,
                    operator=airline_code,
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
        except Exception:
            logger.exception("Failed to parse Lufthansa schedule entry")
            continue

    logger.info(
        "Parsed %d flights from Lufthansa schedules API",
        len(flights),
    )
    return flights
