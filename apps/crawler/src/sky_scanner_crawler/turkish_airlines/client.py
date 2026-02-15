"""Turkish Airlines website API client (L2 direct crawl).

Endpoints (reverse-engineered from turkishairlines.com Next.js SPA):

``POST /api/v1/availability/cheapest-prices``
    Daily price calendar for a route (7-day window around departure).

``POST /api/v1/availability/flight-matrix``
    Full flight search with fare categories and segment details.

``GET /api/v1/booking/locations/TK/{lang}``
    Airport/city autocomplete used for health checks.

``GET /api/v1/parameters``
    App parameters / health check.

Required custom headers (set by the SPA):
    x-platform: WEB
    x-clientid: <uuid4>
    x-bfp: <hex-32>
    x-country: int

The site uses Akamai Bot Manager which may block POST requests
unless a valid ``_abck`` sensor cookie is present.  GET endpoints
(locations, parameters) work without sensor data.  POST endpoints
may intermittently fail with ``Error-DS-30037`` when Akamai
rejects the request.  The retry decorator handles transient failures.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

import primp

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

        # Warm up — visit homepage + booking page to collect cookies.
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
        """No-op — each request creates a fresh primp client."""
