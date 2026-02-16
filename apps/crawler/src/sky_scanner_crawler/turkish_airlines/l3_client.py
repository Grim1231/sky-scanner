"""Turkish Airlines L3 Playwright client with response interception.

Bypasses Akamai DS-30037 bot detection on POST endpoints by using a real
browser to fill the TK booking form and intercept the internal API
responses.

The TK SPA at ``turkishairlines.com/en-int/flights/booking/`` is a
React/Next.js application that internally calls:

- ``/api/v1/availability/flight-matrix`` -- full flight search results
- ``/api/v1/availability/cheapest-prices`` -- daily price calendar

When the SPA makes these calls from a real browser session, Akamai allows
them because the browser has a valid ``_abck`` cookie bound to a genuine
TLS fingerprint.

L3 Strategy (response interception):
1. Launch system Chrome (``channel="chrome"``) with anti-detection flags
2. Navigate to ``turkishairlines.com/en-int/flights/booking/``
3. Dismiss the cookie consent overlay (pointer-events workaround)
4. Fill the form: one-way, origin, destination
5. The calendar auto-opens after destination -- navigate and select date
6. Set up response interception for ``/api/v1/availability/*``
7. Click the search button
8. Capture and return the intercepted JSON response
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from playwright._impl._errors import Error as PlaywrightError
from playwright.async_api import Response, async_playwright

from sky_scanner_crawler.retry import async_retry

if TYPE_CHECKING:
    from datetime import date

    from playwright.async_api import Page

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.turkishairlines.com"
_BOOKING_URL = f"{_BASE_URL}/en-int/flights/booking/"

# Cabin class mapping: our CabinClass enum values -> TK form text.
_CABIN_FORM_MAP: dict[str, str] = {
    "ECONOMY": "Economy",
    "PREMIUM_ECONOMY": "Economy",  # TK has no premium economy
    "BUSINESS": "Business",
    "FIRST": "Business",  # TK has no first class
}

# User agent string mimicking a real Chrome browser.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Timeouts (milliseconds).
_PAGE_LOAD_TIMEOUT_MS = 60_000
_SEARCH_RESULT_TIMEOUT_MS = 90_000
_AUTOCOMPLETE_DELAY_MS = 2000

# URL substrings that indicate a flight search API response.
_INTERCEPT_PATTERNS = (
    "/api/v1/availability/flight-matrix",
    "/api/v1/availability/cheapest-prices",
)

# JavaScript injected before navigation to remove webdriver flag and
# prevent automation detection.
_STEALTH_SCRIPT = """
(() => {
  // Remove webdriver flag.
  try {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
  } catch {}
  // Mask chrome.runtime (headless indicator).
  try {
    window.chrome = window.chrome || {};
    window.chrome.runtime = window.chrome.runtime || {};
  } catch {}
  // Override permissions query for notifications (Akamai checks this).
  try {
    const origQuery = Notification.permission;
    Object.defineProperty(Notification, 'permission', {get: () => 'default'});
  } catch {}
  // Override plugins length (headless has 0).
  try {
    Object.defineProperty(navigator, 'plugins', {
      get: () => [1, 2, 3, 4, 5],
    });
  } catch {}
  // Override languages (headless may have empty).
  try {
    Object.defineProperty(navigator, 'languages', {
      get: () => ['en-US', 'en'],
    });
  } catch {}
})();
"""


class TurkishAirlinesPlaywrightClient:
    """L3 Playwright client for Turkish Airlines flight search.

    Automates the TK booking form and intercepts the internal API
    responses that the React SPA fires when search results load.

    Each ``search_flights`` call launches a fresh browser session, fills
    the form, and captures the API response.  No cookies or sessions are
    reused across calls.
    """

    def __init__(self, *, timeout: int = 60) -> None:
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Cookie banner dismissal
    # ------------------------------------------------------------------

    @staticmethod
    async def _dismiss_cookie_banner(page: Page) -> None:
        """Dismiss the TK cookie consent banner and overlay.

        TK renders a full-viewport overlay div
        (``hm__style_overlay__*``, ``position: fixed``,
        ``pointer-events: auto``, ``z-index: 1000``) that intercepts
        all pointer events.

        **Important**: We must NOT remove the overlay from the DOM
        because it is part of the React component tree.  Removing it
        crashes the React app ("Application error: a client-side
        exception has occurred").  Instead we set
        ``pointer-events: none`` on the overlay so clicks pass through,
        then programmatically click the accept button.
        """
        try:
            await page.evaluate(
                """
                () => {
                    // Disable pointer events on blocking overlays.
                    document.querySelectorAll(
                        '[class*="overlay"]'
                    ).forEach(el => {
                        const s = getComputedStyle(el);
                        if (s.position === 'fixed'
                            && parseInt(s.zIndex) > 100) {
                            el.style.pointerEvents = 'none';
                        }
                    });
                    // Click accept cookies button.
                    const btn = document.getElementById(
                        'allowCookiesButton'
                    );
                    if (btn) btn.click();
                }
                """
            )
            logger.debug("TK L3: disabled overlay + accepted cookies")
            await page.wait_for_timeout(2000)
            return
        except Exception:
            pass

        # Fallback: try clicking buttons with force option.
        for sel in [
            "#allowCookiesButton",
            "#onetrust-accept-btn-handler",
            'button:has-text("accept all cookies")',
            'button:has-text("Accept")',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click(force=True, timeout=3000)
                    logger.debug(
                        "TK L3: cookie via %s (force)",
                        sel,
                    )
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                continue

    # ------------------------------------------------------------------
    # Form interaction helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _select_one_way(page: Page) -> None:
        """Select the one-way trip type.

        The TK React booking widget uses ``<span>`` elements with
        ``role="button"`` and IDs like ``one-way``, ``round-trip``.
        The active trip type has ``aria-current="true"``.
        """
        for sel in [
            "#one-way",
            "span#one-way",
            'span:has-text("One way")',
            '[role="button"]:has-text("One way")',
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click(timeout=3000)
                    logger.debug(
                        "TK L3: selected one-way via %s",
                        sel,
                    )
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                continue

        logger.debug("TK L3: could not find one-way selector")
        await page.wait_for_timeout(300)

    @staticmethod
    async def _fill_airport(
        page: Page,
        iata_code: str,
        field_name: str,
        *,
        field_index: int = 0,
    ) -> None:
        """Fill an airport field in the TK booking widget.

        The TK React widget uses ``<input role="combobox">`` with
        IDs ``fromPort`` (origin) and ``toPort`` (destination).
        Typing triggers an ARIA listbox with option elements.

        Parameters
        ----------
        page:
            Playwright page.
        iata_code:
            IATA airport code (e.g. ``IST``).
        field_name:
            ``"origin"`` or ``"destination"``.
        field_index:
            0 for origin, 1 for destination.
        """
        port_id = "fromPort" if field_index == 0 else "toPort"
        input_selectors = [
            f"#{port_id}",
            'input[aria-label="From"]'
            if field_index == 0
            else 'input[aria-label="To"]',
        ]

        input_el = None
        for sel in input_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    input_el = el
                    logger.debug(
                        "TK L3: found %s via %s",
                        field_name,
                        sel,
                    )
                    break
            except Exception:
                continue

        if input_el is None:
            msg = f"TK L3: could not find {field_name} input"
            raise RuntimeError(msg)

        # Click, clear, and type the IATA code.
        await input_el.click(timeout=5000)
        await page.wait_for_timeout(300)
        await input_el.fill("")
        await page.wait_for_timeout(200)
        await input_el.press_sequentially(iata_code, delay=100)
        logger.debug(
            "TK L3: typed '%s' into %s",
            iata_code,
            field_name,
        )

        # Wait for autocomplete suggestions.
        await page.wait_for_timeout(_AUTOCOMPLETE_DELAY_MS)

        # Try clicking the matching suggestion in the listbox.
        suggestion_selectors = [
            f'[role="option"]:has-text("{iata_code}")',
            f'li:has-text("{iata_code}")',
        ]

        for sel in suggestion_selectors:
            try:
                option = page.locator(sel).first
                if await option.is_visible(timeout=2000):
                    await option.click(timeout=3000)
                    logger.debug(
                        "TK L3: selected %s via %s",
                        field_name,
                        sel,
                    )
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                continue

        # Fallback: click first visible option.
        try:
            opt = page.locator('[role="option"]').first
            if await opt.is_visible(timeout=2000):
                await opt.click(timeout=3000)
                logger.debug(
                    "TK L3: first option for %s",
                    field_name,
                )
                await page.wait_for_timeout(500)
                return
        except Exception:
            pass

        # Last resort: press Enter.
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(500)
        logger.debug("TK L3: Enter to confirm %s", field_name)

    @staticmethod
    async def _select_date(page: Page, departure_date: date) -> None:
        """Select the departure date from the TK calendar picker.

        The TK React calendar (``react-calendar``) auto-opens when the
        destination airport is selected (the SPA advances focus to the
        date picker, setting ``aria-expanded="true"``).

        **Important**: Do NOT click the date picker trigger to open it.
        If ``aria-expanded`` is already ``"true"``, clicking the trigger
        will TOGGLE it closed.  Instead, check if the calendar is
        already visible and only open it if it is not.

        Calendar tiles are ``<button class="react-calendar__tile">``
        containing ``<abbr aria-label="Month Day DayOfWeek, Year">``
        (e.g. ``"March 18 Wednesday, 2026"``).

        The calendar uses ``react-calendar--doubleView`` (shows two
        months side by side).  Navigation uses the class
        ``react-calendar__navigation__next-button``.
        """
        day = departure_date.day
        month_name = departure_date.strftime("%B")
        day_of_week = departure_date.strftime("%A")
        year = departure_date.year

        # Build the abbr aria-label for the target date.
        # Format: "March 18 Wednesday, 2026"
        target_abbr = f"{month_name} {day} {day_of_week}, {year}"
        target_month = f"{month_name} {year}"

        # Check if calendar is already open (auto-opens after dest).
        cal_visible = await page.evaluate(
            "() => !!document.querySelector('.react-calendar')"
        )

        if not cal_visible:
            # Open the calendar via focus + Enter on the datepicker
            # container (NOT a click, which may toggle it closed).
            logger.debug("TK L3: calendar not auto-opened, opening")
            dp = page.locator('[class*="oneway-container"][role="button"]')
            try:
                # If aria-expanded is true but calendar isn't in DOM,
                # click to close then reopen.
                aria = await dp.get_attribute(
                    "aria-expanded",
                    timeout=2000,
                )
                if aria == "true":
                    await dp.click(timeout=3000)
                    await page.wait_for_timeout(500)
                await dp.focus()
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(2000)
            except Exception:
                # Last resort: direct click.
                try:
                    await dp.click(timeout=3000)
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass

        # Navigate to the target month (double-view shows 2 months).
        for _attempt in range(8):
            labels = await page.evaluate(
                """
                () => {
                    const ls = document.querySelectorAll(
                        '.react-calendar__navigation__label'
                    );
                    return Array.from(ls).map(
                        l => l.textContent.trim()
                    );
                }
                """
            )
            label_text = " ".join(labels)
            if target_month in label_text:
                logger.debug(
                    "TK L3: calendar at target month: %s",
                    label_text,
                )
                break

            # Click the next-month navigation arrow.
            next_btn = page.locator(".react-calendar__navigation__next-button").first
            try:
                if await next_btn.is_visible(timeout=2000):
                    await next_btn.click(timeout=3000)
                    await page.wait_for_timeout(500)
                else:
                    logger.debug("TK L3: no next-month button")
                    break
            except Exception:
                break

        # Click the target date tile using the abbr aria-label.
        tile_sel = f'.react-calendar__tile:has(abbr[aria-label="{target_abbr}"])'
        tile = page.locator(tile_sel).first
        try:
            if await tile.is_visible(timeout=3000):
                await tile.click(timeout=3000)
                logger.debug(
                    "TK L3: selected date '%s'",
                    target_abbr,
                )
                await page.wait_for_timeout(1000)
                return
        except Exception:
            pass

        # Fallback: partial match on month + day.
        logger.debug(
            "TK L3: exact tile not found, trying partial match",
        )
        partial_sel = (
            f'.react-calendar__tile:has(abbr[aria-label*="{month_name} {day}"])'
        )
        partial = page.locator(partial_sel).first
        try:
            if await partial.is_visible(timeout=2000):
                await partial.click(timeout=3000)
                logger.debug("TK L3: date via partial match")
                await page.wait_for_timeout(1000)
                return
        except Exception:
            pass

        logger.warning(
            "TK L3: could not select date %s in calendar",
            departure_date,
        )

    @staticmethod
    async def _select_cabin_class(page: Page, cabin_class: str) -> None:
        """Set the cabin class in the TK booking form."""
        form_value = _CABIN_FORM_MAP.get(cabin_class, "Economy")
        if form_value == "Economy":
            return  # Economy is the default.

        for sel in [
            f'[role="radio"]:has-text("{form_value}")',
            f'label:has-text("{form_value}")',
            f'button:has-text("{form_value}")',
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click(timeout=3000)
                    logger.debug(
                        "TK L3: cabin class %s via %s",
                        form_value,
                        sel,
                    )
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                continue

        logger.debug(
            "TK L3: could not set cabin class to %s",
            form_value,
        )

    @staticmethod
    async def _click_search(page: Page) -> None:
        """Click the search/submit button on the booking form."""
        for sel in [
            'button:has-text("Search flights")',
            'button:has-text("Search")',
            'button[type="submit"]:has-text("Search")',
            'button:has-text("Ara")',  # Turkish
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click(timeout=5000)
                    logger.debug(
                        "TK L3: clicked search via %s",
                        sel,
                    )
                    return
            except Exception:
                continue

        # Fallback: press Enter.
        await page.keyboard.press("Enter")
        logger.debug("TK L3: Enter as search fallback")

    # ------------------------------------------------------------------
    # Response interception
    # ------------------------------------------------------------------

    @staticmethod
    async def _setup_interception(
        page: Page,
    ) -> tuple[dict[str, Any], asyncio.Event]:
        """Register response interception for TK API responses.

        Returns a tuple of (captured_data_dict, asyncio_event).
        The event is set when the first matching response is captured.
        """
        captured: dict[str, Any] = {}
        capture_event = asyncio.Event()

        async def _on_response(response: Response) -> None:
            if captured:
                return  # Already captured.
            url = response.url
            if not any(p in url for p in _INTERCEPT_PATTERNS):
                return
            if response.status != 200:
                logger.debug(
                    "TK L3: non-200 API: %s %d",
                    url,
                    response.status,
                )
                return

            try:
                body = await response.json()
            except Exception:
                return

            if not isinstance(body, dict):
                return

            # The TK API returns {success: bool, data: {...}}.
            if body.get("data") is not None:
                captured.update(body)
                capture_event.set()
                ep = "flight-matrix" if "flight-matrix" in url else "cheapest-prices"
                logger.debug(
                    "TK L3: intercepted %s response",
                    ep,
                )

        page.on("response", _on_response)
        return captured, capture_event

    # ------------------------------------------------------------------
    # Public search method
    # ------------------------------------------------------------------

    @async_retry(
        max_retries=1,
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
    ) -> dict[str, Any]:
        """Search flights via Playwright form automation.

        Navigates to the TK booking page, fills the form, clicks search,
        and intercepts the API response.

        Parameters
        ----------
        origin:
            IATA airport code (e.g. ``IST``).
        destination:
            IATA airport code (e.g. ``ICN``).
        departure_date:
            Departure date.
        cabin_class:
            Cabin class string (``ECONOMY``, ``BUSINESS``, etc.).
        adults:
            Number of adult passengers (currently always 1).

        Returns
        -------
        dict
            Raw JSON response from the TK API containing flight data.
        """
        async with async_playwright() as pw:
            # Use locally installed Chrome (channel="chrome") instead
            # of Playwright's bundled Chromium.  Akamai blocks the
            # bundled Chromium via HTTP/2 TLS fingerprinting
            # (ERR_HTTP2_PROTOCOL_ERROR).  System Chrome has a genuine
            # TLS fingerprint that Akamai trusts.
            try:
                browser = await pw.chromium.launch(
                    headless=True,
                    channel="chrome",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
            except Exception:
                # Fallback to bundled Chromium if Chrome not installed.
                logger.debug(
                    "TK L3: system Chrome not found, "
                    "using bundled Chromium (may be blocked)",
                )
                browser = await pw.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
            context = await browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1440, "height": 900},
                locale="en-US",
            )

            page = await context.new_page()

            # Inject stealth script before navigation.
            await page.add_init_script(_STEALTH_SCRIPT)

            try:
                # 1. Set up response interception BEFORE navigation.
                captured, capture_event = await self._setup_interception(page)

                # 2. Navigate to the booking page.
                logger.debug(
                    "TK L3: navigating to %s",
                    _BOOKING_URL,
                )
                await page.goto(
                    _BOOKING_URL,
                    wait_until="domcontentloaded",
                    timeout=_PAGE_LOAD_TIMEOUT_MS,
                )
                # Wait for Akamai sensor + React widget init.
                await page.wait_for_timeout(5000)

                # 3. Verify we're on the TK domain.
                if "turkishairlines.com" not in page.url:
                    msg = f"TK L3: redirected away: {page.url}"
                    raise RuntimeError(msg)

                # 4. Dismiss cookie consent overlay.
                await self._dismiss_cookie_banner(page)

                # 5. Select one-way trip.
                await self._select_one_way(page)

                # 6. Fill origin airport.
                await self._fill_airport(
                    page,
                    origin,
                    "origin",
                    field_index=0,
                )
                await page.wait_for_timeout(500)

                # 7. Fill destination airport.
                #    After this, the calendar auto-opens.
                await self._fill_airport(
                    page,
                    destination,
                    "destination",
                    field_index=1,
                )
                await page.wait_for_timeout(1500)

                # 8. Select departure date (calendar already open).
                await self._select_date(page, departure_date)

                # 9. Select cabin class (if non-Economy).
                await self._select_cabin_class(page, cabin_class)

                # 10. Click the search button.
                await self._click_search(page)

                # 11. Wait for the intercepted API response.
                logger.debug("TK L3: waiting for API response...")
                try:
                    await asyncio.wait_for(
                        capture_event.wait(),
                        timeout=_SEARCH_RESULT_TIMEOUT_MS / 1000,
                    )
                except TimeoutError:
                    msg = "TK L3: timed out waiting for API response"
                    raise RuntimeError(msg) from None

            finally:
                await browser.close()

        # Validate the response.
        if not captured:
            msg = "TK L3: no API response was captured"
            raise RuntimeError(msg)

        if not captured.get("success", False):
            errors = captured.get("statusDetailList") or []
            codes = [e.get("code", "") for e in errors]
            msgs = [e.get("translatedMessage", "") for e in errors]
            error_summary = "; ".join(
                f"{c}: {m}" for c, m in zip(codes, msgs, strict=True) if c
            )
            if error_summary:
                msg = f"TK L3 API error: {error_summary}"
                raise RuntimeError(msg)

        logger.info(
            "TK L3: search %s->%s (%s) captured API response",
            origin,
            destination,
            departure_date,
        )
        return captured

    async def health_check(self) -> bool:
        """Check if the TK booking page is reachable."""
        try:
            async with async_playwright() as pw:
                try:
                    browser = await pw.chromium.launch(
                        headless=True,
                        channel="chrome",
                        args=["--no-sandbox"],
                    )
                except Exception:
                    browser = await pw.chromium.launch(
                        headless=True,
                        args=["--no-sandbox"],
                    )
                page = await browser.new_page()
                resp = await page.goto(
                    f"{_BASE_URL}/",
                    wait_until="commit",
                    timeout=15000,
                )
                await browser.close()
                return resp is not None and resp.ok
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each search opens and closes its own browser."""
