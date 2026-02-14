"""HTTP client for Air Seoul's booking API using primp TLS fingerprint."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://flyairseoul.com"


class AirSeoulClient:
    """Wrapper around Air Seoul's ``flyairseoul.com`` booking API.

    Air Seoul's API requires browser-like TLS fingerprints to bypass
    Cloudflare protection.  We use ``primp`` (Rust-based HTTP client)
    with Chrome impersonation instead of plain ``httpx``.

    The API uses **form-encoded POST** (not JSON).  Sending JSON
    payloads causes ``{"code": "9999"}`` error responses.

    CF protection on Air Seoul is **intermittent** — some sessions
    pass, some get 403.  We create a fresh primp client and warm
    up with a homepage GET before making API calls.
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    def _new_client(self) -> primp.Client:
        """Create a fresh primp client with TLS impersonation."""
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    def _warm_and_post(
        self,
        path: str,
        data: dict[str, str],
    ) -> dict[str, Any]:
        """Warm up with homepage, then POST form data.

        Creates a fresh primp client each time so CF doesn't
        track and block a persistent session.
        """
        client = self._new_client()

        # Warm up — visit homepage to collect CF cookies
        warmup = client.get(f"{_BASE_URL}/I/KO/main.do")
        logger.info(
            "warmup: %s %d",
            warmup.url,
            warmup.status_code,
        )

        resp = client.post(f"{_BASE_URL}{path}", data=data)
        if resp.status_code != 200:
            msg = f"Air Seoul API {path}: HTTP {resp.status_code}"
            raise RuntimeError(msg)
        result: dict[str, Any] = resp.json()
        code = result.get("code", "")
        if code and code != "0000":
            msg = f"Air Seoul API {path}: code={code}"
            raise RuntimeError(msg)
        return result

    @async_retry(
        max_retries=3,
        base_delay=2.0,
        max_delay=20.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_flight_info(
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
        """Fetch flight availability with fares for a date.

        Parameters
        ----------
        origin:
            IATA airport code (e.g. ``ICN``).
        destination:
            IATA airport code (e.g. ``NRT``).
        departure_date:
            Date as ``YYYYMMDD`` (e.g. ``20260301``).
        trip_type:
            ``OW`` (one-way) or ``RT`` (round-trip).
        adults:
            Number of adult passengers.
        children:
            Number of child passengers.
        infants:
            Number of infant passengers.

        Returns
        -------
        dict
            Raw JSON with ``fareShopData`` containing
            ``flightShopDatas`` and ``calendarShopDatas``.
        """
        data = {
            "gubun": "I",
            "depAirport": origin,
            "arrAirport": destination,
            "depDate": departure_date,
            "tripType": trip_type,
            "adtPaxCnt": str(adults),
            "chdPaxCnt": str(children),
            "infPaxCnt": str(infants),
        }
        result = await asyncio.to_thread(
            self._warm_and_post,
            "/I/KO/searchFlightInfo.do",
            data,
        )
        shop_data = result.get("fareShopData", {})
        n_flights = len(shop_data.get("flightShopDatas", []))
        n_cal = len(shop_data.get("calendarShopDatas", []))
        logger.debug(
            "Air Seoul %s→%s (%s): %d flights, %d cal days",
            origin,
            destination,
            departure_date,
            n_flights,
            n_cal,
        )
        return result

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=15.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_route(
        self,
        trip_type: str = "OW",
    ) -> dict[str, Any]:
        """Fetch the Air Seoul route network."""
        data = {
            "tripType": trip_type,
            "language": "KO",
        }
        return await asyncio.to_thread(
            self._warm_and_post,
            "/I/KO/searchRoute.do",
            data,
        )

    async def health_check(self) -> bool:
        """Check if the Air Seoul API is reachable."""
        try:
            result = await asyncio.to_thread(
                self._warm_and_post,
                "/I/KO/searchMemberLimitInfo.do",
                {},
            )
            return "memberLimit" in result
        except Exception:
            return False

    async def close(self) -> None:
        """No-op — each request creates a fresh client."""
