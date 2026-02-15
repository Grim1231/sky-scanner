"""Parse Malaysia Airlines low-fare calendar responses into NormalizedFlight objects.

The low-fare calendar API returns daily lowest prices in two modes:

**One-way** (``firstdate`` param)::

    [
        {
            "refNo": "1",
            "dateOfDeparture": "150226",  # DDMMYY
            "totalFareAmount": "249.00",
            "totalTaxAmount": "112.00",
            "currency": "MYR",
            "isLowFare": false,
        },
        ...,
    ]

**Return** (``departdate`` + ``fromDepartDate=true``)::

    [
        {
            "dateOfDeparture": "150326",
            "totalFareAmount": "3390.00",
            "totalTaxAmount": "387.00",
            "currency": "MYR",
            "returnDetail": [
                {
                    "dateOfDeparture": "150326",
                    "totalFareAmount": "2325.00",
                    "totalTaxAmount": "369.00",
                    "currency": "MYR",
                },
                ...,
            ],
        }
    ]

Date format is ``DDMMYY`` -- day first, then month, then two-digit year.
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

_MH_CODE = "MH"
_MH_NAME = "Malaysia Airlines"


def _parse_ddmmyy(date_str: str) -> datetime | None:
    """Convert a ``DDMMYY`` string to a UTC datetime, or ``None`` on failure."""
    if not date_str or len(date_str) != 6:
        return None
    try:
        return datetime.strptime(date_str, "%d%m%y").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        logger.warning("Invalid DDMMYY date: %s", date_str)
        return None


def parse_oneway_fares(
    raw: list[dict[str, Any]],
    *,
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert one-way low-fare entries into NormalizedFlight list.

    Parameters
    ----------
    raw:
        Raw JSON entries from the one-way low-fare API.
    origin:
        IATA departure code.
    destination:
        IATA arrival code.
    cabin_class:
        Cabin class to assign (the low-fare API returns lowest economy by
        default).

    Returns
    -------
    list[NormalizedFlight]
        One ``NormalizedFlight`` per fare entry with ``totalFareAmount > 0``.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    for entry in raw:
        fare_str = entry.get("totalFareAmount", "0")
        try:
            fare_amount = float(fare_str)
        except (ValueError, TypeError):
            continue
        if fare_amount <= 0:
            continue

        tax_str = entry.get("totalTaxAmount", "0")
        try:
            tax_amount = float(tax_str)
        except (ValueError, TypeError):
            tax_amount = 0.0

        currency = entry.get("currency", "MYR")
        date_str = entry.get("dateOfDeparture", "")
        dep_dt = _parse_ddmmyy(date_str)
        if dep_dt is None:
            continue

        total = fare_amount + tax_amount

        fare_label = "economy-lowest"
        if entry.get("isLowFare"):
            fare_label = "economy-promo"

        price_obj = NormalizedPrice(
            amount=total,
            currency=currency,
            source=DataSource.DIRECT_CRAWL,
            fare_class=fare_label,
            crawled_at=now,
        )

        flights.append(
            NormalizedFlight(
                flight_number=f"{_MH_CODE}-{origin}{destination}",
                airline_code=_MH_CODE,
                airline_name=_MH_NAME,
                operator=_MH_CODE,
                origin=origin,
                destination=destination,
                departure_time=dep_dt,
                arrival_time=dep_dt,  # exact time unknown from this API
                duration_minutes=0,
                cabin_class=cabin_class,
                stops=0,
                prices=[price_obj],
                source=DataSource.DIRECT_CRAWL,
                crawled_at=now,
            ),
        )

    logger.info(
        "Parsed %d one-way daily fares for %s->%s from Malaysia Airlines",
        len(flights),
        origin,
        destination,
    )
    return flights


def parse_return_fares(
    raw: list[dict[str, Any]],
    *,
    origin: str,
    destination: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Convert return-trip low-fare entries into NormalizedFlight list.

    The return API returns one top-level object per departure date, with a
    nested ``returnDetail`` array.  We emit one ``NormalizedFlight`` for the
    outbound leg **and** one per return-leg date.

    Parameters
    ----------
    raw:
        Raw JSON entries from the return low-fare API.
    origin:
        IATA departure code.
    destination:
        IATA arrival code.
    cabin_class:
        Cabin class to assign.

    Returns
    -------
    list[NormalizedFlight]
        ``NormalizedFlight`` objects for outbound and return legs.
    """
    now = datetime.now(tz=UTC)
    flights: list[NormalizedFlight] = []

    for entry in raw:
        # -- Outbound leg ------------------------------------------------
        ob_fare_str = entry.get("totalFareAmount", "0")
        ob_tax_str = entry.get("totalTaxAmount", "0")
        ob_date_str = entry.get("dateOfDeparture", "")
        currency = entry.get("currency", "MYR")

        try:
            ob_fare = float(ob_fare_str)
            ob_tax = float(ob_tax_str)
        except (ValueError, TypeError):
            ob_fare, ob_tax = 0.0, 0.0

        ob_dt = _parse_ddmmyy(ob_date_str)

        if ob_dt and ob_fare > 0:
            ob_total = ob_fare + ob_tax
            ob_price = NormalizedPrice(
                amount=ob_total,
                currency=currency,
                source=DataSource.DIRECT_CRAWL,
                fare_class="economy-lowest-outbound",
                crawled_at=now,
            )
            flights.append(
                NormalizedFlight(
                    flight_number=f"{_MH_CODE}-{origin}{destination}",
                    airline_code=_MH_CODE,
                    airline_name=_MH_NAME,
                    operator=_MH_CODE,
                    origin=origin,
                    destination=destination,
                    departure_time=ob_dt,
                    arrival_time=ob_dt,
                    duration_minutes=0,
                    cabin_class=cabin_class,
                    stops=0,
                    prices=[ob_price],
                    source=DataSource.DIRECT_CRAWL,
                    crawled_at=now,
                ),
            )

        # -- Return legs -------------------------------------------------
        return_details: list[dict[str, Any]] = entry.get("returnDetail", [])
        for ret in return_details:
            ret_fare_str = ret.get("totalFareAmount", "0")
            ret_tax_str = ret.get("totalTaxAmount", "0")
            ret_date_str = ret.get("dateOfDeparture", "")
            ret_currency = ret.get("currency", currency)

            try:
                ret_fare = float(ret_fare_str)
                ret_tax = float(ret_tax_str)
            except (ValueError, TypeError):
                continue
            if ret_fare <= 0:
                continue

            ret_dt = _parse_ddmmyy(ret_date_str)
            if ret_dt is None:
                continue

            ret_total = ret_fare + ret_tax
            ret_price = NormalizedPrice(
                amount=ret_total,
                currency=ret_currency,
                source=DataSource.DIRECT_CRAWL,
                fare_class="economy-lowest-return",
                crawled_at=now,
            )
            flights.append(
                NormalizedFlight(
                    # Return leg: reversed route
                    flight_number=f"{_MH_CODE}-{destination}{origin}",
                    airline_code=_MH_CODE,
                    airline_name=_MH_NAME,
                    operator=_MH_CODE,
                    origin=destination,
                    destination=origin,
                    departure_time=ret_dt,
                    arrival_time=ret_dt,
                    duration_minutes=0,
                    cabin_class=cabin_class,
                    stops=0,
                    prices=[ret_price],
                    source=DataSource.DIRECT_CRAWL,
                    crawled_at=now,
                ),
            )

    logger.info(
        "Parsed %d return-trip daily fares for %s<->%s from Malaysia Airlines",
        len(flights),
        origin,
        destination,
    )
    return flights
