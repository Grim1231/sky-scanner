"""Turkish Airlines API clients.

Two client implementations:

1. **TurkishAirlinesClient** (L2 direct crawl) -- reverse-engineered website API.
   Works without any API key by using ``primp`` with Chrome TLS impersonation.
   Subject to Akamai Bot Manager intermittent blocks on POST endpoints.

2. **TurkishAirlinesOfficialClient** -- official developer API from
   ``developer.apim.turkishairlines.com``.  Requires ``apikey`` and
   ``apisecret`` headers obtained by registering an application on the
   developer portal.  Uses ``api.turkishairlines.com`` endpoints.

Official API endpoints (from TK developer portal documentation):

``POST /getAvailability``
    Flight availability search for a city pair / date / pax.

``POST /getTimeTable``
    Weekly/daily/monthly flight schedule for a route.

``GET /getPortList``
    Airport/port listings (IATA codes, city names, countries).

``POST /calculateFlightMiles``
    Frequent-flyer mileage calculations.

Authentication:
    Headers ``apikey`` and ``apisecret`` on every request.

L2 website API endpoints (reverse-engineered):

``POST /api/v1/availability/cheapest-prices``
    Daily price calendar for a route (7-day window around departure).

``POST /api/v1/availability/flight-matrix``
    Full flight search with fare categories and segment details.

``GET /api/v1/booking/locations/TK/{lang}``
    Airport/city autocomplete used for health checks.

``GET /api/v1/parameters``
    App parameters / health check.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

import httpx
import primp

from sky_scanner_crawler.config import settings
from sky_scanner_crawler.retry import async_retry

if TYPE_CHECKING:
    from datetime import date

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.turkishairlines.com"

# Cabin class mapping: our enum value -> TK website value.
_CABIN_MAP: dict[str, str] = {
    "ECONOMY": "Economy",
    "PREMIUM_ECONOMY": "Economy",  # TK has no premium economy.
    "BUSINESS": "Business",
    "FIRST": "Business",  # TK has no first class.
}


# ======================================================================
# Official TK Developer API client
# ======================================================================


class TurkishAirlinesOfficialClient:
    """Async HTTP client for the official Turkish Airlines developer API.

    API portal: https://developer.apim.turkishairlines.com
    Auth: ``apikey`` + ``apisecret`` headers on every request.
    Base URL: ``https://api.turkishairlines.com``

    The official API returns JSON responses.  Endpoint paths use a
    ``/test/`` prefix for the sandbox/test plan; production omits it.
    """

    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def _base_url(self) -> str:
        return f"https://{settings.tk_api_hostname}"

    def _ensure_config(self) -> None:
        if not settings.tk_api_key or not settings.tk_api_secret:
            raise RuntimeError(
                "CRAWLER_TK_API_KEY and CRAWLER_TK_API_SECRET must be set "
                "in environment or .env to use the official TK API"
            )

    async def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self._base_url(),
                timeout=httpx.Timeout(settings.l2_timeout, connect=10),
            )
        return self._http

    def _api_headers(self) -> dict[str, str]:
        """Build headers required by the official TK API."""
        return {
            "apikey": settings.tk_api_key,
            "apisecret": settings.tk_api_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Public async methods
    # ------------------------------------------------------------------

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError, RuntimeError),
    )
    async def get_timetable(
        self,
        origin: str,
        destination: str,
        departure_date: date,
    ) -> dict[str, Any]:
        """Fetch flight timetable from the official TK API.

        ``POST /getTimeTable``

        Returns schedule info: all flights on the requested route with
        operation days for the week.
        """
        self._ensure_config()
        http = await self._ensure_http()

        body: dict[str, Any] = {
            "departureAirportCode": origin,
            "arrivalAirportCode": destination,
            "departureDate": departure_date.isoformat(),
        }

        resp = await http.post(
            "/getTimeTable",
            json=body,
            headers=self._api_headers(),
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        logger.info(
            "TK official timetable %s->%s (%s): success",
            origin,
            destination,
            departure_date,
        )
        return data

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError, RuntimeError),
    )
    async def get_availability(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
    ) -> dict[str, Any]:
        """Fetch flight availability from the official TK API.

        ``POST /getAvailability``

        Returns flight availability with fare families and prices for a
        city pair on a specific date.
        """
        self._ensure_config()
        http = await self._ensure_http()

        body: dict[str, Any] = {
            "departureAirportCode": origin,
            "arrivalAirportCode": destination,
            "departureDate": departure_date.isoformat(),
            "cabinClass": _CABIN_MAP.get(cabin_class, "Economy"),
            "passengerCount": adults,
        }

        resp = await http.post(
            "/getAvailability",
            json=body,
            headers=self._api_headers(),
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        logger.info(
            "TK official availability %s->%s (%s): success",
            origin,
            destination,
            departure_date,
        )
        return data

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError, RuntimeError),
    )
    async def get_port_list(self) -> dict[str, Any]:
        """Fetch airport/port listings from the official TK API.

        ``GET /getPortList``
        """
        self._ensure_config()
        http = await self._ensure_http()

        resp = await http.get(
            "/getPortList",
            headers=self._api_headers(),
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    async def health_check(self) -> bool:
        """Verify credentials and connectivity via getPortList."""
        try:
            self._ensure_config()
            data = await self.get_port_list()
            # Any successful response means the API key works.
            return bool(data)
        except Exception:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()
        self._http = None


# ======================================================================
# L2 website scrape client (existing, unchanged)
# ======================================================================


class TurkishAirlinesClient:
    """Async HTTP client for Turkish Airlines website API.

    Uses ``primp`` (Rust HTTP client) with Chrome TLS impersonation
    to bypass basic bot protection.  Each request creates a fresh
    session to avoid cookie tracking.
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new_client(self) -> primp.Client:
        """Create a fresh primp client with TLS impersonation."""
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    def _api_headers(self) -> dict[str, str]:
        """Build the custom headers required by the TK API."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "x-platform": "WEB",
            "x-clientid": str(uuid.uuid4()),
            "x-bfp": uuid.uuid4().hex,
            "x-country": "int",
        }

    def _build_od_info(
        self,
        origin: str,
        destination: str,
        departure_date: date,
    ) -> dict[str, Any]:
        """Build a single originDestinationInformation entry."""
        return {
            "originAirportCode": origin,
            "destinationAirportCode": destination,
            "departureDate": departure_date.isoformat(),  # YYYY-MM-DD
            "originMultiPort": False,
            "destinationMultiPort": False,
        }

    def _build_payload(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
    ) -> dict[str, Any]:
        """Build the availability request payload.

        This mirrors the ``availabilityPayload`` object constructed
        by the TK SPA booker component.
        """
        passengers: list[dict[str, Any]] = []
        if adults > 0:
            passengers.append({"code": "adult", "quantity": adults})

        return {
            "originDestinationInformationList": [
                self._build_od_info(origin, destination, departure_date),
            ],
            "selectedCabinClass": _CABIN_MAP.get(cabin_class, "Economy"),
            "selectedBookerSearch": "ONE_WAY",
            "passengerTypeList": passengers,
            "moduleType": "Ticketing",
        }

    def _warm_and_post(
        self,
        path: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a fresh session, warm with homepage, then POST.

        Creates a new primp client per call to avoid Akamai
        fingerprint tracking across requests.
        """
        client = self._new_client()

        # Warm up -- visit homepage + booking page to collect cookies.
        warmup = client.get(f"{_BASE_URL}/")
        logger.debug("warmup: %s %d", warmup.url, warmup.status_code)

        client.get(f"{_BASE_URL}/en-int/flights/booking/")

        url = f"{_BASE_URL}{path}"
        resp = client.post(url, json=body, headers=self._api_headers())

        if resp.status_code != 200:
            msg = f"TK API {path}: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        result: dict[str, Any] = resp.json()

        # Check for API-level errors.
        if not result.get("success", False):
            errors = result.get("statusDetailList") or []
            codes = [e.get("code", "") for e in errors]
            msgs = [e.get("translatedMessage", "") for e in errors]
            error_summary = "; ".join(
                f"{c}: {m}" for c, m in zip(codes, msgs, strict=True) if c
            )
            msg = f"TK API {path}: {error_summary}"
            raise RuntimeError(msg)

        return result

    def _get_json(self, path: str) -> dict[str, Any]:
        """Simple GET request (no warm-up needed for GET endpoints)."""
        client = self._new_client()
        client.get(f"{_BASE_URL}/")  # Minimal warmup for cookies.

        url = f"{_BASE_URL}{path}"
        resp = client.get(url, headers=self._api_headers())

        if resp.status_code != 200:
            msg = f"TK API {path}: HTTP {resp.status_code}"
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
    async def get_cheapest_prices(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
    ) -> dict[str, Any]:
        """Fetch the daily price calendar from TK.

        Returns a dict with ``data.dailyPriceList`` containing
        prices for each day around the departure date.
        """
        body = self._build_payload(
            origin, destination, departure_date, cabin_class, adults
        )
        result = await asyncio.to_thread(
            self._warm_and_post,
            "/api/v1/availability/cheapest-prices",
            body,
        )
        logger.info(
            "TK cheapest-prices %s->%s (%s): success",
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
    async def get_flight_matrix(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
    ) -> dict[str, Any]:
        """Fetch the full flight search results from TK.

        Returns a dict with ``data.originDestinationInformationList``
        containing flights with fare categories and segment details.

        The ``responsive`` flag is sent to match the SPA behaviour.
        """
        body = self._build_payload(
            origin, destination, departure_date, cabin_class, adults
        )
        body["responsive"] = True
        result = await asyncio.to_thread(
            self._warm_and_post,
            "/api/v1/availability/flight-matrix",
            body,
        )
        logger.info(
            "TK flight-matrix %s->%s (%s): success",
            origin,
            destination,
            departure_date,
        )
        return result

    async def get_locations(
        self,
        search_text: str,
        *,
        lang: str = "en",
    ) -> dict[str, Any]:
        """Search airports/cities (used for health checks).

        GET ``/api/v1/booking/locations/TK/{lang}?searchText=...``
        """
        path = (
            f"/api/v1/booking/locations/TK/{lang}"
            f"?searchText={search_text}&bookerType=TICKETING"
        )
        return await asyncio.to_thread(self._get_json, path)

    async def health_check(self) -> bool:
        """Verify the TK API is reachable.

        Uses the GET ``/api/v1/parameters`` endpoint which does
        not require Akamai sensor data.
        """
        try:
            result = await asyncio.to_thread(
                self._get_json,
                "/api/v1/parameters",
            )
            return result.get("success", False)
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
