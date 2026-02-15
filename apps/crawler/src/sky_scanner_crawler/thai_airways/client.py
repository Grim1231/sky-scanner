"""Playwright-based client for Thai Airways flight search.

Thai Airways (TG) uses an Amadeus OSCI backend.  The search flow is:

1. Navigate to ``thaiairways.com/en/booking/flight-search.page``
2. Fill the one-way search form (origin, destination, departure date)
3. Submit the form and wait for XHR/fetch responses
4. Intercept API responses that contain flight availability data

The site is protected by Akamai Bot Manager; using a real Chromium
browser (via Playwright) with stealth settings solves the challenge.
We intercept all network responses matching known flight-data patterns
and return the raw JSON.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from playwright._impl._errors import Error as PlaywrightError
from playwright.async_api import async_playwright

from sky_scanner_crawler.retry import async_retry

if TYPE_CHECKING:
    from datetime import date

    from playwright.async_api import Response

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.thaiairways.com"
_SEARCH_PAGE = f"{_BASE_URL}/en/booking/flight-search.page"

# User-Agent string mimicking a real Chrome browser.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# URL substrings that indicate a flight search result response.
# Thai Airways uses Amadeus OSCI; look for availability or fare responses.
_INTERCEPT_PATTERNS = (
    "/api/",
    "/booking/",
    "availability",
    "OSCI",
    "flightsearch",
    "FlightSearch",
    "airshopping",
    "AirShopping",
    "OfferPrice",
    "offers",
    "low-fare",
    "lowfare",
    "calendar",
)


class ThaiAirwaysClient:
    """Async Playwright client for Thai Airways flight search.

    Navigates to the TG booking page, fills the search form, submits
    it, and intercepts API responses containing flight data.
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    @async_retry(
        max_retries=2,
        base_delay=5.0,
        max_delay=30.0,
        exceptions=(RuntimeError, OSError, PlaywrightError, TimeoutError),
    )
    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
    ) -> list[dict[str, Any]]:
        """Search flights on thaiairways.com and return intercepted API responses.

        Parameters
        ----------
        origin:
            IATA airport code (e.g. ``ICN``).
        destination:
            IATA airport code (e.g. ``BKK``).
        departure_date:
            Date of departure.
        cabin_class:
            Cabin class string (``ECONOMY``, ``BUSINESS``, ``FIRST``).
        adults:
            Number of adult passengers.

        Returns
        -------
        list[dict]
            List of raw JSON response dicts intercepted from flight-data APIs.
        """
        intercepted: list[dict[str, Any]] = []
        date_str = departure_date.strftime("%d/%m/%Y")

        async def _on_response(response: Response) -> None:
            """Capture JSON responses from flight-data endpoints."""
            url = response.url.lower()
            if not any(p in url for p in _INTERCEPT_PATTERNS):
                return

            content_type = response.headers.get("content-type", "")
            if "json" not in content_type and "javascript" not in content_type:
                return

            try:
                body = await response.json()
                if isinstance(body, dict) and body:
                    intercepted.append(body)
                    logger.debug(
                        "TG intercepted response from %s (%d bytes)",
                        response.url[:120],
                        len(json.dumps(body)),
                    )
            except Exception:
                pass

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = await browser.new_context(
                user_agent=_USER_AGENT,
                locale="en-US",
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            # Stealth: remove webdriver flag.
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            # Register response interceptor before navigation.
            page.on("response", _on_response)

            try:
                # Navigate to the search page.
                await page.goto(
                    _SEARCH_PAGE,
                    wait_until="domcontentloaded",
                    timeout=self._timeout * 1000,
                )

                # Wait for page to stabilise (Akamai challenge may run).
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    logger.debug("TG page did not reach networkidle; using fixed delay")
                    await page.wait_for_timeout(5000)

                # Verify we are on the right domain.
                if "thaiairways.com" not in page.url:
                    msg = f"TG navigation failed: landed on {page.url}"
                    raise RuntimeError(msg)

                # === Fill the search form ===
                # Thai Airways uses a React/Angular SPA for booking.
                # Selectors are best-effort based on common Amadeus OSCI
                # booking widget patterns.  May need adjustment.

                # Select one-way trip.
                ow_selectors = [
                    'input[value="oneway"]',
                    'label:has-text("One Way")',
                    '[data-trip-type="OW"]',
                    'input[name="tripType"][value="OW"]',
                    "#oneWay",
                    'label[for="oneWay"]',
                ]
                for sel in ow_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            await el.click(timeout=3000)
                            logger.debug("TG: clicked one-way selector %s", sel)
                            break
                    except Exception:
                        continue

                # Fill origin.
                origin_selectors = [
                    'input[placeholder*="From"]',
                    'input[aria-label*="From"]',
                    'input[aria-label*="Origin"]',
                    'input[name="origin"]',
                    'input[id*="origin"]',
                    'input[data-testid*="origin"]',
                    "#fromCity",
                ]
                await self._fill_airport_field(page, origin_selectors, origin, "origin")

                # Fill destination.
                dest_selectors = [
                    'input[placeholder*="To"]',
                    'input[aria-label*="To"]',
                    'input[aria-label*="Destination"]',
                    'input[name="destination"]',
                    'input[id*="destination"]',
                    'input[data-testid*="destination"]',
                    "#toCity",
                ]
                await self._fill_airport_field(
                    page, dest_selectors, destination, "destination"
                )

                # Fill departure date.
                date_selectors = [
                    'input[placeholder*="Depart"]',
                    'input[aria-label*="Depart"]',
                    'input[name="departureDate"]',
                    'input[id*="depart"]',
                    'input[data-testid*="depart"]',
                    "#departDate",
                ]
                for sel in date_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            await el.click(timeout=3000)
                            await el.fill(date_str, timeout=3000)
                            logger.debug("TG: filled departure date via %s", sel)
                            break
                    except Exception:
                        continue

                # Try to set cabin class if UI allows.
                cabin_selectors = [
                    'select[name="cabinClass"]',
                    "#cabinClass",
                    'select[aria-label*="class"]',
                ]
                cabin_val_map = {
                    "ECONOMY": "economy",
                    "PREMIUM_ECONOMY": "premium",
                    "BUSINESS": "business",
                    "FIRST": "first",
                }
                cabin_val = cabin_val_map.get(cabin_class, "economy")
                for sel in cabin_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            await el.select_option(value=cabin_val, timeout=3000)
                            logger.debug("TG: selected cabin via %s", sel)
                            break
                    except Exception:
                        continue

                # Click search button.
                search_selectors = [
                    'button[type="submit"]',
                    'button:has-text("Search")',
                    'button:has-text("search")',
                    'a:has-text("Search")',
                    "#searchFlight",
                    'button[data-testid*="search"]',
                    ".search-button",
                    'input[type="submit"]',
                ]
                clicked = False
                for sel in search_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            await el.click(timeout=5000)
                            logger.debug("TG: clicked search via %s", sel)
                            clicked = True
                            break
                    except Exception:
                        continue

                if not clicked:
                    # Fallback: press Enter on the page.
                    await page.keyboard.press("Enter")
                    logger.debug("TG: pressed Enter as search fallback")

                # Wait for search results (intercepted responses).
                # The Amadeus OSCI backend typically takes 10-30 seconds.
                await self._wait_for_results(page, intercepted, timeout_ms=60000)

            finally:
                await browser.close()

        if not intercepted:
            logger.warning(
                "TG: no API responses intercepted for %s->%s on %s",
                origin,
                destination,
                departure_date,
            )

        logger.info(
            "TG: intercepted %d API responses for %s->%s on %s",
            len(intercepted),
            origin,
            destination,
            departure_date,
        )
        return intercepted

    async def _fill_airport_field(
        self,
        page: Any,
        selectors: list[str],
        code: str,
        field_name: str,
    ) -> None:
        """Fill an airport autocomplete field by trying multiple selectors."""
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click(timeout=3000)
                    await el.fill("", timeout=1000)
                    await el.type(code, delay=100, timeout=5000)
                    # Wait for autocomplete dropdown.
                    await page.wait_for_timeout(1500)
                    # Try to click the first suggestion.
                    suggestion_selectors = [
                        f'li:has-text("{code}")',
                        f'[data-value="{code}"]',
                        ".autocomplete-item:first-child",
                        ".suggestion-item:first-child",
                        "ul.dropdown li:first-child",
                        f'option[value="{code}"]',
                    ]
                    for sug_sel in suggestion_selectors:
                        try:
                            sug = page.locator(sug_sel).first
                            if await sug.is_visible(timeout=1500):
                                await sug.click(timeout=2000)
                                break
                        except Exception:
                            continue
                    logger.debug("TG: filled %s via %s", field_name, sel)
                    return
            except Exception:
                continue

        logger.warning("TG: could not fill %s field with code %s", field_name, code)

    async def _wait_for_results(
        self,
        page: Any,
        intercepted: list[dict[str, Any]],
        *,
        timeout_ms: int = 60000,
    ) -> None:
        """Wait for flight search results to appear.

        Polls for intercepted responses or DOM changes indicating
        search results have loaded.
        """
        poll_interval = 2000
        elapsed = 0

        while elapsed < timeout_ms:
            # Check if we have intercepted meaningful responses.
            if intercepted:
                # Wait a bit more for additional responses.
                await page.wait_for_timeout(3000)
                return

            # Check DOM for results indicators.
            result_indicators = [
                ".flight-result",
                ".flight-list",
                ".search-results",
                "[data-flight]",
                ".itinerary",
                ".fare-card",
                ".no-flights",
                ".no-results",
                'text="No flights"',
                'text="no flights"',
            ]
            for indicator in result_indicators:
                try:
                    el = page.locator(indicator).first
                    if await el.is_visible(timeout=500):
                        # Results loaded in DOM.
                        await page.wait_for_timeout(2000)
                        return
                except Exception:
                    continue

            await page.wait_for_timeout(poll_interval)
            elapsed += poll_interval

        logger.warning(
            "TG: timed out waiting for results after %dms",
            timeout_ms,
        )

    async def search_flights_via_evaluate(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
    ) -> dict[str, Any] | None:
        """Alternative: execute fetch() from within the browser context.

        If the form-filling approach fails, this method attempts to
        call the Amadeus OSCI API directly from the browser context,
        inheriting cookies and Akamai session.

        NOTE: This requires knowing the exact API endpoint and payload
        structure, which may need to be captured via browser DevTools.
        Returns None if the endpoint is not yet confirmed.
        """
        # Placeholder for direct API call via page.evaluate().
        # The exact OSCI endpoint and payload structure need to be
        # determined by inspecting network traffic in DevTools.
        logger.info(
            "TG: direct evaluate search not yet implemented for %s->%s",
            origin,
            destination,
        )
        return None

    async def health_check(self) -> bool:
        """Check if the Thai Airways website is reachable."""
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox"],
                )
                context = await browser.new_context(user_agent=_USER_AGENT)
                page = await context.new_page()

                try:
                    resp = await page.goto(
                        _BASE_URL,
                        wait_until="domcontentloaded",
                        timeout=self._timeout * 1000,
                    )
                    ok = resp is not None and resp.status < 400
                finally:
                    await browser.close()

                return ok
        except Exception:
            logger.exception("TG health check failed")
            return False

    async def close(self) -> None:
        """No-op -- each search opens and closes its own browser."""
