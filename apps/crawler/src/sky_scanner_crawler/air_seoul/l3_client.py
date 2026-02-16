"""Playwright-based client for Air Seoul's booking API.

Air Seoul's ``flyairseoul.com`` is protected by Cloudflare, which
hard-blocks ``primp``'s TLS fingerprint with 403.  Extracting cookies
and using httpx also fails because Cloudflare binds ``cf_clearance``
to the browser's TLS fingerprint (JA3 hash).

Strategy:
1. Launch Playwright Chromium in new-headless mode (``headless=False`` +
   ``--headless=new`` arg) with anti-detection patches.
2. Navigate to flyairseoul.com root to solve the CF Turnstile challenge
   (the root URL triggers CF challenge then redirects to ``/CW/ko/main.do``).
3. Keep the browser alive and make API calls via ``page.evaluate(fetch())``
   so requests use the browser's TLS stack and cookies natively.
4. On 403, reset the browser and retry.

Note: Cloudflare may impose a WAF rule that blocks all POST requests
to the ``/I/KO/`` path prefix regardless of cookies.  In that case the
L3 client will fail and the crawler falls back to Amadeus GDS.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://flyairseoul.com"

# JS fetch code executed inside the browser page.
_FETCH_JS = """
async ([url, body]) => {
    const resp = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type':
                'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept':
                'application/json, text/javascript, */*; q=0.01',
        },
        body: body,
    });
    return {
        status: resp.status,
        body: await resp.text(),
    };
}
"""

# Anti-detection init script — removes common headless fingerprints.
_ANTI_DETECT_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', {
    get: () => ['ko-KR', 'ko', 'en-US', 'en'],
});
window.chrome = { runtime: {} };
"""


class AirSeoulL3Client:
    """Async client for Air Seoul using Playwright for all requests.

    Keeps the browser alive and makes API calls through
    ``page.evaluate(fetch(...))`` so that Cloudflare sees the same
    TLS fingerprint that solved the challenge.
    """

    def __init__(self, *, timeout: int = 60) -> None:
        self._timeout = timeout
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def _ensure_page(self) -> Page:
        """Ensure a browser page is ready with CF challenge solved."""
        if self._page is not None:
            return self._page

        logger.info("Air Seoul L3: launching browser")
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=False,
            args=[
                "--headless=new",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self._context = await self._browser.new_context(locale="ko-KR")
        await self._context.add_init_script(_ANTI_DETECT_JS)
        self._page = await self._context.new_page()

        # Navigate to root — CF Turnstile challenge auto-solves here
        # and redirects to /CW/ko/main.do.
        logger.info("Air Seoul L3: solving CF challenge")
        await self._page.goto(
            _BASE_URL,
            wait_until="commit",
            timeout=self._timeout * 1000,
        )

        # Wait for CF to redirect to the main page (up to 30s).
        try:
            await self._page.wait_for_url(
                "**/main.do*",
                timeout=30000,
            )
        except Exception:
            # Fallback: just wait for network to settle.
            with contextlib.suppress(Exception):
                await self._page.wait_for_load_state(
                    "networkidle",
                    timeout=15000,
                )

        # Small extra wait for any deferred cookie setting.
        await asyncio.sleep(1)

        cookies = await self._context.cookies()
        has_clearance = any(c["name"] == "cf_clearance" for c in cookies)
        logger.info(
            "Air Seoul L3: page loaded (url=%s, cf_clearance=%s, cookies=%d)",
            self._page.url,
            has_clearance,
            len(cookies),
        )
        return self._page

    async def _reset_browser(self) -> None:
        """Close and re-create browser to get fresh CF clearance."""
        logger.info("Air Seoul L3: resetting browser")
        await self._close_browser()
        await self._ensure_page()

    async def _close_browser(self) -> None:
        """Close browser resources."""
        for attr, method in [
            ("_page", "close"),
            ("_context", "close"),
            ("_browser", "close"),
            ("_pw", "stop"),
        ]:
            obj = getattr(self, attr, None)
            if obj is not None:
                with contextlib.suppress(Exception):
                    await getattr(obj, method)()
                setattr(self, attr, None)

    async def _post_via_browser(
        self,
        path: str,
        data: dict[str, str],
    ) -> dict[str, Any]:
        """POST form data via the browser's fetch API.

        Uses ``page.evaluate(fetch(...))`` so the request inherits
        the browser's TLS stack and CF cookies.
        """
        page = await self._ensure_page()
        url = f"{_BASE_URL}{path}"

        # Build URL-encoded form body.
        form_body = "&".join(f"{k}={v}" for k, v in data.items())

        resp = await page.evaluate(_FETCH_JS, [url, form_body])

        status = resp["status"]
        body_text = resp["body"]

        if status == 403:
            msg = f"Air Seoul L3 API {path}: HTTP 403 (CF blocked)"
            raise RuntimeError(msg)

        if status != 200:
            msg = f"Air Seoul L3 API {path}: HTTP {status}"
            raise RuntimeError(msg)

        result: dict[str, Any] = json.loads(body_text)
        return result

    @async_retry(
        max_retries=1,
        base_delay=2.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError, TimeoutError),
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

        try:
            result = await self._post_via_browser(
                "/I/KO/searchFlightInfo.do",
                data,
            )
        except RuntimeError as exc:
            if "403" in str(exc):
                # CF blocked -- reset browser and let retry handle it.
                await self._reset_browser()
            raise

        code = result.get("code", "")
        if code and code != "0000":
            msg = f"Air Seoul L3 API: code={code}"
            raise RuntimeError(msg)

        shop_data = result.get("fareShopData", {})
        n_flights = len(shop_data.get("flightShopDatas", []))
        n_cal = len(shop_data.get("calendarShopDatas", []))
        logger.debug(
            "Air Seoul L3 %s->%s (%s): %d flights, %d cal days",
            origin,
            destination,
            departure_date,
            n_flights,
            n_cal,
        )
        return result

    async def health_check(self) -> bool:
        """Check if the Air Seoul API is reachable via Playwright."""
        try:
            result = await self._post_via_browser(
                "/I/KO/searchMemberLimitInfo.do",
                {},
            )
            return "memberLimit" in result
        except Exception:
            return False

    async def close(self) -> None:
        """Shut down the browser."""
        await self._close_browser()
