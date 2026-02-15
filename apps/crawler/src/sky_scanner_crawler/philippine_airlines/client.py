"""Async HTTP client for the Philippine Airlines flight status API.

Philippine Airlines exposes a public flight status API on their main
website (``www.philippineairlines.com``).  No authentication is required.

Endpoint::

    POST / pal / flights / v1 / status

Returns per-route or per-flight-number data: flight legs with scheduled
and actual departure/arrival times, operating airline, airport names,
and codeshare information.

Limitations:
- Schedule data only (no fares/prices).
- Date range limited to approximately 14 days into the future.
- The booking/fare search API (Amadeus DES at ``api-des.philippineairlines.com``)
  is protected by Imperva bot protection and requires a browser-generated
  ``X-D-Token`` header, making L2 fare crawling infeasible.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from sky_scanner_crawler.retry import async_retry

if TYPE_CHECKING:
    from datetime import date

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.philippineairlines.com"
_FLIGHT_STATUS_PATH = "/pal/flights/v1/status"


class PhilippineAirlinesClient:
    """Async client for the Philippine Airlines flight status API.

    Provides schedule data (flight numbers, departure/arrival times,
    operating airline, airports) for PAL-operated routes.
    Does **not** provide fare/pricing data.
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout
        self._http: httpx.AsyncClient | None = None

    async def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=_BASE_URL,
                timeout=httpx.Timeout(self._timeout, connect=10),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                },
            )
        return self._http

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError),
    )
    async def get_flights_by_route(
        self,
        origin: str,
        destination: str,
        flight_date: date,
    ) -> dict[str, Any]:
        """Fetch flight schedule for a route on a given date.

        Parameters
        ----------
        origin:
            3-letter IATA airport code (e.g. ``MNL``).
        destination:
            3-letter IATA airport code (e.g. ``ICN``).
        flight_date:
            The date to query.

        Returns
        -------
        dict
            Raw API response JSON containing ``Details`` with ``leg`` data.

        Raises
        ------
        RuntimeError
            If the API returns an error (e.g. date too far in future).
        """
        http = await self._ensure_http()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_str = flight_date.strftime("%Y%m%d")

        payload: dict[str, Any] = {
            "UniqueReferenceNumber": "sky-scanner-pr",
            "RequestDate": now_str,
            "retrieveFlights": {
                "flightDate": date_str,
                "depStation": origin.upper(),
                "arrStation": destination.upper(),
                "requestType": "STATION",
            },
        }

        resp = await http.post(_FLIGHT_STATUS_PATH, json=payload)

        # Only raise on server errors (5xx); 4xx are not retryable.
        if resp.status_code >= 500:
            resp.raise_for_status()
        if resp.status_code >= 400:
            msg = f"PAL API {resp.status_code}: {resp.text[:200]}"
            raise ValueError(msg)

        data: dict[str, Any] = resp.json()

        if data.get("reply_type") == "error":
            msg = data.get("message", "Unknown error")
            code = data.get("code", "")
            raise ValueError(f"PAL flight status error ({code}): {msg}")

        legs: list[dict[str, Any]] = data.get("Details", {}).get("leg", [])
        logger.debug(
            "PAL %s->%s (%s): %d flights",
            origin,
            destination,
            flight_date.isoformat(),
            len(legs),
        )
        return data

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError),
    )
    async def get_flight_by_number(
        self,
        flight_number: int,
        flight_date: date,
    ) -> dict[str, Any]:
        """Fetch flight status by flight number.

        Parameters
        ----------
        flight_number:
            Numeric flight number (e.g. ``400`` for PR 0400).
        flight_date:
            The date to query.

        Returns
        -------
        dict
            Raw API response JSON.
        """
        http = await self._ensure_http()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_str = flight_date.strftime("%Y%m%d")

        payload: dict[str, Any] = {
            "UniqueReferenceNumber": "sky-scanner-pr",
            "RequestDate": now_str,
            "retrieveFlights": {
                "flightDate": date_str,
                "flightNumber": flight_number,
                "requestType": "FLIGHT",
            },
        }

        resp = await http.post(_FLIGHT_STATUS_PATH, json=payload)

        if resp.status_code >= 500:
            resp.raise_for_status()
        if resp.status_code >= 400:
            msg = f"PAL API {resp.status_code}: {resp.text[:200]}"
            raise ValueError(msg)

        data: dict[str, Any] = resp.json()
        if data.get("reply_type") == "error":
            msg = data.get("message", "Unknown error")
            code = data.get("code", "")
            raise ValueError(f"PAL flight status error ({code}): {msg}")

        return data

    async def health_check(self) -> bool:
        """Check if the Philippine Airlines flight status API is reachable.

        Performs a minimal route query (MNL->CEB for today) to verify.
        """
        try:
            from datetime import date

            data = await self.get_flights_by_route(
                origin="MNL",
                destination="CEB",
                flight_date=date.today(),
            )
            return data.get("Details", {}).get("status") == "okay"
        except Exception:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()
        self._http = None
