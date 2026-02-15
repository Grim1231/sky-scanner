"""Parse Air Busan flightsAvail response into NormalizedFlight objects."""

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

_BUSAN_CODE = "BX"
_BUSAN_NAME = "Air Busan"

# KST offset for parsing Air Busan local times
_KST_OFFSET = timedelta(hours=9)


def _parse_datetime(date_str: str, time_str: str) -> datetime:
    """Parse date (YYYYMMDD) + time (HHMM) in KST to UTC datetime."""
    year = int(date_str[:4])
    month = int(date_str[4:6])
    day = int(date_str[6:8])
    hour = int(time_str[:2])
    minute = int(time_str[2:4])
    local_dt = datetime(year, month, day, hour, minute, tzinfo=UTC) - _KST_OFFSET
    return local_dt.replace(tzinfo=UTC)


def parse_flights_avail(
    raw: dict,
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert Air Busan flightsAvail response into NormalizedFlight list.

    Response contains ``listItineraryFare`` with nested flights.
    Each flight has ``listCls`` with fare classes (S, L, A, E),
    each with per-passenger pricing and seat availability.

    Tax/fuel surcharge is in ``pubTaxFuel`` at the top level.
    Total fare = ``priceAd`` + ``taxAd`` + ``fuelAd``.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    itineraries: list[dict] = raw.get("listItineraryFare", [])
    if not itineraries:
        return flights

    # Tax breakdown (applies per-passenger to all flights in response)
    pub_tax_fuel: dict = raw.get("pubTaxFuel", {})
    tax_ad = float(pub_tax_fuel.get("taxAd", 0) or 0)
    fuel_ad = float(pub_tax_fuel.get("fuelAd", 0) or 0)

    for itin in itineraries:
        itin_dep_date = itin.get("depDate", "")

        for flt in itin.get("listFlight", []):
            flight_no = flt.get("flightNo", "")
            dep_time = flt.get("depTime", "0000")
            arr_time = flt.get("arrTime", "0000")
            dep_date = flt.get("depDate", itin_dep_date)
            arr_date = flt.get("arrDate", dep_date)
            flying_min = int(flt.get("flyingMinute", 0) or 0)
            dep_city = flt.get("depCity", origin)
            arr_city = flt.get("arrCity", destination)

            if not flight_no or not dep_date:
                continue

            try:
                departure_dt = _parse_datetime(dep_date, dep_time)
                arrival_dt = _parse_datetime(arr_date, arr_time)
            except (ValueError, IndexError):
                logger.warning(
                    "Invalid date/time for Air Busan %s",
                    flight_no,
                )
                continue

            # Build prices from all fare classes
            prices: list[NormalizedPrice] = []
            fare_classes: list[dict] = flt.get("listCls", [])

            for cls in fare_classes:
                try:
                    price_ad = float(cls.get("priceAd", 0) or 0)
                except (ValueError, TypeError):
                    continue

                if price_ad <= 0:
                    continue

                avail = int(cls.get("avail", 0) or 0)
                if avail <= 0:
                    continue

                cls_code = cls.get("cls", "")
                sub_cls = cls.get("subCls", "")
                currency = cls.get("currency", "KRW")

                # Total = base fare + tax + fuel
                total = price_ad + tax_ad + fuel_ad

                prices.append(
                    NormalizedPrice(
                        amount=total,
                        currency=currency,
                        source=DataSource.DIRECT_CRAWL,
                        fare_class=f"{cls_code}/{sub_cls}" if sub_cls else cls_code,
                        crawled_at=now,
                    )
                )

            if not prices:
                continue

            flights.append(
                NormalizedFlight(
                    flight_number=flight_no,
                    airline_code=_BUSAN_CODE,
                    airline_name=_BUSAN_NAME,
                    operator=_BUSAN_CODE,
                    origin=dep_city,
                    destination=arr_city,
                    departure_time=departure_dt,
                    arrival_time=arrival_dt,
                    duration_minutes=flying_min,
                    cabin_class=cabin_class,
                    stops=0,
                    prices=prices,
                    source=DataSource.DIRECT_CRAWL,
                    crawled_at=now,
                )
            )

    logger.info(
        "Parsed %d flights for %s->%s from Air Busan",
        len(flights),
        origin,
        destination,
    )
    return flights
