"""Parse Philippine Airlines flight status response into NormalizedFlight objects.

The PAL flight status API returns schedule data (no fares/prices).
Each response contains ``Details.leg[]`` with per-leg schedule info.

Response hierarchy::

    Details
      leg[]
        fltId        -- e.g. "PR 0400"
        acOwn        -- operating airline (always "PR")
        depStn       -- departure IATA code
        arrStn       -- arrival IATA code
        std          -- scheduled departure time (local)
        sta          -- scheduled arrival time (local)
        etd          -- estimated departure time
        eta          -- estimated arrival time
        atd          -- actual departure time
        ata          -- actual arrival time
        dep_airport  -- departure airport name
        arr_airport  -- arrival airport name
        datop        -- date of operation (YYYY-MM-DD)
        status       -- "SCH", "DEP", "ATA", etc.
        StatusGeneral -- human-readable status
      codeshare[]
        operatingFlightNum  -- e.g. "PR 0400"
        marketingFlightNum  -- e.g. "NH 5609"
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sky_scanner_core.schemas import (
    CabinClass,
    DataSource,
    NormalizedFlight,
)

logger = logging.getLogger(__name__)

_PR_CODE = "PR"
_PR_NAME = "Philippine Airlines"

_PAL_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


def _parse_pal_datetime(dt_str: str) -> datetime:
    """Parse PAL datetime string ``YYYY-MM-DD HH:MM:SS`` into UTC datetime.

    PAL returns local airport times without timezone info.  We store
    them as-is with UTC tzinfo for consistency with other crawlers;
    downstream consumers should be aware these are local airport times.
    """
    try:
        dt = datetime.strptime(dt_str, _PAL_DATETIME_FMT)
    except ValueError:
        dt = datetime.fromisoformat(dt_str)
    return dt.replace(tzinfo=UTC)


def parse_flight_status(
    raw: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert PAL flight status response into NormalizedFlight list.

    Parameters
    ----------
    raw:
        Full API response JSON.
    origin:
        Requested origin IATA code.
    destination:
        Requested destination IATA code.
    cabin_class:
        Cabin class from the search request (schedule data has no
        cabin info, so this is used as the default).

    Returns
    -------
    list[NormalizedFlight]
        Parsed flights (without pricing data).
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    details = raw.get("Details", {})
    if not details or details.get("status") != "okay":
        return flights

    legs: list[dict[str, Any]] = details.get("leg", [])

    # Build codeshare map: operating flight -> list of marketing flights
    codeshares: dict[str, list[str]] = {}
    for cs in details.get("codeshare", []):
        op_flt = cs.get("operatingFlightNum", "")
        mkt_flt = cs.get("marketingFlightNum", "")
        if op_flt and mkt_flt:
            codeshares.setdefault(op_flt, []).append(mkt_flt)

    seen_flight_ids: set[str] = set()

    for leg in legs:
        flight_id = leg.get("fltId", "")
        if not flight_id:
            continue

        # Deduplicate legs with the same flight ID on the same date
        datop = leg.get("datop", "")
        dedup_key = f"{flight_id}:{datop}"
        if dedup_key in seen_flight_ids:
            continue
        seen_flight_ids.add(dedup_key)

        # Use scheduled times (std/sta) as the primary times
        dep_str = leg.get("std", "")
        arr_str = leg.get("sta", "")

        if not dep_str or not arr_str:
            continue

        try:
            departure_dt = _parse_pal_datetime(dep_str)
            arrival_dt = _parse_pal_datetime(arr_str)
        except (ValueError, IndexError):
            logger.warning(
                "Invalid datetime in PAL response: dep=%s arr=%s",
                dep_str,
                arr_str,
            )
            continue

        # Compute duration in minutes
        delta = arrival_dt - departure_dt
        # Handle cross-day flights (arrival < departure means next day)
        total_seconds = delta.total_seconds()
        if total_seconds < 0:
            # Arrival is the next day (or crosses dateline)
            total_seconds += 86400  # 24 hours
        duration_minutes = max(int(total_seconds / 60), 0)

        # Extract flight number parts
        # fltId format: "PR 0400" -> airline "PR", number "0400"
        parts = flight_id.split()
        airline_code = parts[0] if parts else _PR_CODE
        flight_number = flight_id.replace(" ", "")

        # Operating airline
        operator = leg.get("acOwn", airline_code)

        # Airports
        dep_station = leg.get("depStn", origin.upper())
        arr_station = leg.get("arrStn", destination.upper())

        flights.append(
            NormalizedFlight(
                flight_number=flight_number,
                airline_code=airline_code,
                airline_name=_PR_NAME if airline_code == _PR_CODE else None,
                operator=operator,
                origin=dep_station,
                destination=arr_station,
                departure_time=departure_dt,
                arrival_time=arrival_dt,
                duration_minutes=duration_minutes,
                cabin_class=cabin_class,
                aircraft_type=None,  # Not provided by flight status API
                stops=0,  # Direct flights (each leg is a single segment)
                prices=[],  # No fare data from flight status API
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    logger.info(
        "Parsed %d flights for %s->%s from Philippine Airlines",
        len(flights),
        origin,
        destination,
    )
    return flights
