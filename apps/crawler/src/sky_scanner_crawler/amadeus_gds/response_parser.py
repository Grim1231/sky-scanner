"""Parse Amadeus flight-offers response into NormalizedFlight objects."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sky_scanner_core.schemas import (
    CabinClass,
    DataSource,
    NormalizedFlight,
    NormalizedPrice,
)

logger = logging.getLogger(__name__)

_CABIN_MAP: dict[str, CabinClass] = {
    "ECONOMY": CabinClass.ECONOMY,
    "PREMIUM_ECONOMY": CabinClass.PREMIUM_ECONOMY,
    "BUSINESS": CabinClass.BUSINESS,
    "FIRST": CabinClass.FIRST,
}

# ISO-8601 duration → minutes (e.g. "PT2H30M" → 150)
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")


def _parse_duration(iso_dur: str) -> int:
    """Convert ISO-8601 duration string to minutes."""
    m = _DURATION_RE.match(iso_dur)
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return hours * 60 + minutes


def _parse_dt(dt_str: str) -> datetime:
    """Parse Amadeus datetime string to timezone-aware datetime."""
    try:
        return datetime.fromisoformat(dt_str).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return datetime.now(tz=UTC)


def parse_flight_offers(
    offers: list[dict],
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Amadeus flight-offers response data into NormalizedFlight list.

    Each offer may contain multiple itineraries (outbound/return) and each
    itinerary may have multiple segments (connections).  We create one
    ``NormalizedFlight`` per *itinerary* in each offer (first itinerary only
    for simplicity, since our model is one-way).

    Parameters
    ----------
    offers:
        The ``data`` array from a Flight Offers Search response.
    cabin_class:
        Requested cabin class (for filtering traveler pricings).
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    for offer in offers:
        itineraries = offer.get("itineraries", [])
        if not itineraries:
            continue

        # Take only the first itinerary (outbound)
        itin = itineraries[0]
        segments = itin.get("segments", [])
        if not segments:
            continue

        # First and last segment determine route endpoints
        first_seg = segments[0]
        last_seg = segments[-1]

        origin = first_seg.get("departure", {}).get("iataCode", "")
        destination = last_seg.get("arrival", {}).get("iataCode", "")
        dep_time = _parse_dt(first_seg.get("departure", {}).get("at", ""))
        arr_time = _parse_dt(last_seg.get("arrival", {}).get("at", ""))

        # Duration from itinerary level
        duration_mins = _parse_duration(itin.get("duration", ""))

        # Flight number from first segment
        carrier_code = first_seg.get("carrierCode", "")
        flight_num = first_seg.get("number", "")
        flight_number = f"{carrier_code}{flight_num}"

        # Operating carrier (if different from marketing carrier)
        operating = first_seg.get("operating", {})
        operator_code = operating.get("carrierCode", carrier_code)

        # Aircraft type
        aircraft_code = first_seg.get("aircraft", {}).get("code")

        # Number of stops = number of segments - 1
        stops = len(segments) - 1

        # Price
        price_data = offer.get("price", {})
        total = price_data.get("grandTotal") or price_data.get("total")
        currency = price_data.get("currency", "KRW")

        if not total:
            continue

        # Determine cabin and fare class from traveler pricings
        fare_class_str = ""
        offer_cabin = cabin_class
        traveler_pricings = offer.get("travelerPricings", [])
        if traveler_pricings:
            fare_details = traveler_pricings[0].get("fareDetailsBySegment", [])
            if fare_details:
                cabin_str = fare_details[0].get("cabin", "")
                offer_cabin = _CABIN_MAP.get(cabin_str, cabin_class)
                fare_class_str = fare_details[0].get("class", "")

        # Check included baggage
        includes_baggage = False
        if traveler_pricings:
            fare_details = traveler_pricings[0].get("fareDetailsBySegment", [])
            if fare_details:
                bag_info = fare_details[0].get("includedCheckedBags", {})
                if bag_info.get("quantity", 0) > 0 or bag_info.get("weight"):
                    includes_baggage = True

        price_obj = NormalizedPrice(
            amount=float(total),
            currency=currency,
            source=DataSource.GDS,
            fare_class=fare_class_str or None,
            includes_baggage=includes_baggage,
            crawled_at=now,
        )

        flights.append(
            NormalizedFlight(
                flight_number=flight_number,
                airline_code=carrier_code,
                operator=operator_code,
                origin=origin,
                destination=destination,
                departure_time=dep_time,
                arrival_time=arr_time,
                duration_minutes=duration_mins,
                cabin_class=offer_cabin,
                aircraft_type=aircraft_code,
                stops=stops,
                prices=[price_obj],
                source=DataSource.GDS,
                crawled_at=now,
            ),
        )

    logger.info(
        "Parsed %d flight offers from Amadeus GDS",
        len(flights),
    )
    return flights
