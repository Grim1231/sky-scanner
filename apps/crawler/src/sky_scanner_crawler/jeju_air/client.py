"""HTTP client for Jeju Air's internal booking API."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://sec.jejuair.net"
_CHANNEL_CODE = "WPC"
_PAGE_ID = "0000000294"


class JejuAirClient:
    """Async wrapper around Jeju Air's ``sec.jejuair.net`` booking API."""

    def __init__(self, *, timeout: int = 30) -> None:
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "Channel-Code": _CHANNEL_CODE,
                "User-Id": "",
                "User-Name": "",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://www.jejuair.net",
                "Referer": "https://www.jejuair.net/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/144.0.0.0 Safari/537.36"
                ),
            },
            timeout=httpx.Timeout(timeout),
        )

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=15.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError),
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

        resp = await self._client.post(
            "/ko/ibe/booking/searchlowestFareCalendar.json",
            data={
                "lowestFareCalendar": json.dumps(payload),
                "pageId": _PAGE_ID,
            },
        )
        resp.raise_for_status()
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

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=15.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError),
    )
    async def get_stations(self) -> dict[str, Any]:
        """Fetch all departure stations (route network)."""
        resp = await self._client.post(
            "/ko/ibe/booking/selectDepartureStations.json",
            data={
                "bookType": "Common",
                "cultureCode": "ko-KR",
                "pageId": _PAGE_ID,
            },
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    async def health_check(self) -> bool:
        """Check if the Jeju Air API is reachable."""
        try:
            data = await self.get_stations()
            return data.get("code") == "0000"
        except Exception:
            return False

    async def close(self) -> None:
        """Shut down the underlying HTTPX client."""
        await self._client.aclose()
