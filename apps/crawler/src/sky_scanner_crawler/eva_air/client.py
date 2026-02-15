"""HTTP client for EVA Air's getBestPrices calendar API.

EVA Air exposes a ``getBestPrices.ashx`` handler on their booking
subdomain that returns up to ~300 days of daily lowest one-way fares.

Flow:
1. GET ``www.evaair.com/en-global/index.html`` to establish a session
   (the booking subdomain requires cookies set by the main site).
2. GET ``booking.evaair.com/flyeva/handler/getBestPrices.ashx``
   with ``dep``, ``arr``, and ``interval`` query parameters.

The endpoint automatically selects the departure country's currency
(e.g. TWD for TPE, KRW for ICN, JPY for NRT).

Response::

    {
        "Succ": true,
        "Code": "0000",
        "Data": {
            "currency": "TWD",
            "data": [
                {"date": "2026-02-15T00:00:00", "price": 16825, "highlight": false},
                ...,
            ],
        },
    }

``highlight: true`` marks the cheapest date in the range.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_HOMEPAGE_URL = "https://www.evaair.com/en-global/index.html"
_BEST_PRICES_URL = "https://booking.evaair.com/flyeva/handler/getBestPrices.ashx"

# Default interval that returns ~300 days of data.
_DEFAULT_INTERVAL = 30


class EvaAirClient:
    """Async client for EVA Air's getBestPrices fare calendar."""

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    def _new_client(self) -> primp.Client:
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    def _establish_session(self, client: primp.Client) -> None:
        """Visit the EVA Air homepage to obtain session cookies.

        The ``getBestPrices.ashx`` handler on ``booking.evaair.com``
        returns 403 unless the request carries cookies from the main
        site.  A single GET to the homepage is sufficient.
        """
        resp = client.get(_HOMEPAGE_URL)
        if resp.status_code != 200:
            msg = f"EVA homepage returned HTTP {resp.status_code}"
            raise RuntimeError(msg)
        logger.debug("EVA Air session established")

    def _fetch_best_prices(
        self,
        origin: str,
        destination: str,
        interval: int,
    ) -> dict[str, Any]:
        """Synchronous fare fetch (runs via ``asyncio.to_thread``)."""
        client = self._new_client()
        self._establish_session(client)

        url = f"{_BEST_PRICES_URL}?dep={origin}&arr={destination}&interval={interval}"
        resp = client.get(
            url,
            headers={
                "Referer": _HOMEPAGE_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        if resp.status_code != 200:
            msg = f"EVA getBestPrices: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: dict[str, Any] = resp.json()
        if not data.get("Succ"):
            msg = f"EVA getBestPrices failed: {data.get('Message', 'unknown')}"
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
        *,
        interval: int = _DEFAULT_INTERVAL,
    ) -> dict[str, Any]:
        """Fetch daily lowest fares for a route.

        Parameters
        ----------
        origin:
            IATA airport code (e.g. ``TPE``).
        destination:
            IATA airport code (e.g. ``ICN``).
        interval:
            Number of days ahead (server always returns ~300 days
            regardless, but values > 30 cause server errors).

        Returns
        -------
        dict
            Raw JSON response with ``Data.currency`` and
            ``Data.data`` containing daily fare entries.
        """
        result = await asyncio.to_thread(
            self._fetch_best_prices,
            origin,
            destination,
            interval,
        )
        entries = result.get("Data", {}).get("data", [])
        priced = sum(1 for e in entries if e.get("price", 0) > 0)
        logger.debug(
            "EVA fares %s->%s: %d entries, %d with prices",
            origin,
            destination,
            len(entries),
            priced,
        )
        return result

    async def health_check(self) -> bool:
        """Check if the EVA Air fare API is accessible."""
        try:
            data = await self.get_best_prices("TPE", "ICN")
            entries = data.get("Data", {}).get("data", [])
            return any(e.get("price", 0) > 0 for e in entries)
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
