"""Async HTTP client for Vietnam Airlines middleware API.

Vietnam Airlines exposes a public middleware API at
``integration-middleware-website.vietnamairlines.com/api/v1``
that provides flight schedules and fare calendar data.

Three endpoints are used (no authentication required):

1. ``GET /public/flight/schedule-table`` -- flight schedule with times,
   aircraft type, operating days, and validity periods.
2. ``POST /public/booking/air-best-price`` -- lowest fare calendar
   per departure date for a route (one-way or round-trip).
3. ``GET /public/flight/info`` -- detailed flight status with
   booking classes, terminals, and real-time status.

The API sits behind a standard Java/Spring backend; TLS fingerprint
checking is **not** enforced (unlike ``booking.vietnamairlines.com``
which runs Imperva WAF).  We use ``primp`` with Chrome impersonation
as a precaution.

Currency/pricing is controlled by the ``location`` parameter which
should match the origin country code (e.g. ``VN`` for Vietnam
departures, ``KR`` for Korea departures).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import primp

from sky_scanner_crawler.retry import async_retry

if TYPE_CHECKING:
    from datetime import date

logger = logging.getLogger(__name__)

_BASE_URL = "https://integration-middleware-website.vietnamairlines.com/api/v1"

# Country code to API location code mapping.
# The ``location`` parameter in air-best-price determines pricing currency.
# It must match the departure country for fares to be returned.
_AIRPORT_COUNTRY: dict[str, str] = {
    "SGN": "VN",
    "HAN": "VN",
    "DAD": "VN",
    "CXR": "VN",
    "PQC": "VN",
    "HPH": "VN",
    "HUI": "VN",
    "DLI": "VN",
    "ICN": "KR",
    "GMP": "KR",
    "NRT": "JP",
    "HND": "JP",
    "KIX": "JP",
    "NGO": "JP",
    "FUK": "JP",
    "SIN": "SG",
    "BKK": "TH",
    "PNH": "KH",
    "VTE": "LA",
    "RGN": "MM",
    "KUL": "MY",
    "PEK": "CN",
    "PVG": "CN",
    "CAN": "CN",
    "TPE": "TW",
    "CDG": "FR",
    "LHR": "GB",
    "FRA": "DE",
    "SYD": "AU",
    "MEL": "AU",
    "SFO": "US",
}


def _location_for_airport(airport_code: str) -> str:
    """Resolve airport IATA code to VN API location parameter.

    Falls back to ``"VN"`` for unknown airports (VN is the most
    common departure country for Vietnam Airlines routes).
    """
    return _AIRPORT_COUNTRY.get(airport_code.upper(), "VN")


class VietnamAirlinesClient:
    """Async client for the Vietnam Airlines middleware API.

    Uses ``primp`` (Rust HTTP client with TLS impersonation) wrapped
    in ``asyncio.to_thread`` for async compatibility.  Each call
    creates a fresh client -- the middleware does not require session
    cookies or warm-up.
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    def _new_client(self) -> primp.Client:
        """Create a fresh primp client with Chrome TLS fingerprint."""
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
            verify=False,  # Middleware uses a cert chain that may not validate locally
        )

    # ------------------------------------------------------------------
    # Flight schedule
    # ------------------------------------------------------------------

    def _get_schedule_sync(
        self,
        origin: str,
        destination: str,
        departure_date: date,
    ) -> dict[str, Any]:
        """Synchronous GET to ``/public/flight/schedule-table``."""
        client = self._new_client()
        params = (
            f"originLocationCode={origin.upper()}"
            f"&destinationLocationCode={destination.upper()}"
            f"&departureDate={departure_date.isoformat()}"
        )
        resp = client.get(f"{_BASE_URL}/public/flight/schedule-table?{params}")
        if resp.status_code != 200:
            msg = f"VN schedule-table: HTTP {resp.status_code}"
            raise RuntimeError(msg)
        data: dict[str, Any] = resp.json()
        if not data.get("success", False):
            msg = f"VN schedule-table: {data.get('message', 'unknown error')}"
            raise RuntimeError(msg)
        return data

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def get_flight_schedule(
        self,
        origin: str,
        destination: str,
        departure_date: date,
    ) -> dict[str, Any]:
        """Fetch flight schedule for a route and date.

        Parameters
        ----------
        origin:
            3-letter IATA airport code (e.g. ``SGN``, ``ICN``).
        destination:
            3-letter IATA airport code (e.g. ``ICN``, ``HAN``).
        departure_date:
            Departure date (the API returns flights within ~7 days
            around this date).

        Returns
        -------
        dict
            Raw API response with ``data.departureFlight.scheduleItems``
            containing per-flight schedule entries with connected flights,
            operating days, and validity periods.
        """
        data = await asyncio.to_thread(
            self._get_schedule_sync,
            origin,
            destination,
            departure_date,
        )
        items = data.get("data", {}).get("departureFlight", {}).get("scheduleItems", [])
        logger.debug(
            "VN schedule %s->%s (%s): %d items",
            origin,
            destination,
            departure_date.isoformat(),
            len(items),
        )
        return data

    # ------------------------------------------------------------------
    # Fare calendar (best price per day)
    # ------------------------------------------------------------------

    def _post_best_price_sync(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        range_of_departure: int = 62,
        trip_duration: int | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """Synchronous POST to ``/public/booking/air-best-price``."""
        client = self._new_client()
        loc = location or _location_for_airport(origin)

        payload: dict[str, Any] = {
            "route": {
                "originLocationCode": origin.upper(),
                "destinationLocationCode": destination.upper(),
                "departureDateTime": departure_date.isoformat(),
            },
            "tripDetails": {
                "rangeOfDeparture": range_of_departure,
            },
            "location": loc.upper(),
        }
        if trip_duration is not None:
            payload["tripDetails"]["tripDuration"] = trip_duration

        resp = client.post(
            f"{_BASE_URL}/public/booking/air-best-price",
            content=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code != 200:
            msg = f"VN air-best-price: HTTP {resp.status_code}: {resp.text[:300]}"
            raise RuntimeError(msg)
        data: dict[str, Any] = resp.json()
        if not data.get("success", False):
            msg = f"VN air-best-price: {data.get('message', 'unknown error')}"
            raise RuntimeError(msg)
        return data

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def get_best_prices(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        range_of_departure: int = 62,
        trip_duration: int | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """Fetch fare calendar (lowest price per departure date).

        Parameters
        ----------
        origin:
            3-letter IATA airport code.
        destination:
            3-letter IATA airport code.
        departure_date:
            Start of the fare range (fares are returned for
            ``rangeOfDeparture`` days from this date).
        range_of_departure:
            Number of days to scan ahead (default 62).
        trip_duration:
            For round-trip fares: stay duration in days minus 1.
            Omit or ``None`` for one-way fares.
        location:
            Country code for pricing (e.g. ``VN``, ``KR``).
            Auto-detected from origin airport if not specified.

        Returns
        -------
        dict
            Raw API response with ``data.prices`` containing per-date
            fare entries with ``base``, ``total``, ``totalTaxes``,
            and ``currencyCode``.  ``data.dictionaries.currency``
            provides decimal-place info.
        """
        data = await asyncio.to_thread(
            self._post_best_price_sync,
            origin,
            destination,
            departure_date,
            range_of_departure=range_of_departure,
            trip_duration=trip_duration,
            location=location,
        )
        prices = data.get("data", {}).get("prices", [])
        logger.debug(
            "VN best-price %s->%s (%s, %dd): %d price entries",
            origin,
            destination,
            departure_date.isoformat(),
            range_of_departure,
            len(prices),
        )
        return data

    # ------------------------------------------------------------------
    # Flight info (detailed status for a specific flight)
    # ------------------------------------------------------------------

    def _get_flight_info_sync(
        self,
        airline_code: str,
        flight_number: str,
        departure_date: date,
    ) -> dict[str, Any]:
        """Synchronous GET to ``/public/flight/info``."""
        client = self._new_client()
        # The API expects numeric flight number (e.g. "402" not "VN402")
        num = flight_number.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        params = (
            f"marketingAirlineCode={airline_code.upper()}"
            f"&marketingFlightNumber={num}"
            f"&departureDate={departure_date.isoformat()}"
        )
        resp = client.get(f"{_BASE_URL}/public/flight/info?{params}")
        if resp.status_code != 200:
            msg = f"VN flight/info: HTTP {resp.status_code}"
            raise RuntimeError(msg)
        data: dict[str, Any] = resp.json()
        if not data.get("success", False):
            msg = f"VN flight/info: {data.get('message', 'unknown error')}"
            raise RuntimeError(msg)
        return data

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def get_flight_info(
        self,
        airline_code: str,
        flight_number: str,
        departure_date: date,
    ) -> dict[str, Any]:
        """Fetch detailed info for a specific flight.

        Parameters
        ----------
        airline_code:
            IATA airline code (e.g. ``VN``).
        flight_number:
            Flight number (e.g. ``402`` or ``VN402``).
        departure_date:
            Date of the flight.

        Returns
        -------
        dict
            Raw API response with ``data.flightDetails`` containing
            departure/arrival info, booking classes, aircraft code,
            duration, and real-time flight status.
        """
        return await asyncio.to_thread(
            self._get_flight_info_sync,
            airline_code,
            flight_number,
            departure_date,
        )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Check if the Vietnam Airlines middleware API is reachable.

        Performs a minimal call to the country-codes endpoint.
        """
        try:

            def _check() -> bool:
                client = self._new_client()
                resp = client.get(f"{_BASE_URL}/public/country-codes")
                return resp.status_code == 200

            return await asyncio.to_thread(_check)
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
