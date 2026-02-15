"""HTTP client for LOT Polish Airlines fare API.

LOT runs an AEM-powered site with internal JSON APIs.  While the main
low-fare calendar endpoint requires Akamai JS challenge completion,
the **watchlist price boxes** endpoint is accessible via primp TLS
fingerprinting after visiting the homepage.

Endpoints used:

``watchlistPriceBoxesSearch.json``
    Returns curated price boxes for a route (economy + business,
    with round-trip prices and departure/return dates).

``airports.json``
    Full airport/city dataset for health checks.

URL pattern::

    /api/{locale}/watchlistPriceBoxesSearch.json/{ORIGIN}-{DEST}.json

Response::

    {
        "priceBoxes": [
            {
                "originAirportIATA": "WAW",
                "destinationAirportIATA": "ICN",
                "cabinClassCode": "E",
                "priceValue": "2485",
                "priceCurrency": "PLN",
                "tripTypeCode": "R",
                "bookerDepartureTime": "15-03-2026",
                "bookerReturnTime": "25-03-2026",
                ...
            }
        ]
    }
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.lot.com"
_DEFAULT_LOCALE = "pl/en"


class LotPolishClient:
    """Async client for LOT Polish Airlines fare API."""

    def __init__(self, *, timeout: int = 30, locale: str = _DEFAULT_LOCALE) -> None:
        self._timeout = timeout
        self._locale = locale

    def _new_client(self) -> primp.Client:
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    def _establish_session(self, client: primp.Client) -> None:
        """Visit the LOT homepage to obtain cookies for the API."""
        url = f"{_BASE_URL}/{self._locale}"
        resp = client.get(url)
        if resp.status_code != 200:
            msg = f"LOT homepage returned HTTP {resp.status_code}"
            raise RuntimeError(msg)
        logger.debug("LOT session established via %s", url)

    def _fetch_price_boxes(
        self,
        origin: str,
        destination: str,
    ) -> dict[str, Any]:
        """Synchronous price box fetch (runs via ``asyncio.to_thread``)."""
        client = self._new_client()
        self._establish_session(client)

        path = (
            f"/api/{self._locale}/watchlistPriceBoxesSearch.json"
            f"/{origin}-{destination}.json"
        )
        resp = client.get(
            f"{_BASE_URL}{path}",
            headers={
                "Referer": f"{_BASE_URL}/{self._locale}",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            },
        )
        if resp.status_code != 200:
            msg = f"LOT price boxes: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: dict[str, Any] = resp.json()
        return data

    def _fetch_airports(self) -> dict[str, Any]:
        """Fetch the full airport dataset (for health checks)."""
        client = self._new_client()
        self._establish_session(client)

        resp = client.get(
            f"{_BASE_URL}/api/{self._locale}/airports.json",
            headers={
                "Referer": f"{_BASE_URL}/{self._locale}",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            },
        )
        if resp.status_code != 200:
            msg = f"LOT airports: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: dict[str, Any] = resp.json()
        return data

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def get_price_boxes(
        self,
        origin: str,
        destination: str,
    ) -> dict[str, Any]:
        """Fetch watchlist price boxes for a route.

        Parameters
        ----------
        origin:
            IATA airport code (e.g. ``WAW``).
        destination:
            IATA airport code (e.g. ``ICN``).

        Returns
        -------
        dict
            JSON with ``priceBoxes`` list containing fare data.
        """
        result = await asyncio.to_thread(
            self._fetch_price_boxes,
            origin,
            destination,
        )
        boxes = result.get("priceBoxes", [])
        logger.debug(
            "LOT price boxes %s->%s: %d entries",
            origin,
            destination,
            len(boxes),
        )
        return result

    async def health_check(self) -> bool:
        """Check if the LOT API is accessible."""
        try:
            data = await asyncio.to_thread(self._fetch_airports)
            countries = data.get("countries", [])
            return len(countries) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
