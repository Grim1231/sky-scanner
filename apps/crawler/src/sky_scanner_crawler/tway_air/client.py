"""HTTP client for T'way Air fares via the travel agency portal.

The main site (``www.twayair.com``) protects fare endpoints with
Akamai Bot Manager, but the travel agency portal
(``tagency.twayair.com``) exposes the **same API** without Akamai.

Flow:
1. GET ``/app/booking/searchItinerary`` to establish session + get CSRF
2. POST ``/ajax/booking/getLowestFare`` with CSRF token header

Response is JSON with pipe-delimited fare strings::

    {"OW": {"20260301": "20260301|ICN|NRT|N|N|Y|N|100000.0|138700.0|SmartFare"}}

Fields: date|dep|arr|soldOut|bizSoldOut|operating|bizOperating|fare|totalFare|fareClass
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://tagency.twayair.com"


class TwayAirClient:
    """Async client for T'way Air via ``tagency.twayair.com``."""

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout
        self._csrf_token: str | None = None

    def _new_client(self) -> primp.Client:
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    def _ensure_session(self, client: primp.Client) -> str:
        """Visit the booking page to get a session and CSRF token."""
        resp = client.get(
            f"{_BASE_URL}/app/booking/searchItinerary",
        )
        if resp.status_code != 200:
            msg = f"T'way session page: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        m = re.search(
            r'<meta\s+name="_csrf"\s+content="([^"]+)"',
            resp.text,
        )
        if not m:
            msg = "T'way: CSRF token not found in HTML"
            raise RuntimeError(msg)

        token = m.group(1)
        logger.debug("T'way CSRF token obtained: %s...", token[:12])
        return token

    def _fetch_fares(
        self,
        origin: str,
        destination: str,
        trip_type: str,
        currency: str,
    ) -> dict[str, Any]:
        """Synchronous fare fetch (runs in thread)."""
        client = self._new_client()
        csrf = self._ensure_session(client)

        resp = client.post(
            f"{_BASE_URL}/ajax/booking/getLowestFare",
            headers={
                "X-CSRF-TOKEN": csrf,
                "X-Requested-With": "XMLHttpRequest",
            },
            data={
                "tripType": trip_type,
                "bookingType": "PASSENGER",
                "currency": currency,
                "depAirport": origin,
                "arrAirport": destination,
                "baseDeptAirportCode": origin,
            },
        )
        if resp.status_code != 200:
            msg = f"T'way fare API: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        result: dict[str, Any] = resp.json()
        return result

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def get_lowest_fares(
        self,
        origin: str,
        destination: str,
        *,
        trip_type: str = "OW",
        currency: str = "KRW",
    ) -> dict[str, Any]:
        """Fetch daily lowest fares for a route.

        Parameters
        ----------
        origin:
            IATA airport code (e.g. ``ICN``).
        destination:
            IATA airport code (e.g. ``NRT``).
        trip_type:
            ``OW`` (one-way) or ``RT`` (round-trip).
        currency:
            Currency code (``KRW``, ``USD``, ``JPY``).

        Returns
        -------
        dict
            JSON with ``OW`` (and optionally ``RT``) keys,
            each mapping ``YYYYMMDD`` to pipe-delimited fare
            strings.
        """
        result = await asyncio.to_thread(
            self._fetch_fares,
            origin,
            destination,
            trip_type,
            currency,
        )
        ow_count = len(result.get("OW", {}))
        logger.debug(
            "T'way fares %s→%s: %d OW entries",
            origin,
            destination,
            ow_count,
        )
        return result

    async def health_check(self) -> bool:
        """Check if the T'way agency portal is accessible."""
        try:
            data = await self.get_lowest_fares("ICN", "NRT")
            return len(data.get("OW", {})) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """No-op — each request creates a fresh client."""
