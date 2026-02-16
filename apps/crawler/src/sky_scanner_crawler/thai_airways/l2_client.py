"""HTTP client for Thai Airways fare search via EveryMundo Sputnik + popular-fares API.

Thai Airways (TG) publishes fares through two accessible HTTP endpoints:

**Primary: EveryMundo Sputnik API**
POST ``openair-california.airtrfx.com/airfare-sputnik-service/v3/tg/fares/search``
Returns daily lowest one-way fares across the TG route network (same format as
JL/NZ/ET Sputnik endpoints).

**Fallback: popular-fares API**
POST ``www.thaiairways.com/common/calendarPricing/popular-fares``
Returns cheapest fares for all destinations from a given origin.  Uses custom
headers (``source: website``, ``hostname: https://www.thaiairways.com``) and
requires Chrome TLS fingerprinting (primp) to bypass Cloudflare.

Both approaches avoid the fragile L3 Playwright form automation that suffers
from duplicate element IDs in the OSCI booking widget.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

# EveryMundo Sputnik endpoint for Thai Airways.
_SPUTNIK_URL = (
    "https://openair-california.airtrfx.com/airfare-sputnik-service/v3/tg/fares/search"
)
_SPUTNIK_REFERER = "https://www.thaiairways.com/flights/en/"
_SPUTNIK_ORIGIN = "https://www.thaiairways.com"

# Public EM API key shared across EveryMundo airline tenants.
_EM_API_KEY = "HeQpRjsFI5xlAaSx2onkjc1HTK0ukqA1IrVvd5fvaMhNtzLTxInTpeYB1MK93pah"

# Thai Airways popular-fares endpoint.
_POPULAR_FARES_URL = "https://www.thaiairways.com/common/calendarPricing/popular-fares"

# Default Sputnik search parameters.
_DEFAULT_DAYS_INTERVAL_MIN = 1
_DEFAULT_DAYS_INTERVAL_MAX = 300
_DEFAULT_ROUTES_LIMIT = 100
_DEFAULT_FARES_LIMIT = 500
_DEFAULT_FARES_PER_ROUTE = 5
_DEFAULT_CURRENCY = "KRW"


class ThaiAirwaysL2Client:
    """Async client for Thai Airways fare search via Sputnik + popular-fares.

    Uses primp with Chrome 131 TLS impersonation for both endpoints.

    Usage::

        client = ThaiAirwaysL2Client()
        # Sputnik fares
        fares = await client.search_fares("ICN", "BKK")
        # Popular-fares fallback
        fares = await client.search_popular_fares("ICN")
        await client.close()
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    def _new_client(self) -> primp.Client:
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------
    # Sputnik API (primary)
    # ------------------------------------------------------------------

    def _fetch_sputnik_fares(
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
        """Synchronous Sputnik fare fetch (runs via ``asyncio.to_thread``)."""
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
            "Referer": _SPUTNIK_REFERER,
            "Origin": _SPUTNIK_ORIGIN,
        }

        resp = client.post(_SPUTNIK_URL, headers=headers, json=body)

        if resp.status_code != 200:
            msg = f"TG Sputnik fare search: HTTP {resp.status_code}"
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
        """Fetch daily lowest fares for Thai Airways routes via Sputnik API.

        Parameters
        ----------
        origin:
            IATA airport code to filter origin (e.g. ``ICN``).
            If ``None``, fares from all origins are returned.
        destination:
            IATA airport code to filter destination (e.g. ``BKK``).
            If ``None``, fares to all destinations are returned.
        currency:
            ISO currency code (default ``KRW``).
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
            self._fetch_sputnik_fares,
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
            "TG Sputnik fares %s->%s: %d entries, %d with prices",
            origin or "*",
            destination or "*",
            len(result),
            priced,
        )
        return result

    # ------------------------------------------------------------------
    # Popular-fares API (fallback)
    # ------------------------------------------------------------------

    def _fetch_popular_fares(
        self,
        origin: str,
    ) -> dict[str, Any]:
        """Synchronous popular-fares fetch (runs via ``asyncio.to_thread``)."""
        client = self._new_client()

        body: dict[str, Any] = {
            "journeyType": "ONE_WAY",
            "origins": [origin],
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "source": "website",
            "hostname": "https://www.thaiairways.com",
            "accept-language": "en-kr",
            "Referer": "https://www.thaiairways.com/en-kr/",
            "Origin": "https://www.thaiairways.com",
        }

        resp = client.post(_POPULAR_FARES_URL, headers=headers, json=body)

        if resp.status_code != 200:
            msg = f"TG popular-fares: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: dict[str, Any] = resp.json()
        return data

    @async_retry(
        max_retries=2,
        base_delay=2.0,
        max_delay=15.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_popular_fares(
        self,
        origin: str,
    ) -> dict[str, Any]:
        """Fetch popular fares for all destinations from a given origin.

        Parameters
        ----------
        origin:
            IATA airport code (e.g. ``ICN``).

        Returns
        -------
        dict
            Raw response from the popular-fares endpoint, containing a
            ``prices`` list with route/date/fare entries.
        """
        result = await asyncio.to_thread(
            self._fetch_popular_fares,
            origin,
        )
        # Tag response so the parser knows its source.
        result["_source"] = "popular-fares"
        result["_origin"] = origin
        num_prices = len(result.get("prices", []))
        logger.debug(
            "TG popular-fares from %s: %d price entries",
            origin,
            num_prices,
        )
        return result

    # ------------------------------------------------------------------
    # Health check and cleanup
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Check if the Thai Airways Sputnik API is accessible."""
        try:
            data = await self.search_fares(
                origin="BKK",
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
