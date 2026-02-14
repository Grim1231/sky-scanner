"""HTTP client for Jin Air's public fare data on S3/CloudFront.

Jin Air publishes pre-computed daily lowest fares at
``fare.jinair.com`` — an unauthenticated AWS S3 bucket fronted by
CloudFront.  No API key, cookies, or TLS fingerprinting needed.

URL patterns::

    # International (and domestic)
    https://fare.jinair.com/{ORIGIN}{DEST}/OW/{COUNTRY}/{CURRENCY}/totalamounts.json

    totalamounts.json  →  fare + tax (what users pay)
    basefares.json     →  fare only (before tax)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_FARE_BASE = "https://fare.jinair.com"


class JinAirClient:
    """Async client for Jin Air's public S3 fare bucket."""

    def __init__(self, *, timeout: int = 15) -> None:
        self._client = httpx.AsyncClient(
            base_url=_FARE_BASE,
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(timeout),
        )

    @async_retry(
        max_retries=2,
        base_delay=0.5,
        max_delay=5.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError),
    )
    async def get_total_fares(
        self,
        origin: str,
        destination: str,
        *,
        trip_type: str = "OW",
        country: str = "KOR",
        currency: str = "KRW",
    ) -> list[dict[str, int]]:
        """Fetch daily lowest total fares for a route.

        Parameters
        ----------
        origin:
            IATA airport code (e.g. ``ICN``).
        destination:
            IATA airport code (e.g. ``NRT``).
        trip_type:
            ``OW`` (one-way) or ``RT`` (round-trip).
        country:
            3-letter origin country code (e.g. ``KOR``).
        currency:
            3-letter currency code (e.g. ``KRW``).

        Returns
        -------
        list[dict[str, int]]
            Array of ``{YYYYMMDD: price}`` entries.
        """
        path = (
            f"/{origin}{destination}/{trip_type}/{country}/{currency}/totalamounts.json"
        )
        resp = await self._client.get(path)
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        logger.debug(
            "Jin Air fares %s→%s (%s %s): %d days",
            origin,
            destination,
            trip_type,
            currency,
            len(data),
        )
        return data

    @async_retry(
        max_retries=2,
        base_delay=0.5,
        max_delay=5.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError),
    )
    async def get_base_fares(
        self,
        origin: str,
        destination: str,
        *,
        trip_type: str = "OW",
        country: str = "KOR",
        currency: str = "KRW",
    ) -> list[dict[str, int]]:
        """Fetch daily lowest base fares (before tax)."""
        path = f"/{origin}{destination}/{trip_type}/{country}/{currency}/basefares.json"
        resp = await self._client.get(path)
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data

    async def health_check(self) -> bool:
        """Check if the Jin Air fare bucket is accessible."""
        try:
            data = await self.get_total_fares(
                "ICN",
                "NRT",
                trip_type="OW",
            )
            return len(data) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """Shut down the underlying HTTPX client."""
        await self._client.aclose()
