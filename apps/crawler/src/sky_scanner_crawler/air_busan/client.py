"""HTTP client for Air Busan's booking API via Naver Yeti UA bypass.

Air Busan (``www.airbusan.com``) is behind Cloudflare, but the WAF
whitelists the Naver search-crawler User-Agent.  Setting the UA to
``Yeti/1.1`` bypasses the JS challenge entirely — no cookies, no
session warmup, no CSRF tokens.

Endpoint::

    POST / web / bookingApi / flightsAvail

Returns per-flight data: flight numbers, dep/arr times, duration,
multiple fare classes (S/L/A/E) each with price and seat availability.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.airbusan.com"

_HEADERS = {
    "User-Agent": "Yeti/1.1 (NHN Corp.; https://help.naver.com/robots/)",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": "https://www.airbusan.com/web/individual/booking/international",
    "Origin": "https://www.airbusan.com",
}


class AirBusanClient:
    """Async client for Air Busan via Naver Yeti UA bypass."""

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    def _new_client(self) -> primp.Client:
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    def _post(
        self,
        path: str,
        data: dict[str, str],
    ) -> dict[str, Any]:
        """POST form data with Yeti UA — no session needed."""
        client = self._new_client()
        resp = client.post(
            f"{_BASE_URL}{path}",
            headers=_HEADERS,
            data=data,
        )
        if resp.status_code != 200:
            msg = f"Air Busan API {path}: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        result: dict[str, Any] = resp.json()
        if result.get("errorCode"):
            msg = (
                f"Air Busan API {path}: "
                f"{result.get('errorCode')} {result.get('errorDesc', '')}"
            )
            raise RuntimeError(msg)
        return result

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def get_flights_avail(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        *,
        trip_type: str = "OW",
        adults: int = 1,
        children: int = 0,
        infants: int = 0,
    ) -> dict[str, Any]:
        """Fetch flight availability with per-class fares.

        Parameters
        ----------
        origin:
            IATA city code (e.g. ``PUS``, ``ICN``).
        destination:
            IATA city code (e.g. ``NRT``, ``FUK``).
        departure_date:
            Date as ``YYYYMMDD``.
        trip_type:
            ``OW`` (one-way) or ``RT`` (round-trip).
        adults:
            Adult passenger count.

        Returns
        -------
        dict
            JSON with ``listItineraryFare`` containing flights
            and ``pubTaxFuel`` with tax breakdown.
        """
        data = {
            "tripType": trip_type,
            "depCity1": origin,
            "arrCity1": destination,
            "depDate1": departure_date,
            "paxCountAd": str(adults),
            "paxCountCh": str(children),
            "paxCountIn": str(infants),
            "bookingCategory": "Individual",
        }
        result = await asyncio.to_thread(
            self._post, "/web/bookingApi/flightsAvail", data
        )
        n_flights = sum(
            len(itin.get("listFlight", []))
            for itin in result.get("listItineraryFare", [])
        )
        logger.debug(
            "Air Busan %s->%s (%s): %d flights",
            origin,
            destination,
            departure_date,
            n_flights,
        )
        return result

    async def health_check(self) -> bool:
        """Check if the Air Busan API is reachable."""
        try:
            result = await asyncio.to_thread(
                self._post,
                "/web/bookingApi/flightsAvail",
                {
                    "tripType": "OW",
                    "depCity1": "PUS",
                    "arrCity1": "CJU",
                    "depDate1": "20260401",
                    "paxCountAd": "1",
                    "paxCountCh": "0",
                    "paxCountIn": "0",
                    "bookingCategory": "Individual",
                },
            )
            return len(result.get("listItineraryFare", [])) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """No-op — each request creates a fresh client."""
