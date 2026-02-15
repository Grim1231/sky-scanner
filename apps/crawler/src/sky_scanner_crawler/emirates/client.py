"""HTTP client for the Emirates featured-fares and service APIs (L2 direct crawl).

Emirates exposes several public JSON service endpoints on ``emirates.com``
that the Next.js SPA (BEX Runtime) consumes.  No authentication is required.

Endpoints used::

    GET /service/featured-fares
        Returns promotional fare cards for a given country/locale.
        Query params: countryLanguage, geocountrycode, promoted, isTerms

    GET /service/geo
        Returns GeoIP-based continent/country/coordinates.
        Used for health checks.

    GET /service/publications
        Returns all Emirates country publications with locale info.

The featured-fares API returns per-origin fare cards with destination,
price, cabin class, travel period, and booking window.  This gives us
a rich set of price signals across all Emirates routes from a given origin.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.emirates.com"

# Map our CabinClass values to EK's travelClassCode values.
_CABIN_MAP: dict[str, str] = {
    "ECONOMY": "Y",
    "PREMIUM_ECONOMY": "W",
    "BUSINESS": "J",
    "FIRST": "F",
}


class EmiratesClient:
    """Async HTTP client for Emirates public service APIs.

    Uses ``primp`` with Chrome TLS impersonation.  A warm-up GET
    to the featured-fares page is performed before API calls
    to collect cookies and avoid bot detection.
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    def _new_client(self) -> primp.Client:
        """Create a fresh primp client with Chrome TLS impersonation."""
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    def _fetch_featured_fares_sync(
        self,
        country_language: str,
        geocountrycode: str,
    ) -> dict[str, Any]:
        """Synchronous request for featured fares.

        Parameters
        ----------
        country_language:
            Locale string (e.g. ``en-kr``, ``en-us``, ``en-gb``).
        geocountrycode:
            ISO-3166-1 alpha-2 country code (e.g. ``kr``, ``us``).

        Returns
        -------
        dict
            Raw JSON response from the Emirates API.
        """
        client = self._new_client()

        # Warm up to collect cookies.
        client.get(f"{_BASE_URL}/")

        url = (
            f"{_BASE_URL}/service/featured-fares"
            f"?countryLanguage={country_language}"
            f"&geocountrycode={geocountrycode}"
            f"&promoted=false"
            f"&isTerms=true"
        )
        resp = client.get(url)

        if resp.status_code != 200:
            msg = f"Emirates featured-fares API: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        result: dict[str, Any] = resp.json()
        return result

    def _fetch_geo_sync(self) -> dict[str, Any]:
        """Synchronous GeoIP lookup (used for health checks)."""
        client = self._new_client()
        resp = client.get(f"{_BASE_URL}/service/geo")

        if resp.status_code != 200:
            msg = f"Emirates geo API: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        result: dict[str, Any] = resp.json()
        return result

    @async_retry(
        max_retries=2,
        base_delay=2.0,
        max_delay=15.0,
        exceptions=(RuntimeError, OSError),
    )
    async def get_featured_fares(
        self,
        country_language: str = "en-kr",
        geocountrycode: str = "kr",
    ) -> dict[str, Any]:
        """Fetch Emirates featured (promotional) fares for a country.

        Parameters
        ----------
        country_language:
            Locale string (e.g. ``en-kr``, ``en-us``).
        geocountrycode:
            ISO-3166-1 alpha-2 country code.

        Returns
        -------
        dict
            API response with ``results.data.fares`` containing
            per-origin fare cards.
        """
        result = await asyncio.to_thread(
            self._fetch_featured_fares_sync,
            country_language,
            geocountrycode,
        )

        fares = result.get("results", {}).get("data", {}).get("fares", [])
        total_dests = sum(len(f.get("destinations", [])) for f in fares)

        logger.info(
            "Emirates featured-fares (%s): %d origins, %d total fares",
            country_language,
            len(fares),
            total_dests,
        )
        return result

    async def health_check(self) -> bool:
        """Verify the Emirates service API is reachable.

        Uses the ``/service/geo`` endpoint which requires no
        parameters and returns GeoIP data.
        """
        try:
            result = await asyncio.to_thread(self._fetch_geo_sync)
            return "country" in result
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
