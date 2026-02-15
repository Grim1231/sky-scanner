"""Playwright-based client for ANA's international flight search.

ANA (All Nippon Airways) uses an SPA booking widget on ana.co.jp that talks
to ``aswbe.ana.co.jp``.  The search API returns 401 when called directly,
and the site is protected by Akamai Bot Manager.

Strategy (L3 -- full browser automation):
1. Launch Playwright Chromium (headless, with anti-detection tweaks).
2. Navigate to ``https://www.ana.co.jp/en/jp/international/``.
3. Fill the booking search form via button clicks + airport/date selectors.
4. Click "Search" and intercept the JSON responses from the booking engine
   (``aswbe.ana.co.jp/webapps/...``).
5. Return the raw flight result data.

Alternative fallback: navigate directly to the booking engine URL with
query parameters and scrape the results DOM.

Note: ANA's SPA uses custom React-like components, not standard <select>/<input>.
Airport selectors are button-triggered popups.  Selectors documented below are
best-effort; they may need updating when ANA redesigns the site.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from playwright._impl._errors import Error as PlaywrightError
from playwright.async_api import async_playwright

from sky_scanner_crawler.retry import async_retry

if TYPE_CHECKING:
    from datetime import date

    from playwright.async_api import Page, Response

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.ana.co.jp"
_INTL_PAGE = f"{_BASE_URL}/en/jp/international/"

# Booking engine domain -- API responses come from here.
_BOOKING_DOMAIN = "aswbe.ana.co.jp"

# Direct booking engine search URL (used as fallback).
_BOOKING_SEARCH_URL = (
    "https://aswbe.ana.co.jp/webapps/reservation/flight-search"
    "?CONNECTION_KIND=JPN&LANG=en"
)

# User-Agent matching a real Chrome on macOS.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Timeout for page navigation and network waits (ms).
_NAV_TIMEOUT_MS = 45_000
_SEARCH_TIMEOUT_MS = 60_000


class AnaPlaywrightClient:
    """Async Playwright client for ANA international flight search.

    Each ``search_flights`` call opens a fresh browser session, fills the
    search form, and returns the raw result data.  The browser is closed
    after each call to avoid stale Akamai sessions.
    """

    def __init__(self, *, timeout: int = 60) -> None:
        self._timeout = timeout

    async def _setup_page(self, page: Page) -> None:
        """Apply anti-bot-detection patches to a Playwright page."""
        await page.add_init_script(
            """
            // Remove webdriver flag.
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            // Override permissions query for notifications.
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) =>
                params.name === 'notifications'
                    ? Promise.resolve({state: Notification.permission})
                    : origQuery(params);
            """
        )

    async def _fill_airport(
        self,
        page: Page,
        *,
        field: str,
        code: str,
    ) -> None:
        """Click the airport selector button and type the IATA code.

        Parameters
        ----------
        page:
            Active Playwright page.
        field:
            Either ``"From"`` or ``"To"`` -- used to locate the heading.
        code:
            3-letter IATA airport code (e.g. ``NRT``).
        """
        # The booking widget uses h5 headings "From Required Input" /
        # "To Required Input" followed by a button displaying the current
        # selection.  Click the button to open the airport picker.
        # Selector: find the heading, then click the next sibling button.
        heading_text = f"{field} Required Input"
        heading = page.get_by_role("heading", name=heading_text, exact=False)

        # The button is inside the next sibling <div>.
        container = heading.locator("..").locator("~ div").first
        button = container.get_by_role("button").first
        # Fallback: if the above doesn't match, try the sibling of the
        # heading's parent.
        try:
            await button.wait_for(state="visible", timeout=3000)
        except PlaywrightError:
            button = heading.locator("..").get_by_role("button").first

        await button.click(timeout=5000)
        await page.wait_for_timeout(500)

        # The airport picker popup should now be visible.
        # Try typing the airport code into any visible search input.
        search_input = page.locator(
            'input[type="text"]:visible, input[type="search"]:visible'
        ).first
        try:
            await search_input.wait_for(state="visible", timeout=5000)
            await search_input.fill(code)
            await page.wait_for_timeout(1000)

            # Click the first matching result that contains the IATA code.
            result_item = page.locator(f"text=/{code}/ >> visible=true").first
            await result_item.click(timeout=5000)
        except PlaywrightError:
            # Fallback: try clicking a list item that contains the code.
            logger.debug(
                "ANA airport search input not found for %s=%s, trying list scan",
                field,
                code,
            )
            item = page.locator(f'[class*="airport"] >> text=/{code}/').first
            try:
                await item.click(timeout=5000)
            except PlaywrightError:
                logger.warning(
                    "ANA: could not select airport %s for %s field",
                    code,
                    field,
                )

        await page.wait_for_timeout(300)

    async def _set_departure_date(self, page: Page, dep_date: date) -> None:
        """Open the date picker and select the departure date."""
        # Click the departure date button.
        date_heading = page.get_by_role(
            "heading",
            name="Departure Date",
            exact=False,
        )
        date_button = (
            date_heading.locator("..").locator("..").get_by_role("button").first
        )

        try:
            await date_button.click(timeout=5000)
        except PlaywrightError:
            # Fallback: click any button that contains a date-like pattern.
            date_button = page.locator('button:has-text("/")').first
            await date_button.click(timeout=5000)

        await page.wait_for_timeout(500)

        # The calendar widget should now be visible.
        # Navigate to the correct month, then click the day.
        formatted = dep_date.strftime("%Y/%-m/%-d")
        # Try clicking a calendar cell with the date.
        day_cell = page.locator(
            f'button:has-text("{dep_date.day}"), '
            f'td:has-text("{dep_date.day}"), '
            f'[data-date="{formatted}"], '
            f'[data-date="{dep_date.isoformat()}"]'
        ).first

        try:
            await day_cell.click(timeout=5000)
        except PlaywrightError:
            logger.warning(
                "ANA: could not click date %s in calendar, trying JS injection",
                dep_date,
            )

        await page.wait_for_timeout(300)

    async def _intercept_search_responses(
        self,
        page: Page,
    ) -> list[dict[str, Any]]:
        """Collect JSON responses from the booking engine after search.

        Waits for responses from ``aswbe.ana.co.jp`` that contain flight data.
        Returns a list of parsed JSON response bodies.
        """
        results: list[dict[str, Any]] = []
        captured_event = asyncio.Event()

        async def _on_response(response: Response) -> None:
            url = response.url
            if _BOOKING_DOMAIN not in url:
                return
            if response.status != 200:
                return
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type and "javascript" not in content_type:
                return
            try:
                body = await response.json()
                if isinstance(body, dict):
                    results.append(body)
                    logger.debug("ANA: captured API response from %s", url)
                    captured_event.set()
            except Exception:
                pass

        page.on("response", _on_response)

        # Wait up to the search timeout for at least one result.
        try:
            await asyncio.wait_for(
                captured_event.wait(),
                timeout=self._timeout,
            )
            # Give a bit more time for additional responses.
            await page.wait_for_timeout(3000)
        except TimeoutError:
            logger.warning("ANA: no API responses captured within timeout")

        return results

    async def _scrape_results_dom(self, page: Page) -> list[dict[str, Any]]:
        """Fallback: scrape flight results from the DOM.

        Parses visible flight result cards on the search results page.
        Returns a list of dicts with flight info extracted from the DOM.
        """
        flights: list[dict[str, Any]] = []

        # Wait for results to appear.
        try:
            await page.wait_for_selector(
                '[class*="flight"], [class*="result"], [class*="itinerary"]',
                timeout=15000,
            )
        except PlaywrightError:
            logger.debug("ANA: no flight result elements found in DOM")
            return flights

        # Extract flight data from result cards via JavaScript.
        raw = await page.evaluate(
            """
            () => {
                const flights = [];
                // Try common patterns for flight result containers.
                const cards = document.querySelectorAll(
                    '[class*="flight-card"], [class*="FlightCard"], '
                    + '[class*="result-item"], [class*="itinerary-item"], '
                    + 'tr[class*="flight"], li[class*="flight"]'
                );
                for (const card of cards) {
                    const text = card.innerText || '';
                    // Extract flight number pattern (NH followed by digits).
                    const fnMatch = text.match(/NH\\s*(\\d{1,4})/);
                    // Extract time pattern (HH:MM).
                    const times = text.match(/(\\d{2}:\\d{2})/g) || [];
                    // Extract price pattern.
                    const priceMatch = text.match(
                        /[¥￥]([\\d,]+)|([\\d,]+)\\s*(?:JPY|KRW|USD)/
                    );
                    flights.push({
                        raw_text: text.substring(0, 500),
                        flight_number: fnMatch ? 'NH' + fnMatch[1] : null,
                        departure_time: times[0] || null,
                        arrival_time: times[1] || null,
                        price: priceMatch ? priceMatch[1] || priceMatch[2] : null,
                    });
                }
                return flights;
            }
            """
        )

        if isinstance(raw, list):
            flights.extend(raw)

        logger.debug("ANA: scraped %d flight cards from DOM", len(flights))
        return flights

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
    ) -> dict[str, Any]:
        """Search for ANA international flights.

        Opens a browser, navigates to ANA's international booking page,
        fills the search form, and returns the flight results.

        Parameters
        ----------
        origin:
            IATA airport code (e.g. ``NRT``, ``HND``, ``TYO``).
        destination:
            IATA airport code (e.g. ``ICN``, ``LAX``, ``SIN``).
        departure_date:
            Date of departure.

        Returns
        -------
        dict
            Contains ``"api_responses"`` (list of raw JSON from booking API)
            and ``"dom_flights"`` (list of flights scraped from the DOM).
        """
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
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                timezone_id="Asia/Tokyo",
            )
            page = await context.new_page()
            await self._setup_page(page)

            try:
                # Step 1: Navigate to international flights page.
                logger.info(
                    "ANA: navigating to %s for %s->%s on %s",
                    _INTL_PAGE,
                    origin,
                    destination,
                    departure_date,
                )
                await page.goto(
                    _INTL_PAGE,
                    wait_until="domcontentloaded",
                    timeout=_NAV_TIMEOUT_MS,
                )

                # Wait for the booking widget to render.
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except PlaywrightError:
                    await page.wait_for_timeout(5000)

                # Verify we are on ana.co.jp.
                if "ana.co.jp" not in page.url:
                    msg = f"ANA: landed on unexpected URL: {page.url}"
                    raise RuntimeError(msg)

                # Step 2: Ensure the "International" tab is selected in the
                # booking widget.
                intl_tab = page.get_by_role("tab", name="International")
                try:
                    await intl_tab.click(timeout=5000)
                    await page.wait_for_timeout(500)
                except PlaywrightError:
                    logger.debug(
                        "ANA: International tab click failed or already selected"
                    )

                # Step 3: Switch to "One Way".
                one_way_btn = page.get_by_role("button", name="One Way")
                try:
                    await one_way_btn.click(timeout=5000)
                    await page.wait_for_timeout(300)
                except PlaywrightError:
                    logger.debug("ANA: One Way button not found, continuing with RT")

                # Step 4: Fill origin airport.
                await self._fill_airport(page, field="From", code=origin)

                # Step 5: Fill destination airport.
                await self._fill_airport(page, field="To", code=destination)

                # Step 6: Set departure date.
                await self._set_departure_date(page, departure_date)

                # Step 7: Start intercepting API responses.
                api_task = asyncio.create_task(self._intercept_search_responses(page))

                # Step 8: Click the Search button.
                search_btn = page.get_by_role("button", name="Search").first
                try:
                    await search_btn.click(timeout=10000)
                except PlaywrightError:
                    # The Search button might be disabled if form is incomplete.
                    logger.warning("ANA: Search button click failed")
                    # Try submitting via keyboard.
                    await page.keyboard.press("Enter")

                # Step 9: Wait for navigation / results.
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=_SEARCH_TIMEOUT_MS
                    )
                except PlaywrightError:
                    await page.wait_for_timeout(10000)

                # Collect API responses.
                api_responses = await api_task

                # Step 10: Scrape DOM as fallback.
                dom_flights = await self._scrape_results_dom(page)

                result: dict[str, Any] = {
                    "api_responses": api_responses,
                    "dom_flights": dom_flights,
                    "final_url": page.url,
                    "origin": origin,
                    "destination": destination,
                    "departure_date": departure_date.isoformat(),
                }

                logger.info(
                    "ANA search %s->%s (%s): %d API responses, %d DOM flights",
                    origin,
                    destination,
                    departure_date,
                    len(api_responses),
                    len(dom_flights),
                )
                return result

            finally:
                await browser.close()

    async def health_check(self) -> bool:
        """Check if ANA's website is reachable."""
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()
                resp = await page.goto(
                    _BASE_URL,
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                await browser.close()
                return resp is not None and resp.ok
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each search opens and closes its own browser."""
