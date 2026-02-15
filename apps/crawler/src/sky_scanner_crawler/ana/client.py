"""Playwright-based client for ANA's international flight search.

ANA (All Nippon Airways) uses an SPA booking widget on ana.co.jp that talks
to ``aswbe.ana.co.jp``.  The search API returns 401 when called directly,
and the site is protected by Akamai Bot Manager.

Strategy (L3 -- full browser automation):
1. Launch Playwright Chromium (headless, with anti-detection tweaks).
2. Navigate to ``https://www.ana.co.jp/en/jp/search/international/flight/``.
3. Fill the booking search form via button clicks + airport/date selectors.
4. Click "Search" and intercept the JSON responses from the booking engine
   (``aswbe.ana.co.jp/webapps/...``).
5. Return the raw flight result data.

Alternative fallback: navigate directly to the booking engine URL with
query parameters and scrape the results DOM.

Note: ANA's SPA uses custom React-like components, not standard <select>/<input>.
The booking widget is rendered by ``BookingManager`` JS class loaded from
``booking-asw.bundle.js``.

Key selectors (as of 2026-02):
- Airport buttons: ``.be-overseas-reserve-ticket-{departure,arrival}-airport__button``
- Airport search input: ``input.be-list-with-search__searchbox-input``
- Airport result items: ``li.be-list__item``
- Date button: opens ``be-dialog`` calendar popup
- Calendar day buttons: ``button.be-calendar-month__cell-button`` with
  ``aria-label="YYYY/M/D(DAY)"``
- Calendar confirm: ``button.be-dialog__button--positive``
- Calendar nav: ``button.be-calendar__button--next`` / ``--prev``
- Search submit: ``button.be-overseas-reserve-ticket-submit__button``

The site has ``localselect`` scripts that redirect users to other regional
airline sites based on geolocation.  These must be blocked via route
interception to keep the browser on ``ana.co.jp``.
"""

from __future__ import annotations

import asyncio
import calendar
import logging
from typing import TYPE_CHECKING, Any

from playwright._impl._errors import Error as PlaywrightError
from playwright.async_api import async_playwright

from sky_scanner_crawler.retry import async_retry

if TYPE_CHECKING:
    from datetime import date

    from playwright.async_api import BrowserContext, Page, Response

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.ana.co.jp"
_SEARCH_PAGE = f"{_BASE_URL}/en/jp/search/international/flight/"

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

# Day-of-week abbreviations matching ANA's calendar aria-label format.
_DOW_ABBR = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


def _calendar_aria_label(d: date) -> str:
    """Build the aria-label string ANA uses for calendar day buttons.

    Format: ``YYYY/M/D(DAY)`` -- e.g. ``2026/3/1(SU)``.
    """
    dow = _DOW_ABBR[d.weekday()]
    return f"{d.year}/{d.month}/{d.day}({dow})"


