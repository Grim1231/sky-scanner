"""Cathay Pacific website API client (L2 direct crawl).

Endpoints (reverse-engineered from cathaypacific.com SPA):

``GET api.cathaypacific.com/flightinformation/flightschedule/v2/flightTimetable``
    Flight timetable / schedule for a route and date range.
    Query params (discovered from minified React bundle):
        carrierCode (CX), lang (en_HK), countryCode (HK),
        sortBy (2), tripType (R|O), origin, destination,
        departAt (YYYY-MM-DD), returnOn (YYYY-MM-DD, optional),
        multiOrigin (false), multiDestination (false).
    NOTE: This endpoint currently returns HTTP 406 for all routes
    due to a server-side response-body validation bug (null fields
    where strings are expected).  We keep the implementation for
    future use but the crawler falls through to the histogram.

``GET api.cathaypacific.com/ibe-od/v2.0/{lang}``
    Full list of airports / destinations served by CX.
    No authentication required; JSON dict with "airports" array.

``GET api.cathaypacific.com/ibe-od/v2.0/{lang}/{origin}``
    Destinations reachable from a specific origin airport.

``GET book.cathaypacific.com/CathayPacificV3/dyn/air/api/instant/histogram``
    Fare calendar: cheapest return fares per month for a route.
    Query params (uppercase): ORIGIN, DESTINATION, SITE (CBEUCBEU),
    TYPE (MTH), LANGUAGE (GB), CABIN (optional: Y/W/J/F).
    Returns a JSON array of fare records.  No Akamai warm-up needed.

``GET book.cathaypacific.com/CathayPacificV3/dyn/air/api/instant/open-search``
    Best fares from an origin to all destinations.
    Query params: ORIGIN, LANGUAGE (GB), SITE (CBEUCBEU),
    CABIN (optional).

The ``api.cathaypacific.com`` domain is behind Akamai Bot Manager and
requires a valid session for the timetable endpoint.  However, the
``book.cathaypacific.com`` histogram/open-search endpoints work without
any warm-up using ``primp`` Chrome TLS impersonation alone.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import primp

from sky_scanner_crawler.retry import async_retry

if TYPE_CHECKING:
    from datetime import date

logger = logging.getLogger(__name__)

_MAIN_URL = "https://www.cathaypacific.com"
_API_URL = "https://api.cathaypacific.com"
_BOOK_URL = "https://book.cathaypacific.com"

# Cabin class mapping: our enum value -> CX cabin code.
_CABIN_MAP: dict[str, str] = {
    "ECONOMY": "Y",
    "PREMIUM_ECONOMY": "W",
    "BUSINESS": "J",
    "FIRST": "F",
}

# Standard headers to mimic the SPA.
_COMMON_HEADERS: dict[str, str] = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{_MAIN_URL}/cx/en_US/book-a-trip/timetable.html",
}

# Booking-site SITE code (from AEM config: CBEUCBEU).
_BOOK_SITE = "CBEUCBEU"


class CathayPacificClient:
    """Async HTTP client for Cathay Pacific website APIs.

    Uses ``primp`` (Rust HTTP client) with Chrome TLS impersonation.
    The histogram and open-search endpoints on ``book.cathaypacific.com``
    do not require any Akamai warm-up, so we call them directly.
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new_client(self) -> primp.Client:
        """Create a fresh primp client with Chrome TLS impersonation."""
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    def _warm_up(self, client: primp.Client) -> None:
        """Visit the main website to acquire Akamai session cookies.

        Required only for the ``api.cathaypacific.com`` timetable endpoint.
        The ``book.cathaypacific.com`` endpoints do not need this.
        """
        resp = client.get(f"{_MAIN_URL}/cx/en_US.html")
        logger.debug("Warmup homepage: %d", resp.status_code)

        resp = client.get(f"{_MAIN_URL}/cx/en_US/book-a-trip/timetable.html")
        logger.debug("Warmup timetable: %d", resp.status_code)

    def _get_timetable(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: date | None = None,
        *,
        cabin: str = "Y",
    ) -> dict[str, Any]:
        """Synchronous GET request to the flight timetable API.

        Uses the exact query-parameter names discovered from the SPA's
        minified React/Redux code (module 1579).

        .. warning::
           As of 2026-02, this endpoint returns HTTP 406 for all routes
           due to an upstream response-body schema validation failure.
           The caller should handle this gracefully and fall through to
           the histogram endpoint.
        """
        client = self._new_client()
        self._warm_up(client)

        params: dict[str, str] = {
            "carrierCode": "CX",
            "lang": "en_HK",
            "countryCode": "HK",
            "sortBy": "2",
            "tripType": "R" if return_date else "O",
            "origin": origin,
            "destination": destination,
            "departAt": departure_date.isoformat(),
            "multiOrigin": "false",
            "multiDestination": "false",
        }
        if return_date:
            params["returnOn"] = return_date.isoformat()

        url = f"{_API_URL}/flightinformation/flightschedule/v2/flightTimetable"
        resp = client.get(url, params=params, headers=_COMMON_HEADERS)

        if resp.status_code != 200:
            msg = f"CX timetable API: HTTP {resp.status_code} (body: {resp.text[:200]})"
            raise RuntimeError(msg)

        result: dict[str, Any] = resp.json()
        return result

    def _get_destinations(self, lang: str = "en_US") -> dict[str, Any]:
        """Fetch the full airport / destination list."""
        client = self._new_client()
        url = f"{_API_URL}/ibe-od/v2.0/{lang}"
        resp = client.get(url, headers=_COMMON_HEADERS)

        if resp.status_code != 200:
            msg = f"CX ibe-od API: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: dict[str, Any] = resp.json()
        return data

    def _get_destinations_from(
        self, origin: str, lang: str = "en_US"
    ) -> dict[str, Any]:
        """Fetch destinations reachable from *origin*."""
        client = self._new_client()
        url = f"{_API_URL}/ibe-od/v2.0/{lang}/{origin}"
        resp = client.get(url, headers=_COMMON_HEADERS)

        if resp.status_code != 200:
            msg = f"CX ibe-od/{origin} API: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: dict[str, Any] = resp.json()
        return data

    def _get_histogram(
        self,
        origin: str,
        destination: str,
        *,
        cabin: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET the instant histogram (fare calendar) endpoint.

        This endpoint is a simple GET on ``book.cathaypacific.com`` and
        does **not** require Akamai warm-up.  It returns a JSON array
        of fare records with ``date_departure``, ``total_fare``,
        ``currency``, ``outbound_cabin``, etc.

        For multi-airport cities, use the **airport** code directly
        (e.g. ``ICN`` not ``SEL``).  Some airports only work via their
        city virtual code (e.g. ``LON`` for Heathrow/Gatwick).
        """
        client = self._new_client()

        params: dict[str, str] = {
            "ORIGIN": origin,
            "DESTINATION": destination,
            "SITE": _BOOK_SITE,
            "TYPE": "MTH",
            "LANGUAGE": "GB",
        }
        if cabin:
            params["CABIN"] = cabin

        url = f"{_BOOK_URL}/CathayPacificV3/dyn/air/api/instant/histogram"
        resp = client.get(url, params=params, headers=_COMMON_HEADERS)

        if resp.status_code != 200:
            msg = f"CX histogram API: HTTP {resp.status_code} (body: {resp.text[:200]})"
            raise RuntimeError(msg)

        result: list[dict[str, Any]] = resp.json()
        return result

    def _get_open_search(
        self,
        origin: str,
        *,
        cabin: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET the instant open-search (best fares) endpoint.

        Returns cheapest return fares from *origin* to all CX
        destinations.  No Akamai warm-up required.
        """
        client = self._new_client()

        params: dict[str, str] = {
            "ORIGIN": origin,
            "LANGUAGE": "GB",
            "SITE": _BOOK_SITE,
        }
        if cabin:
            params["CABIN"] = cabin

        url = f"{_BOOK_URL}/CathayPacificV3/dyn/air/api/instant/open-search"
        resp = client.get(url, params=params, headers=_COMMON_HEADERS)

        if resp.status_code != 200:
            msg = (
                f"CX open-search API: HTTP {resp.status_code} (body: {resp.text[:200]})"
            )
            raise RuntimeError(msg)

        result: list[dict[str, Any]] = resp.json()
        return result

    # ------------------------------------------------------------------
    # Public async methods
    # ------------------------------------------------------------------

    @async_retry(
        max_retries=0,
        base_delay=2.0,
        max_delay=15.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_timetable(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: date | None = None,
        *,
        cabin_class: str = "ECONOMY",
    ) -> dict[str, Any]:
        """Fetch the flight timetable for a route and departure date.

        Returns the raw JSON response from the timetable API.

        .. note::
           Currently broken server-side (HTTP 406).  The crawler falls
           through to ``search_histogram`` when this raises.
        """
        cabin = _CABIN_MAP.get(cabin_class, "Y")
        result = await asyncio.to_thread(
            self._get_timetable,
            origin,
            destination,
            departure_date,
            return_date,
            cabin=cabin,
        )
        logger.info(
            "CX timetable %s->%s (%s): fetched",
            origin,
            destination,
            departure_date,
        )
        return result

    @async_retry(
        max_retries=1,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_histogram(
        self,
        origin: str,
        destination: str,
        *,
        cabin_class: str = "ECONOMY",
    ) -> list[dict[str, Any]]:
        """Fetch the fare histogram (calendar) for a route.

        Returns the raw JSON array from the histogram endpoint.
        Each element contains ``date_departure``, ``date_return``,
        ``total_fare``, ``currency``, ``outbound_cabin``, etc.
        """
        cabin = _CABIN_MAP.get(cabin_class, "Y")
        result = await asyncio.to_thread(
            self._get_histogram,
            origin,
            destination,
            cabin=cabin,
        )
        logger.info(
            "CX histogram %s->%s: %d fare records",
            origin,
            destination,
            len(result),
        )
        return result

    @async_retry(
        max_retries=1,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_open(
        self,
        origin: str,
        *,
        cabin_class: str = "ECONOMY",
    ) -> list[dict[str, Any]]:
        """Fetch the cheapest fares from *origin* to all destinations.

        Returns the raw JSON array from the open-search endpoint.
        Each element contains ``origin``, ``destination``,
        ``date_departure``, ``date_return``, ``total_fare``, etc.
        """
        cabin = _CABIN_MAP.get(cabin_class, "Y")
        result = await asyncio.to_thread(
            self._get_open_search,
            origin,
            cabin=cabin,
        )
        logger.info(
            "CX open-search from %s: %d destination fares",
            origin,
            len(result),
        )
        return result

    async def get_destinations(
        self,
        lang: str = "en_US",
    ) -> dict[str, Any]:
        """Fetch all served airports/destinations.

        Returns a dict with an ``airports`` key containing a list of
        airport objects including ``airportCode``, ``airportDetails``,
        ``isVirtualAirport``, ``belongToVirtualPortCode``, etc.
        """
        return await asyncio.to_thread(self._get_destinations, lang)

    async def get_destinations_from(
        self,
        origin: str,
        lang: str = "en_US",
    ) -> dict[str, Any]:
        """Fetch destinations reachable from *origin*.

        Useful for resolving city codes (e.g. NRT -> TYO) before
        calling the histogram API.
        """
        return await asyncio.to_thread(self._get_destinations_from, origin, lang)

    async def health_check(self) -> bool:
        """Check if the Cathay Pacific API is reachable.

        Uses the IBE origin-destination endpoint which has lower
        protection than the timetable/search endpoints.
        """
        try:
            destinations = await self.get_destinations()
            airports = destinations.get("airports", [])
            return len(airports) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
