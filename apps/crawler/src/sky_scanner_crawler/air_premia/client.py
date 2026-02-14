"""Playwright-assisted HTTP client for Air Premia's fare API.

Air Premia's route endpoints (/api/v1/airports, /api/v1/airport-regions) are
publicly accessible, but fare endpoints (/api/v1/low-fares, /api/v1/fares)
are protected by Cloudflare JS Challenge.

Strategy:
1. Use Playwright to load airpremia.com (solves CF challenge, gets cf_clearance)
2. Extract cookies from the browser context
3. Use those cookies with httpx for fast subsequent API calls
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.airpremia.com"


class AirPremiaClient:
    """Async client for Air Premia's API, using Playwright to bypass Cloudflare."""

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout
        self._http_client: httpx.AsyncClient | None = None
        self._cookies_obtained = False

    async def _obtain_cf_cookies(self) -> None:
        """Launch Playwright, visit Air Premia, and extract CF cookies."""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            await page.goto(_BASE_URL, wait_until="networkidle", timeout=30000)

            # Extract all cookies from the browser
            cookies = await context.cookies()
            await browser.close()

        # Build httpx client with extracted cookies
        cookie_jar = httpx.Cookies()
        for c in cookies:
            cookie_jar.set(c["name"], c["value"], domain=c.get("domain", ""))

        self._http_client = httpx.AsyncClient(
            base_url=_BASE_URL,
            cookies=cookie_jar,
            headers={
                "Accept": "application/json",
                "Referer": f"{_BASE_URL}/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            },
            timeout=httpx.Timeout(self._timeout),
        )
        self._cookies_obtained = True
        logger.debug(
            "Air Premia CF cookies obtained: %d cookies",
            len(cookies),
        )

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure we have an authenticated httpx client."""
        if not self._cookies_obtained or self._http_client is None:
            await self._obtain_cf_cookies()
        assert self._http_client is not None
        return self._http_client

    async def get_low_fares(
        self,
        origin: str,
        destination: str,
        begin_date: str,
        end_date: str,
        trip_type: str = "OW",
        adt_count: int = 1,
    ) -> dict[str, Any]:
        """Fetch daily lowest fares for a route/date range.

        Parameters
        ----------
        origin:
            IATA station code (e.g. ``ICN``).
        destination:
            IATA station code (e.g. ``NRT``).
        begin_date:
            Start date as ``YYYY-MM-DD``.
        end_date:
            End date as ``YYYY-MM-DD``.
        trip_type:
            ``OW`` (one-way), ``RT`` (round-trip).
        adt_count:
            Number of adult passengers.

        Returns
        -------
        dict
            Raw JSON response from the API.
        """
        client = await self._ensure_client()
        resp = await client.get(
            "/api/v1/low-fares",
            params={
                "origin": origin,
                "destination": destination,
                "beginDate": begin_date,
                "endDate": end_date,
                "tripType": trip_type,
                "adtCount": str(adt_count),
            },
        )

        # If CF challenge again, re-obtain cookies and retry once
        if resp.status_code == 403 and "Just a moment" in resp.text:
            logger.warning("CF challenge on low-fares, re-obtaining cookies")
            self._cookies_obtained = False
            client = await self._ensure_client()
            resp = await client.get(
                "/api/v1/low-fares",
                params={
                    "origin": origin,
                    "destination": destination,
                    "beginDate": begin_date,
                    "endDate": end_date,
                    "tripType": trip_type,
                    "adtCount": str(adt_count),
                },
            )

        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    async def get_airports(self) -> list[dict[str, Any]]:
        """Fetch all active airports (no CF protection)."""
        async with httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(self._timeout),
        ) as client:
            resp = await client.get(
                "/api/v1/airports",
                params={"isActive": "true"},
            )
            resp.raise_for_status()
            data: list[dict[str, Any]] = resp.json()
            return data

    async def get_destinations(self, origin: str) -> dict[str, Any]:
        """Fetch destinations from a given origin (no CF protection)."""
        async with httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(self._timeout),
        ) as client:
            resp = await client.get(f"/api/v1/airports/{origin}/destinations")
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

    async def health_check(self) -> bool:
        """Check if Air Premia's route API is reachable."""
        try:
            airports = await self.get_airports()
            return len(airports) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """Shut down the underlying httpx client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