def _calendar_month_heading(d: date) -> str:
    """Build the calendar month heading string.

    Format: ``MonthName YYYY`` -- e.g. ``March 2026``.
    """
    return f"{calendar.month_name[d.month]} {d.year}"


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

    async def _block_redirect_scripts(self, context: BrowserContext) -> None:
        """Placeholder for redirect blocking (currently disabled).

        ANA's ``localselect`` module can redirect to partner airline
        sites (e.g. thaiairways.com), but testing shows the page loads
        normally without explicit blocking.  The ``navigator.webdriver``
        removal in ``_setup_page`` appears sufficient.

        This method is kept as a no-op for future use if redirects
        become an issue.
        """

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
        heading = page.get_by_role(
            "heading", name=f"{field} Required Input", exact=False
        )
        # The button sits inside the container div next to the heading.
        airport_btn = heading.locator("..").locator("button").first

        try:
            await airport_btn.click(timeout=5000)
        except PlaywrightError:
            # Broader fallback: find by BEM class.
            slug = "departure" if field == "From" else "arrival"
            css = f"button.be-overseas-reserve-ticket-{slug}-airport__button"
            airport_btn = page.locator(css).first
            await airport_btn.click(timeout=5000)

        await page.wait_for_timeout(500)

        # The airport picker popup with a search input should now be visible.
        search_input = page.locator(
            "input.be-list-with-search__searchbox-input:visible"
        ).first
        try:
            await search_input.wait_for(state="visible", timeout=5000)
            await search_input.fill(code)
            await page.wait_for_timeout(1500)

            # Click the first matching result item.
            result_item = page.locator("li.be-list__item:visible").first
            await result_item.click(timeout=5000)
        except PlaywrightError:
            logger.warning(
                "ANA: could not select airport %s for %s field",
                code,
                field,
            )

        await page.wait_for_timeout(500)

    async def _set_departure_date(self, page: Page, dep_date: date) -> None:
        """Open the date picker and select the departure date.

        ANA's calendar is a ``be-dialog`` popup showing two months at a
        time.  Each day button has an ``aria-label`` like
        ``2026/3/15(SU)``.  After clicking a day we must confirm with
        the "Confirm Selection" button.
        """
        # The departure date button shows the currently selected date
        # (e.g. "2026/2/15") and sits under the "Departure Date ..." heading.
        heading = page.get_by_role(
            "heading",
            name="Departure Date and Time Slot",
            exact=False,
        )
        date_button = heading.locator("..").locator("button").first

        try:
            await date_button.click(timeout=5000)
        except PlaywrightError:
            # Fallback: click any visible button whose text matches YYYY/M/D.
            date_button = page.locator('button:has-text("/")').first
            await date_button.click(timeout=5000)

        await page.wait_for_timeout(500)

        # The calendar dialog should now be visible.
        # Navigate to the correct month if needed.
        target_heading = _calendar_month_heading(dep_date)
        for _ in range(12):
            # Check if the target month heading is visible.
            month_h = page.locator(f'h5:has-text("{target_heading}")')
            if await month_h.count() > 0 and await month_h.first.is_visible():
                break
            # Click "Next" to advance the calendar.
            next_btn = page.locator("button.be-calendar__button--next:visible").last
            try:
                await next_btn.click(timeout=3000)
                await page.wait_for_timeout(300)
            except PlaywrightError:
                logger.debug("ANA: calendar Next button not clickable")
                break

        # Click the specific day button by its aria-label.
        aria = _calendar_aria_label(dep_date)
        day_btn = page.locator(f'button[aria-label="{aria}"]')

        try:
            await day_btn.click(timeout=5000)
        except PlaywrightError:
            logger.warning(
                "ANA: could not click date %s (aria-label=%s) in calendar",
                dep_date,
                aria,
            )
            # Close the dialog to avoid blocking further interaction.
            close_btn = page.locator("button.be-dialog__button--positive:visible")
            if await close_btn.count() > 0:
                await close_btn.click(timeout=3000)
            return

        await page.wait_for_timeout(300)

        # Confirm the selection.
        confirm_btn = page.locator("button.be-dialog__button--positive:visible")
        try:
            await confirm_btn.click(timeout=5000)
        except PlaywrightError:
            # Sometimes the dialog auto-closes on selection.
            logger.debug(
                "ANA: Confirm Selection button not found, may have auto-closed"
            )

        await page.wait_for_timeout(300)

    async def _click_search(self, page: Page) -> None:
        """Click the Search/submit button.

        The button is disabled until both From and To airports are filled.
        """
        # Primary: use the BEM class.
        search_btn = page.locator(
            "button.be-overseas-reserve-ticket-submit__button"
        ).first
        try:
            await search_btn.wait_for(state="visible", timeout=5000)
            # Verify the button is not disabled.
            is_disabled = await search_btn.is_disabled()
            if is_disabled:
                logger.warning("ANA: Search button is disabled (form incomplete)")
                return
            await search_btn.click(timeout=10000)
            return
        except PlaywrightError:
            pass

        # Fallback: find the Search button by accessible name.  There may be
        # multiple buttons named "Search" on the page (e.g. site-wide search),
        # so prefer the one inside the booking widget.
        search_btn = page.get_by_role("button", name="Search").first
        try:
            await search_btn.click(timeout=10000)
        except PlaywrightError:
            logger.warning("ANA: Search button click failed")
            await page.keyboard.press("Enter")

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

            # Block scripts that redirect the page away from ana.co.jp.
            await self._block_redirect_scripts(context)

            page = await context.new_page()
            await self._setup_page(page)

            try:
                # Step 1: Navigate to the international flight search page.
                logger.info(
                    "ANA: navigating to %s for %s->%s on %s",
                    _SEARCH_PAGE,
                    origin,
                    destination,
                    departure_date,
                )
                await page.goto(
                    _SEARCH_PAGE,
                    wait_until="domcontentloaded",
                    timeout=_NAV_TIMEOUT_MS,
                )

                # Wait for the BookingManager widget to render.
                try:
                    await page.wait_for_selector(
                        "button.be-overseas-reserve-ticket-submit__button",
                        state="attached",
                        timeout=15000,
                    )
                except PlaywrightError:
                    # Fall back to a timed wait.
                    await page.wait_for_timeout(8000)

                # Verify we are still on ana.co.jp (redirect scripts may
                # have fired before route blocking took effect).
                if "ana.co.jp" not in page.url:
                    msg = f"ANA: landed on unexpected URL: {page.url}"
                    raise RuntimeError(msg)

                # Step 2: Switch to "One Way".
                one_way_btn = page.get_by_role("button", name="One Way")
                try:
                    await one_way_btn.click(timeout=5000)
                    await page.wait_for_timeout(300)
                except PlaywrightError:
                    logger.debug(
                        "ANA: One Way button not found, continuing with Round Trip"
                    )

                # Step 3: Fill origin airport.
                await self._fill_airport(page, field="From", code=origin)

                # Step 4: Fill destination airport.
                await self._fill_airport(page, field="To", code=destination)

                # Step 5: Set departure date.
                await self._set_departure_date(page, departure_date)

                # Step 6: Start intercepting API responses.
                api_task = asyncio.create_task(self._intercept_search_responses(page))

                # Step 7: Click the Search button.
                await self._click_search(page)

                # Step 8: Wait for navigation / results.
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=_SEARCH_TIMEOUT_MS
                    )
                except PlaywrightError:
                    await page.wait_for_timeout(10000)

                # Collect API responses.
                api_responses = await api_task

                # Step 9: Scrape DOM as fallback.
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
