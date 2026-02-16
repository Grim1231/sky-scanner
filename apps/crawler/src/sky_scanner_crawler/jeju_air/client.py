"""HTTP client for Jeju Air's internal booking API.

Uses ``primp`` with Chrome TLS impersonation to bypass Akamai Bot Manager
on ``sec.jejuair.net``.  Each request creates a fresh ``primp.Client``
to avoid fingerprint staleness.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://sec.jejuair.net"
_CHANNEL_CODE = "WPC"
_PAGE_ID = "0000000294"

_HEADERS = {
    "Channel-Code": _CHANNEL_CODE,
    "User-Id": "",
    "User-Name": "",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.jejuair.net",
    "Referer": "https://www.jejuair.net/",
}


class JejuAirClient:
    """Async wrapper around Jeju Air's ``sec.jejuair.net`` booking API."""

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    def _new_client(self) -> primp.Client:
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------
    # Synchronous helpers (run via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _fetch_lowest_fares(
        self,
        origin: str,
        destination: str,
        search_month: str,
        pax_type: str,
        pax_count: int,
    ) -> dict[str, Any]:
        client = self._new_client()

        payload = {
            "tripRoute": [
                {
                    "searchStartDate": search_month,
                    "originAirport": origin,
                    "destinationAirport": destination,
                },
            ],
            "passengers": [{"type": pax_type, "count": str(pax_count)}],
            "includeTaxesAndFee": True,
        }

        resp = client.post(
            f"{_BASE_URL}/ko/ibe/booking/searchlowestFareCalendar.json",
            headers=_HEADERS,
            data={
                "lowestFareCalendar": json.dumps(payload),
                "pageId": _PAGE_ID,
            },
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Jeju Air API: HTTP {resp.status_code}")

        data: dict[str, Any] = resp.json()

        if data.get("code") != "0000":
            msg = data.get("message", "Unknown error")
            raise RuntimeError(f"Jeju Air API error: {msg}")

        logger.debug(
            "Jeju Air lowest fares %s→%s (%s): %d days",
            origin,
            destination,
            search_month,
            len(data.get("data", {}).get("lowfares", {}).get("lowFareDateMarkets", [])),
        )
        return data

    def _fetch_stations(self) -> dict[str, Any]:
        client = self._new_client()
        resp = client.post(
            f"{_BASE_URL}/ko/ibe/booking/selectDepartureStations.json",
            headers=_HEADERS,
            data={
                "bookType": "Common",
                "cultureCode": "ko-KR",
                "pageId": _PAGE_ID,
            },
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Jeju Air stations: HTTP {resp.status_code}")

        data: dict[str, Any] = resp.json()
        return data

    # ------------------------------------------------------------------
    # Async public API
    # ------------------------------------------------------------------

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=15.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_lowest_fares(
        self,
        origin: str,
        destination: str,
        search_month: str,
        pax_type: str = "ADT",
        pax_count: int = 1,
    ) -> dict[str, Any]:
        """Fetch lowest daily fares for a route/month.

        Parameters
        ----------
        origin:
            3-letter IATA code (e.g. ``ICN``).
        destination:
            3-letter IATA code (e.g. ``NRT``).
        search_month:
            First day of the month as ``YYYY-MM-01``.
        pax_type:
            Passenger type: ``ADT``, ``CHD``, or ``INF``.
        pax_count:
            Number of passengers of this type.

        Returns
        -------
        dict
            Raw JSON response from the API.
        """
        return await asyncio.to_thread(
            self._fetch_lowest_fares,
            origin,
            destination,
            search_month,
            pax_type,
            pax_count,
        )

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=15.0,
        exceptions=(RuntimeError, OSError),
    )
    async def get_stations(self) -> dict[str, Any]:
        """Fetch all departure stations (route network)."""
        return await asyncio.to_thread(self._fetch_stations)

    async def health_check(self) -> bool:
        """Check if the Jeju Air API is reachable."""
        try:
            data = await self.get_stations()
            return data.get("code") == "0000"
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
