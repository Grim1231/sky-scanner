"""Playwright-based client for Thai Airways flight search.

Thai Airways (TG) uses an OSCI React booking widget on its homepage.
The search flow is:

1. Navigate to ``thaiairways.com/en-kr/`` (homepage has booking widget)
2. Dismiss cookie consent and any login dialogs
3. Fill the one-way search form (origin, destination, departure date)
4. Submit the form and wait for XHR/fetch responses
5. Intercept API responses that contain flight availability data

The OSCI widget renders custom ``<div role="textbox">`` elements for
airport inputs rather than standard ``<input>`` tags.  Clicking the
container div reveals a hidden ``<input>`` for typing, and a React
Bootstrap dropdown shows filtered airport suggestions.

Additionally, the ``/common/calendarPricing/popular-fares`` API endpoint
can be called directly from the browser context to get lowest fares
per route without filling the form.
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

    from playwright.async_api import Page, Response

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.thaiairways.com"
# Homepage has the OSCI booking widget; /en/booking/flight-search.page
# redirects back here anyway.
_SEARCH_PAGE = f"{_BASE_URL}/en-kr/"

# User-Agent string mimicking a real Chrome browser.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# URL substrings that indicate a flight search result response.
_INTERCEPT_PATTERNS = (
    "/common/calendarpricing",
    "/common/flight",
    "/common/booking",
    "/common/availability",
    "/common/airport",
    "/api/",
    "availability",
    "flightsearch",
    "airshopping",
    "offerprice",
    "offers",
    "low-fare",
    "lowfare",
    "popular-fares",
    "calendar",
)


class ThaiAirwaysClient:
    """Async Playwright client for Thai Airways flight search.

    Navigates to the TG booking page, fills the search form, submits
    it, and intercepts API responses containing flight data.

    The OSCI booking widget uses:
    - ``button[aria-label="Book Flight Tab One-way"]`` for trip type
    - ``#input-container-from`` / ``#input-container-to`` (div role=textbox)
    - ``#input-box-from`` / ``#input-box-to`` (real inputs revealed on click)
    - react-datepicker for calendar
    - ``#bookingSearchBtn`` for search
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
                if isinstance(body, (dict, list)) and body:
                    wrapped = body if isinstance(body, dict) else {"items": body}
                    intercepted.append(wrapped)
                    logger.debug(
                        "TG intercepted response from %s (%d bytes)",
                        response.url[:120],
                        len(json.dumps(wrapped)),
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
                # Navigate to the homepage (has the OSCI booking widget).
                await page.goto(
                    _SEARCH_PAGE,
                    wait_until="domcontentloaded",
                    timeout=self._timeout * 1000,
                )

                # Wait for page to stabilise.
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    logger.debug("TG page did not reach networkidle; using fixed delay")
                    await page.wait_for_timeout(5000)

                # Verify we are on the right domain.
                if "thaiairways.com" not in page.url:
                    msg = f"TG navigation failed: landed on {page.url}"
                    raise RuntimeError(msg)

                # Dismiss cookie consent and login dialogs.
                await self._dismiss_dialogs(page)

                # Wait for OSCI widget to load.
                await self._wait_for_osci_widget(page)

                # === Fill the search form ===
                await self._fill_search_form(
                    page, origin, destination, departure_date, cabin_class
                )

                # Click search button.
                await self._click_search(page)

                # Wait for search results (intercepted responses).
                await self._wait_for_results(page, intercepted, timeout_ms=60000)

                # If form-based search yielded nothing, try the direct
                # popular-fares API via page.evaluate() as fallback.
                if not intercepted:
                    logger.info(
                        "TG: form search got no results, trying "
                        "popular-fares API fallback"
                    )
                    api_result = await self._fetch_popular_fares(
                        page, origin, destination
                    )
                    if api_result:
                        intercepted.append(api_result)

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

    # ------------------------------------------------------------------
    # Dialog dismissal
    # ------------------------------------------------------------------

    async def _dismiss_dialogs(self, page: Page) -> None:
        """Dismiss cookie consent banner and login dialogs."""
        # Cookie consent (OneTrust).
        for sel in (
            "#onetrust-accept-btn-handler",
            'button:has-text("Accept All Cookies")',
            'button:has-text("Accept All")',
        ):
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click(timeout=3000)
                    logger.debug("TG: dismissed cookie consent via %s", sel)
                    await page.wait_for_timeout(500)
                    break
            except Exception:
                continue

        # Sign-in / login dialog that may auto-open.
        for sel in (
            'button[aria-label="Close"]',
            ".modal .btn-close",
            'button:has-text("Close")',
        ):
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click(timeout=2000)
                    logger.debug("TG: closed dialog via %s", sel)
                    await page.wait_for_timeout(500)
                    break
            except Exception:
                continue

    # ------------------------------------------------------------------
    # OSCI widget detection
    # ------------------------------------------------------------------

    async def _wait_for_osci_widget(self, page: Page) -> None:
        """Wait until the OSCI booking widget has rendered."""
        try:
            await page.wait_for_selector(
                "#input-container-from, #input-container-to",
                state="visible",
                timeout=15000,
            )
            logger.debug("TG: OSCI booking widget loaded")
        except Exception:
            logger.warning("TG: OSCI widget did not appear within 15s")

    # ------------------------------------------------------------------
    # Form filling
    # ------------------------------------------------------------------

    async def _fill_search_form(
        self,
        page: Page,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str,
    ) -> None:
        """Fill origin, destination, date, and cabin class in the form."""
        # 1. Select one-way trip.
        await self._select_one_way(page)

        # 2. Fill origin airport.
        await self._fill_airport_field(
            page,
            container_id="input-container-from",
            input_id="input-box-from",
            code=origin,
            field_name="origin",
        )

        # 3. Fill destination airport.
        await self._fill_airport_field(
            page,
            container_id="input-container-to",
            input_id="input-box-to",
            code=destination,
            field_name="destination",
        )

        # 4. Select departure date.
        await self._select_date(page, departure_date)

        # 5. Set cabin class if not Economy.
        if cabin_class.upper() not in ("ECONOMY", "PREMIUM_ECONOMY"):
            await self._select_cabin_class(page, cabin_class)

    async def _select_one_way(self, page: Page) -> None:
        """Click the One-way trip type button."""
        sel = 'button[aria-label="Book Flight Tab One-way"]'
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click(timeout=3000)
                logger.debug("TG: selected one-way trip type")
                await page.wait_for_timeout(500)
                return
        except Exception:
            pass

        # Fallback: try text match.
        try:
            btn = page.locator('button:has-text("One-way")').first
            if await btn.is_visible(timeout=2000):
                await btn.click(timeout=3000)
                logger.debug("TG: selected one-way via text match")
                await page.wait_for_timeout(500)
        except Exception:
            logger.warning("TG: could not select one-way trip type")

    async def _fill_airport_field(
        self,
        page: Page,
        *,
        container_id: str,
        input_id: str,
        code: str,
        field_name: str,
    ) -> None:
        """Fill an airport field in the OSCI booking widget.

        The OSCI widget uses a ``<div role="textbox">`` as the visible
        container.  Clicking it reveals a hidden ``<input>`` element for
        typing.  As the user types, a React Bootstrap dropdown filters
        and shows matching airports.  We click the matching dropdown
        item to select the airport.
        """
        # Click the container to open it and reveal the input.
        # Note: the page may have duplicate IDs -- use .first to ensure
        # we target the visible one.
        container = page.locator(f"#{container_id}:visible").first
        try:
            if not await container.is_visible(timeout=3000):
                logger.warning(
                    "TG: %s container #%s not visible", field_name, container_id
                )
                return
            await container.click(timeout=3000)
            await page.wait_for_timeout(500)
        except Exception:
            logger.warning(
                "TG: failed to click %s container #%s",
                field_name,
                container_id,
            )
            return

        # Type the IATA code into the revealed input.
        text_input = page.locator(f"#{input_id}:visible").first
        try:
            await text_input.wait_for(state="visible", timeout=3000)
            # Clear any pre-existing value.
            await text_input.fill("")
            # Type letter by letter so React onChange fires.
            await text_input.type(code, delay=150)
            logger.debug("TG: typed '%s' into %s", code, field_name)
        except Exception:
            logger.warning("TG: could not type into %s input #%s", field_name, input_id)
            return

        # Wait for the autocomplete dropdown to filter.
        await page.wait_for_timeout(1500)

        # Click the matching suggestion in the dropdown.
        # Each airport item is a <div role="button"> inside
        # .dropdown-menu.show that contains a <span class="badge"> with
        # the IATA code.
        await self._click_airport_suggestion(page, code, field_name)

    async def _click_airport_suggestion(
        self, page: Page, code: str, field_name: str
    ) -> None:
        """Click an airport suggestion matching the given IATA code."""
        # Strategy 1: Find the badge span containing the exact code and
        # click its parent button element.
        suggestion_selectors = [
            (
                f'.dropdown-menu.show div[role="button"]'
                f':has(span.badge:has-text("{code}"))'
            ),
            f'.dropdown-menu.show [role="button"]:has-text("{code}")',
            f'.dropdown-menu.show a:has-text("{code}")',
        ]
        for sel in suggestion_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click(timeout=3000)
                    logger.debug(
                        "TG: selected %s airport %s via %s",
                        field_name,
                        code,
                        sel,
                    )
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                continue

        # Strategy 2: Use page.evaluate to find and click the element
        # by iterating over all dropdown buttons.
        try:
            clicked = await page.evaluate(
                """(code) => {
                    const buttons = document.querySelectorAll(
                        '.dropdown-menu.show [role="button"]'
                    );
                    for (const btn of buttons) {
                        const badge = btn.querySelector('.badge');
                        if (badge && badge.textContent.trim() === code) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }""",
                code,
            )
            if clicked:
                logger.debug(
                    "TG: selected %s airport %s via evaluate",
                    field_name,
                    code,
                )
                await page.wait_for_timeout(500)
                return
        except Exception:
            pass

        logger.warning(
            "TG: could not select %s airport suggestion for %s",
            field_name,
            code,
        )

    async def _select_date(self, page: Page, target_date: date) -> None:
        """Open the calendar and select the target date.

        The OSCI widget uses react-datepicker.  Each day cell has
        ``role="option"`` with an ``aria-label`` like
        ``Choose Monday, April 15th, 2026`` (available) or
        ``Not available ...`` (disabled).
        """
        # Open the calendar.
        cal_btn = page.locator('[aria-label="open calendar date selection"]')
        try:
            if await cal_btn.is_visible(timeout=3000):
                await cal_btn.click(timeout=3000)
                await page.wait_for_timeout(1000)
                logger.debug("TG: opened calendar")
            else:
                logger.warning("TG: calendar button not visible")
                return
        except Exception:
            logger.warning("TG: failed to open calendar")
            return

        # Navigate to the correct month.
        # The calendar shows the current month by default.
        # We need to click "Next Month" until we reach the target month.
        target_month = target_date.strftime("%B %Y")  # e.g. "April 2026"
        max_clicks = 12
        for _ in range(max_clicks):
            try:
                header = page.locator(".react-datepicker__current-month")
                current_month = await header.text_content(timeout=2000)
                if current_month and target_month in current_month:
                    break

                # Click "Next Month".
                next_btn = page.locator('button[aria-label="Next Month"]').first
                await next_btn.click(timeout=2000)
                await page.wait_for_timeout(300)
            except Exception:
                break

        # Click the target day.
        # Build a partial aria-label match like "April 15"
        # since the full format varies (e.g. "15th" vs "15").
        day = target_date.day
        month_name = target_date.strftime("%B")

        # Try ordinal suffix variants.
        suffixes = {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd", 31: "st"}
        suffix = suffixes.get(day, "th")
        # aria-label pattern: "Choose <Weekday>, <Month> <Day><suffix>, <Year>"
        label_fragment = f"{month_name} {day}{suffix}"

        day_sel = (
            f'.react-datepicker__day[role="option"][aria-label*="{label_fragment}"]'
        )
        try:
            day_el = page.locator(day_sel).first
            if await day_el.is_visible(timeout=3000):
                aria = await day_el.get_attribute("aria-label")
                if aria and aria.startswith("Choose"):
                    await day_el.click(timeout=3000)
                    logger.debug("TG: selected date %s", target_date)
                    await page.wait_for_timeout(500)
                    return
                logger.warning(
                    "TG: date %s exists but is not available: %s",
                    target_date,
                    aria,
                )
                return
        except Exception:
            pass

        # Fallback: try clicking by evaluating in JS.
        try:
            clicked = await page.evaluate(
                """(args) => {
                    const [monthName, day] = args;
                    const cells = document.querySelectorAll(
                        '.react-datepicker__day[role="option"]'
                    );
                    for (const cell of cells) {
                        const label = cell.getAttribute('aria-label') || '';
                        if (label.startsWith('Choose') &&
                            label.includes(monthName) &&
                            label.includes(String(day))) {
                            cell.click();
                            return true;
                        }
                    }
                    return false;
                }""",
                [month_name, str(day)],
            )
            if clicked:
                logger.debug("TG: selected date %s via evaluate", target_date)
                await page.wait_for_timeout(500)
                return
        except Exception:
            pass

        logger.warning("TG: could not select date %s in calendar", target_date)

    async def _select_cabin_class(self, page: Page, cabin_class: str) -> None:
        """Open passenger/class popup and select the cabin class radio.

        The OSCI widget has two radio options:
        - ``#radio-class-1``: Economy & Premium Economy
        - ``#radio-class-2``: Premium Economy Plus, Business & First
        """
        # Open passenger selection popup.
        try:
            popup_btn = page.locator('[aria-label="open passenger selection"]').first
            if await popup_btn.is_visible(timeout=2000):
                await popup_btn.click(timeout=3000)
                await page.wait_for_timeout(500)
        except Exception:
            logger.warning("TG: could not open passenger/class popup")
            return

        # Select the appropriate radio.
        radio_id = "#radio-class-1"  # Default: Economy
        if cabin_class.upper() in ("BUSINESS", "FIRST", "PREMIUM_ECONOMY"):
            radio_id = "#radio-class-2"

        try:
            radio = page.locator(radio_id).first
            if await radio.is_visible(timeout=2000):
                # Click the label (parent span) since the radio may be
                # hidden and styled via its label.
                label = page.locator(f'label[for="{radio_id[1:]}"]').first
                if await label.is_visible(timeout=1000):
                    await label.click(timeout=2000)
                else:
                    await radio.click(timeout=2000, force=True)
                logger.debug("TG: selected cabin class %s", cabin_class)
        except Exception:
            logger.warning("TG: could not select cabin class %s", cabin_class)

        # Close popup by clicking elsewhere.
        try:
            await page.locator("body").click(position={"x": 10, "y": 10})
            await page.wait_for_timeout(300)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Search submission
    # ------------------------------------------------------------------

    async def _click_search(self, page: Page) -> None:
        """Click the Search Flights button."""
        search_btn = page.locator("#bookingSearchBtn")
        try:
            await search_btn.wait_for(state="visible", timeout=5000)
            is_disabled = await search_btn.is_disabled()
            if is_disabled:
                logger.warning("TG: search button is disabled (form may be incomplete)")
                # Try clicking anyway -- sometimes the button enables
                # after a short delay.
                await page.wait_for_timeout(2000)
                is_disabled = await search_btn.is_disabled()

            if not is_disabled:
                await search_btn.click(timeout=5000)
                logger.debug("TG: clicked Search Flights button")
                return
        except Exception:
            pass

        # Fallback selectors.
        for sel in (
            'button[aria-label="Search Flights Button"]',
            'button:has-text("Search Flights")',
            'button:has-text("Search")',
        ):
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click(timeout=5000)
                    logger.debug("TG: clicked search via %s", sel)
                    return
            except Exception:
                continue

        # Last resort: press Enter.
        await page.keyboard.press("Enter")
        logger.debug("TG: pressed Enter as search fallback")

    # ------------------------------------------------------------------
    # Result waiting
    # ------------------------------------------------------------------

    async def _wait_for_results(
        self,
        page: Page,
        intercepted: list[dict[str, Any]],
        *,
        timeout_ms: int = 60000,
    ) -> None:
        """Wait for flight search results to appear."""
        poll_interval = 2000
        elapsed = 0

        while elapsed < timeout_ms:
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
                'text="Sorry"',
            ]
            for indicator in result_indicators:
                try:
                    el = page.locator(indicator).first
                    if await el.is_visible(timeout=500):
                        await page.wait_for_timeout(2000)
                        return
                except Exception:
                    continue

            await page.wait_for_timeout(poll_interval)
            elapsed += poll_interval

        logger.warning("TG: timed out waiting for results after %dms", timeout_ms)

    # ------------------------------------------------------------------
    # Direct API fallback
    # ------------------------------------------------------------------

    async def _fetch_popular_fares(
        self,
        page: Page,
        origin: str,
        destination: str,
    ) -> dict[str, Any] | None:
        """Call the popular-fares API from the browser context.

        This ``/common/calendarPricing/popular-fares`` endpoint returns
        the cheapest fare per route from EveryMundo/airTRFX data.  It
        needs no authentication beyond a valid browser session.
        """
        try:
            result = await page.evaluate(
                """async (args) => {
                    const [origin, destination] = args;
                    const resp = await fetch(
                        '/common/calendarPricing/popular-fares',
                        {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json',
                                'source': 'website',
                                'hostname': 'https://www.thaiairways.com',
                                'accept-language': 'en-kr',
                            },
                            body: JSON.stringify({
                                journeyType: 'ONE_WAY',
                                origins: [origin],
                            }),
                        }
                    );
                    if (!resp.ok) return null;
                    return await resp.json();
                }""",
                [origin, destination],
            )
            if result and isinstance(result, dict):
                # Tag response so the parser knows its source.
                result["_source"] = "popular-fares"
                result["_origin"] = origin
                result["_destination"] = destination
                logger.info(
                    "TG: popular-fares API returned %d prices",
                    len(result.get("prices", [])),
                )
                return result
        except Exception:
            logger.debug("TG: popular-fares API call failed")
        return None

    async def search_flights_via_evaluate(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
    ) -> dict[str, Any] | None:
        """Alternative: call popular-fares API from a fresh browser context.

        Navigates to the TG homepage to establish a valid session, then
        calls the ``/common/calendarPricing/popular-fares`` endpoint
        directly to get the cheapest fare for the given route.
        """
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox"],
                )
                context = await browser.new_context(user_agent=_USER_AGENT)
                page = await context.new_page()

                try:
                    await page.goto(
                        _SEARCH_PAGE,
                        wait_until="domcontentloaded",
                        timeout=self._timeout * 1000,
                    )
                    await page.wait_for_timeout(3000)

                    result = await self._fetch_popular_fares(page, origin, destination)
                    return result
                finally:
                    await browser.close()
        except Exception:
            logger.exception("TG: evaluate search failed")
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
