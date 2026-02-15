"""HTTP client for Air New Zealand's fare search via EveryMundo Sputnik API.

Air New Zealand uses EveryMundo's airTrfx platform to publish lowest fares.
The ``airfare-sputnik-service`` exposes a fare search endpoint that returns
daily lowest one-way fares across the entire NZ route network.

Flow:
1. POST ``openair-california.airtrfx.com/airfare-sputnik-service/v3/nz/fares/search``
   with ``departureDaysInterval``, ``routesLimit``, ``faresLimit``, and
   optional ``origin`` / ``destination`` filters.
2. Authenticate via the ``em-api-key`` header (public key embedded in the
   Air New Zealand flights page at ``www.airnewzealand.co.nz/flights/en-nz/``).
3. Include ``Referer`` and ``Origin`` headers pointing to the NZ flights page
   (required by Cloudflare / CORS policy).

The endpoint returns an array of fare objects, each containing:
- ``outboundFlight.departureAirportIataCode`` / ``arrivalAirportIataCode``
- ``priceSpecification.totalPrice`` / ``currencyCode``
- ``departureDate`` (YYYY-MM-DD)
- ``outboundFlight.fareClass`` (ECONOMY, BUSINESS, etc.)
- ``flightType`` (DOMESTIC / INTERNATIONAL)

Note: the ``origin`` and ``destination`` body parameters influence ranking but
the API still returns fares across all routes sorted by price.  Filtering
to the requested route must happen client-side.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_FARE_SEARCH_URL = (
    "https://openair-california.airtrfx.com/airfare-sputnik-service/v3/nz/fares/search"
)
_REFERER = "https://www.airnewzealand.co.nz/flights/en-nz/"
_ORIGIN_HEADER = "https://www.airnewzealand.co.nz"

# Public EM API key embedded in the Air NZ flights page.
_EM_API_KEY = "HeQpRjsFI5xlAaSx2onkjc1HTK0ukqA1IrVvd5fvaMhNtzLTxInTpeYB1MK93pah"

# Default search parameters.
_DEFAULT_DAYS_INTERVAL_MIN = 1
_DEFAULT_DAYS_INTERVAL_MAX = 300
_DEFAULT_ROUTES_LIMIT = 100
_DEFAULT_FARES_LIMIT = 500
_DEFAULT_FARES_PER_ROUTE = 5
_DEFAULT_CURRENCY = "NZD"


class AirNzClient:
    """Async client for Air New Zealand fare search via EveryMundo Sputnik."""

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    def _new_client(self) -> primp.Client:
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    def _fetch_fares(
        self,
        origin: str | None,
        destination: str | None,
        *,
        currency: str = _DEFAULT_CURRENCY,
        days_min: int = _DEFAULT_DAYS_INTERVAL_MIN,
        days_max: int = _DEFAULT_DAYS_INTERVAL_MAX,
        routes_limit: int = _DEFAULT_ROUTES_LIMIT,
        fares_limit: int = _DEFAULT_FARES_LIMIT,
        fares_per_route: int = _DEFAULT_FARES_PER_ROUTE,
    ) -> list[dict[str, Any]]:
        """Synchronous fare fetch (runs via ``asyncio.to_thread``)."""
        client = self._new_client()

        body: dict[str, Any] = {
            "currency": currency,
            "departureDaysInterval": {"min": days_min, "max": days_max},
            "routesLimit": routes_limit,
            "faresLimit": fares_limit,
            "faresPerRoute": fares_per_route,
        }
        if origin:
            body["origin"] = origin
        if destination:
            body["destination"] = destination

        headers = {
            "em-api-key": _EM_API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": _REFERER,
            "Origin": _ORIGIN_HEADER,
        }

        resp = client.post(_FARE_SEARCH_URL, headers=headers, json=body)

        if resp.status_code != 200:
            msg = f"Air NZ fare search: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: list[dict[str, Any]] = resp.json()
        return data

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_fares(
        self,
        origin: str | None = None,
        destination: str | None = None,
        *,
        currency: str = _DEFAULT_CURRENCY,
        days_min: int = _DEFAULT_DAYS_INTERVAL_MIN,
        days_max: int = _DEFAULT_DAYS_INTERVAL_MAX,
        routes_limit: int = _DEFAULT_ROUTES_LIMIT,
        fares_limit: int = _DEFAULT_FARES_LIMIT,
        fares_per_route: int = _DEFAULT_FARES_PER_ROUTE,
    ) -> list[dict[str, Any]]:
        """Fetch daily lowest fares for Air New Zealand routes.

        Parameters
        ----------
        origin:
            IATA airport code to filter origin (e.g. ``AKL``).
            If ``None``, fares from all origins are returned.
        destination:
            IATA airport code to filter destination (e.g. ``NRT``).
            If ``None``, fares to all destinations are returned.
        currency:
            ISO currency code (default ``NZD``).
        days_min:
            Minimum days from today for departure window.
        days_max:
            Maximum days from today for departure window.
        routes_limit:
            Max number of routes to return (default 100).
        fares_limit:
            Max total fare entries to return (default 500).
        fares_per_route:
            Max fares per individual route (default 5).

        Returns
        -------
        list[dict]
            Raw fare entries from the Sputnik API.
        """
        result = await asyncio.to_thread(
            self._fetch_fares,
            origin,
            destination,
            currency=currency,
            days_min=days_min,
            days_max=days_max,
            routes_limit=routes_limit,
            fares_limit=fares_limit,
            fares_per_route=fares_per_route,
        )
        priced = sum(
            1
            for e in result
            if e.get("priceSpecification", {}).get("totalPrice", 0) > 0
        )
        logger.debug(
            "Air NZ fares %s->%s: %d entries, %d with prices",
            origin or "*",
            destination or "*",
            len(result),
            priced,
        )
        return result

    async def health_check(self) -> bool:
        """Check if the Air NZ fare API is accessible."""
        try:
            data = await self.search_fares(
                origin="AKL",
                routes_limit=5,
                fares_limit=10,
                fares_per_route=2,
            )
            return any(
                e.get("priceSpecification", {}).get("totalPrice", 0) > 0 for e in data
            )
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
