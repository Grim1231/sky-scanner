"""Parse Air Seoul searchFlightInfo response into NormalizedFlight objects."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sky_scanner_core.schemas import (
    CabinClass,
    DataSource,
    NormalizedFlight,
    NormalizedPrice,
)

logger = logging.getLogger(__name__)

_AIR_SEOUL_CODE = "RS"
_AIR_SEOUL_NAME = "Air Seoul"

# KST offset for parsing Air Seoul local times
_KST_OFFSET = timedelta(hours=9)


def _parse_datetime(date_str: str, time_str: str) -> datetime:
    """Parse Air Seoul date+time strings into UTC datetime.

    Air Seoul returns dates as ``YYYYMMDD`` and times as ``HHMMSS``
    in Korea Standard Time (KST, UTC+9).
    """
    year = int(date_str[:4])
    month = int(date_str[4:6])
    day = int(date_str[6:8])
    hour = int(time_str[:2])
    minute = int(time_str[2:4])
    local_dt = datetime(year, month, day, hour, minute, tzinfo=UTC) - _KST_OFFSET
    return local_dt.replace(tzinfo=UTC)


def _parse_flying_time(flying_time: str) -> int:
    """Parse Air Seoul flying time ``HHMM`` into minutes."""
    if not flying_time or len(flying_time) < 4:
        return 0
    hours = int(flying_time[:2])
    minutes = int(flying_time[2:4])
    return hours * 60 + minutes


def _aircraft_from_type(flight_type: str) -> str | None:
    """Map Air Seoul flight type code to aircraft name."""
    mapping = {
        "321": "A321",
        "32Q": "A321neo",
        "320": "A320",
        "738": "B737-800",
        "739": "B737-900",
    }
    return mapping.get(flight_type)


def parse_flight_info(
    raw: dict,
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Air Seoul searchFlightInfo response into NormalizedFlight list.

    Unlike calendar-only APIs (Jeju Air, Eastar Jet), Air Seoul's
    ``searchFlightInfo.do`` returns **individual flights** with:

    - Actual departure/arrival times
    - Flight numbers (e.g. RS705)
    - Aircraft type (e.g. A321)
    - Three fare tiers: PROMOTIONAL, DISCOUNT, NORMAL
    - Seat availability per fare class
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    shop_data = raw.get("fareShopData", {})
    if not shop_data:
        return flights

    currency = shop_data.get("USE_CURRENCY", "KRW")
    flight_shops: list[dict] = shop_data.get("flightShopDatas", [])

    for fs in flight_shops:
        if not fs.get("availFlight"):
            continue

        flight_infos: list[dict] = fs.get("flightInfoDatas", [])
        if not flight_infos:
            continue

        # Use the first segment (Air Seoul operates direct flights)
        seg = flight_infos[0]

        flight_no = seg.get("flightNO", "")
        airline_code = seg.get("marketingAirlineCode", _AIR_SEOUL_CODE)
        dep_airport = seg.get("departureAirportCode", origin)
        arr_airport = seg.get("arrivalAirportCode", destination)
        dep_date = seg.get("departureDate", "")
        dep_time = seg.get("departureTime", "000000")
        arr_date = seg.get("arrivalDate", dep_date)
        arr_time = seg.get("arrivalTime", "000000")
        flying_time = seg.get("flyingTime", "")
        flight_type = seg.get("flightType", "")

        if not dep_date or not flight_no:
            continue

        try:
            departure_dt = _parse_datetime(dep_date, dep_time)
            arrival_dt = _parse_datetime(arr_date, arr_time)
        except (ValueError, IndexError):
            logger.warning("Invalid date/time for flight RS%s", flight_no)
            continue

        duration = _parse_flying_time(flying_time)
        aircraft = _aircraft_from_type(flight_type)

        # Build prices from all available fare tiers
        prices: list[NormalizedPrice] = []

        fare_tiers = [
            (
                "promotional",
                "promotionalTotalFare",
                "promotionalEquivFareBasis",
                "promotionalSeatCount",
            ),
            (
                "discount",
                "discountTotalFare",
                "discountEquivFareBasis",
                "discountSeatCount",
            ),
            ("normal", "normalTotalFare", "normalEquivFareBasis", "normalSeatCount"),
        ]

        for tier_name, total_key, basis_key, seat_key in fare_tiers:
            total_str = fs.get(total_key, "0")
            try:
                total = float(total_str)
            except (ValueError, TypeError):
                continue
            if total <= 0:
                continue

            seat_count = int(fs.get(seat_key, "0") or "0")
            if seat_count <= 0 and tier_name == "promotional":
                # Promotional fare sold out — skip
                continue

            prices.append(
                NormalizedPrice(
                    amount=total,
                    currency=currency,
                    source=DataSource.DIRECT_CRAWL,
                    fare_class=fs.get(basis_key, tier_name),
                    crawled_at=now,
                )
            )

        if not prices:
            continue

        flights.append(
            NormalizedFlight(
                flight_number=f"{_AIR_SEOUL_CODE}{flight_no}",
                airline_code=airline_code,
                airline_name=_AIR_SEOUL_NAME,
                operator=seg.get("operationAirlineCode", _AIR_SEOUL_CODE),
                origin=dep_airport,
                destination=arr_airport,
                departure_time=departure_dt,
                arrival_time=arrival_dt,
                duration_minutes=duration,
                cabin_class=cabin_class,
                aircraft_type=aircraft,
                stops=0,
                prices=prices,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            )
        )

    logger.info(
        "Parsed %d flights for %s→%s from Air Seoul",
        len(flights),
        origin,
        destination,
    )
    return flights
