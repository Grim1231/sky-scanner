"""Cathay Pacific website API client (L2 direct crawl).

Endpoints (reverse-engineered from cathaypacific.com SPA):

``GET api.cathaypacific.com/flightinformation/flightschedule/v2/flightTimetable``
    Flight timetable / schedule for a route and date range.
    Query params: origin, destination, departureDate (YYYY-MM-DD),
    returnDate (optional), tripType (O=one-way, R=return),
    cabin (Y/W/J/F), adults (int), lang (en_US).

``GET api.cathaypacific.com/ibe-od/v2.0/{lang}``
    Full list of airports / destinations served by CX.
    No authentication required; JSON array of airport objects.

``GET api.cathaypacific.com/ibe-od/v2.0/{lang}/{origin}``
    Destinations reachable from a specific origin airport.

``POST book.cathaypacific.com/CathayPacificV3/dyn/air/api/instant/histogram``
    Fare calendar / histogram: lowest prices around a departure date.

``POST book.cathaypacific.com/CathayPacificV3/dyn/air/api/instant/open-search``
    Instant flight search with fare details.

The site uses Akamai Bot Manager.  ``api.cathaypacific.com`` endpoints
require a valid session established via the main website.  We use
``primp`` with Chrome TLS impersonation to warm up on the website first,
then call the API endpoints with the acquired cookies.

Strategy:
1. Create a fresh ``primp.Client`` with ``impersonate="chrome_131"``
2. Warm up on ``www.cathaypacific.com/cx/en_US/book-a-trip/timetable.html``
   to acquire Akamai ``_abck`` cookies and any session tokens
3. Hit the API endpoint with the same client (cookies carry over)
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


class CathayPacificClient:
    """Async HTTP client for Cathay Pacific website APIs.

    Uses ``primp`` (Rust HTTP client) with Chrome TLS impersonation
    to bypass Akamai bot protection.  Each public method creates a fresh
    session to avoid fingerprint tracking.
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

        We hit the timetable page because it configures the API endpoints
        and triggers the full Akamai challenge flow.
        """
        # Step 1: Homepage to get base cookies.
        resp = client.get(f"{_MAIN_URL}/cx/en_US.html")
        logger.debug("Warmup homepage: %d", resp.status_code)

        # Step 2: Timetable page to get API-specific session.
        resp = client.get(f"{_MAIN_URL}/cx/en_US/book-a-trip/timetable.html")
        logger.debug("Warmup timetable: %d", resp.status_code)

    def _get_timetable(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin: str = "Y",
        adults: int = 1,
    ) -> dict[str, Any]:
        """Synchronous GET request to the flight timetable API."""
        client = self._new_client()
        self._warm_up(client)

        params = {
            "origin": origin,
            "destination": destination,
            "departureDate": departure_date.isoformat(),
            "tripType": "O",
            "cabin": cabin,
            "adults": str(adults),
            "lang": "en_US",
        }

        url = f"{_API_URL}/flightinformation/flightschedule/v2/flightTimetable"
        resp = client.get(url, params=params, headers=_COMMON_HEADERS)

        if resp.status_code != 200:
            msg = f"CX timetable API: HTTP {resp.status_code} (body: {resp.text[:200]})"
            raise RuntimeError(msg)

        result: dict[str, Any] = resp.json()
        return result

    def _get_destinations(self, lang: str = "en_US") -> list[dict[str, Any]]:
        """Fetch the full airport / destination list (no warm-up needed)."""
        client = self._new_client()
        # Minimal warmup -- just homepage for Akamai cookie.
        client.get(f"{_MAIN_URL}/cx/en_US.html")

        url = f"{_API_URL}/ibe-od/v2.0/{lang}"
        resp = client.get(url, headers=_COMMON_HEADERS)

        if resp.status_code != 200:
            msg = f"CX ibe-od API: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: list[dict[str, Any]] = resp.json()
        return data

    def _get_histogram(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin: str = "Y",
        adults: int = 1,
    ) -> dict[str, Any]:
        """POST to the instant histogram (fare calendar) endpoint."""
        client = self._new_client()
        self._warm_up(client)

        # The histogram endpoint is on the booking domain.
        url = f"{_BOOK_URL}/CathayPacificV3/dyn/air/api/instant/histogram"

        payload = {
            "origin": origin,
            "destination": destination,
            "departureDate": departure_date.isoformat(),
            "cabin": cabin,
            "adults": adults,
            "children": 0,
            "infants": 0,
            "tripType": "O",
            "language": "en",
            "country": "US",
        }

        headers = {
            **_COMMON_HEADERS,
            "Content-Type": "application/json",
            "Origin": _MAIN_URL,
            "Referer": f"{_MAIN_URL}/cx/en_US/book-a-trip/timetable.html",
        }

        resp = client.post(url, json=payload, headers=headers)

        if resp.status_code != 200:
            msg = f"CX histogram API: HTTP {resp.status_code} (body: {resp.text[:200]})"
            raise RuntimeError(msg)

        result: dict[str, Any] = resp.json()
        return result

    # ------------------------------------------------------------------
    # Public async methods
    # ------------------------------------------------------------------

    @async_retry(
        max_retries=2,
        base_delay=2.0,
        max_delay=15.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_timetable(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
    ) -> dict[str, Any]:
        """Fetch the flight timetable for a route and departure date.

        Returns the raw JSON response from the timetable API.
        """
        cabin = _CABIN_MAP.get(cabin_class, "Y")
        result = await asyncio.to_thread(
            self._get_timetable,
            origin,
            destination,
            departure_date,
            cabin=cabin,
            adults=adults,
        )
        logger.info(
            "CX timetable %s->%s (%s): fetched",
            origin,
            destination,
            departure_date,
        )
        return result

    @async_retry(
        max_retries=2,
        base_delay=2.0,
        max_delay=15.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_histogram(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
    ) -> dict[str, Any]:
        """Fetch the fare histogram (calendar) for a route.

        Returns the raw JSON response from the histogram endpoint.
        """
        cabin = _CABIN_MAP.get(cabin_class, "Y")
        result = await asyncio.to_thread(
            self._get_histogram,
            origin,
            destination,
            departure_date,
            cabin=cabin,
            adults=adults,
        )
        logger.info(
            "CX histogram %s->%s (%s): fetched",
            origin,
            destination,
            departure_date,
        )
        return result

    async def get_destinations(
        self,
        lang: str = "en_US",
    ) -> list[dict[str, Any]]:
        """Fetch all served airports/destinations.

        Used for health checks and route validation.
        """
        return await asyncio.to_thread(self._get_destinations, lang)

    async def health_check(self) -> bool:
        """Check if the Cathay Pacific API is reachable.

        Uses the IBE origin-destination endpoint which has lower
        protection than the timetable/search endpoints.
        """
        try:
            destinations = await self.get_destinations()
            return len(destinations) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
