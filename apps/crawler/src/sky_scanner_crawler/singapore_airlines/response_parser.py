"""Parse Singapore Airlines Flight Availability response into NormalizedFlight objects.

The SQ NDC API returns a JSON response with ``recommendations``, each
containing ``segmentBounds`` with nested ``segments`` and ``legs``.
Each recommendation also carries fare family details and per-passenger
pricing with tax breakdown.

Response hierarchy::

    response
      recommendations[]
        segmentBounds[]
          segments[]
            legs[]
              flightNumber, departureDateTime, arrivalDateTime,
              operatingAirline, marketingAirline, aircraft,
              flightDuration (seconds), stops[]
          fareFamily, cabinClass, sellingClass
          fareSummary
            fareTotal { totalAmount, amountWithoutTax, tax }
            fareDetailsPerAdult { totalAmount, ... }
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sky_scanner_core.schemas import (
    CabinClass,
    DataSource,
    NormalizedFlight,
    NormalizedPrice,
)

logger = logging.getLogger(__name__)

_SQ_CODE = "SQ"
_SQ_NAME = "Singapore Airlines"

# Map SQ API cabin codes back to our CabinClass enum.
_CABIN_REVERSE_MAP: dict[str, CabinClass] = {
    "Y": CabinClass.ECONOMY,
    "M": CabinClass.ECONOMY,
    "W": CabinClass.PREMIUM_ECONOMY,
    "S": CabinClass.PREMIUM_ECONOMY,
    "J": CabinClass.BUSINESS,
    "C": CabinClass.BUSINESS,
    "F": CabinClass.FIRST,
    "R": CabinClass.FIRST,
}

_SQ_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


def _parse_sq_datetime(dt_str: str) -> datetime:
    """Parse SQ datetime string ``yyyy-MM-dd HH:mm:ss`` into a UTC datetime.

    SQ returns local times without timezone info.  We store them as-is
    with UTC tzinfo for consistency with other crawlers; downstream
    consumers should be aware these are local airport times.
    """
    try:
        dt = datetime.strptime(dt_str, _SQ_DATETIME_FMT)
    except ValueError:
        # Fallback: try ISO format
        dt = datetime.fromisoformat(dt_str)
    return dt.replace(tzinfo=UTC)


def _resolve_cabin_class(
    cabin_code: str | None,
    fallback: CabinClass,
) -> CabinClass:
    """Resolve SQ cabin code to internal CabinClass, with fallback."""
    if cabin_code:
        return _CABIN_REVERSE_MAP.get(cabin_code.upper(), fallback)
    return fallback


def parse_flight_availability(
    raw: dict[str, Any],
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert SQ Flight Availability response into NormalizedFlight list.

    Parameters
    ----------
    raw:
        Full API response JSON (must have ``status == "SUCCESS"``).
    origin:
        Requested origin IATA code.
    destination:
        Requested destination IATA code.
    cabin_class:
        Fallback cabin class from the search request.

    Returns
    -------
    list[NormalizedFlight]
        Parsed flights with pricing data.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    response = raw.get("response", {})
    if not response:
        return flights

    currency_info = response.get("currency", {})
    currency_code = currency_info.get("code", "SGD")

    recommendations: list[dict[str, Any]] = response.get("recommendations", [])

    for rec in recommendations:
        segment_bounds: list[dict[str, Any]] = rec.get("segmentBounds", [])

        for bound in segment_bounds:
            # Fare information for this bound
            fare_family = bound.get("fareFamily", "")
            selling_class = bound.get("sellingClass", "")
            bound_cabin_code = bound.get("cabinClass")
            resolved_cabin = _resolve_cabin_class(bound_cabin_code, cabin_class)

            # Price extraction
            fare_summary: dict[str, Any] = bound.get("fareSummary", {})
            fare_total: dict[str, Any] = fare_summary.get("fareTotal", {})
            total_amount = fare_total.get("totalAmount", 0)

            # Per-adult details for fare_class labeling
            per_adult: dict[str, Any] = fare_summary.get("fareDetailsPerAdult", {})
            per_adult_total = per_adult.get("totalAmount", total_amount)

            segments: list[dict[str, Any]] = bound.get("segments", [])

            for segment in segments:
                legs: list[dict[str, Any]] = segment.get("legs", [])
                if not legs:
                    continue

                first_leg = legs[0]
                last_leg = legs[-1]

                # Overall segment departure/arrival
                seg_dep_str = segment.get(
                    "departureDateTime",
                    first_leg.get("departureDateTime", ""),
                )
                seg_arr_str = segment.get(
                    "arrivalDateTime",
                    last_leg.get("arrivalDateTime", ""),
                )

                if not seg_dep_str or not seg_arr_str:
                    continue

                try:
                    departure_dt = _parse_sq_datetime(seg_dep_str)
                    arrival_dt = _parse_sq_datetime(seg_arr_str)
                except (ValueError, IndexError):
                    logger.warning(
                        "Invalid datetime in SQ response: dep=%s arr=%s",
                        seg_dep_str,
                        seg_arr_str,
                    )
                    continue

                # Trip duration from segment or computed from legs
                trip_duration_secs = segment.get("tripDuration", 0)
                if trip_duration_secs:
                    duration_minutes = int(trip_duration_secs) // 60
                else:
                    # Fallback: sum leg durations
                    duration_minutes = sum(
                        int(leg.get("flightDuration", 0)) // 60 for leg in legs
                    )

                if duration_minutes <= 0:
                    # Last resort: compute from departure/arrival
                    delta = arrival_dt - departure_dt
                    duration_minutes = max(int(delta.total_seconds() / 60), 0)

                # Flight number from first leg
                flight_number = first_leg.get("flightNumber", "")
                if not flight_number:
                    # Build from marketing airline
                    mkt = first_leg.get("marketingAirline", {})
                    flight_number = f"{mkt.get('code', 'SQ')}????"

                # Operating and marketing airlines
                operating = first_leg.get("operatingAirline", {})
                marketing = first_leg.get("marketingAirline", {})
                airline_code = marketing.get("code", _SQ_CODE)
                airline_name = marketing.get("name", _SQ_NAME)
                operator = operating.get("code", airline_code)

                # Segment origin/destination
                seg_origin = first_leg.get(
                    "originAirportCode",
                    segment.get("originAirportCode", origin),
                )
                seg_destination = last_leg.get(
                    "destinationAirportCode",
                    segment.get("destinationAirportCode", destination),
                )

                # Aircraft type
                aircraft_info = first_leg.get("aircraft", {})
                aircraft_type = aircraft_info.get("code") or aircraft_info.get("name")

                # Number of stops = number of legs - 1
                stops = len(legs) - 1

                # Build price
                prices: list[NormalizedPrice] = []
                if per_adult_total and float(per_adult_total) > 0:
                    fare_label = (
                        f"{selling_class}/{fare_family}"
                        if fare_family
                        else selling_class
                    )
                    prices.append(
                        NormalizedPrice(
                            amount=float(per_adult_total),
                            currency=currency_code,
                            source=DataSource.DIRECT_CRAWL,
                            fare_class=fare_label or None,
                            crawled_at=now,
                        )
                    )

                flights.append(
                    NormalizedFlight(
                        flight_number=flight_number,
                        airline_code=airline_code,
                        airline_name=airline_name,
                        operator=operator,
                        origin=seg_origin,
                        destination=seg_destination,
                        departure_time=departure_dt,
                        arrival_time=arrival_dt,
                        duration_minutes=duration_minutes,
                        cabin_class=resolved_cabin,
                        aircraft_type=aircraft_type,
                        stops=stops,
                        prices=prices,
                        source=DataSource.DIRECT_CRAWL,
                        crawled_at=now,
                    )
                )

    logger.info(
        "Parsed %d flights for %s->%s from Singapore Airlines",
        len(flights),
        origin,
        destination,
    )
    return flights
