"""Playwright-based client for Qatar Airways flight search.

Qatar Airways (QR) uses an Angular SPA backed by the ``qoreservices``
API (``qoreservices.qatarairways.com``).  The search flow is:

1. Navigate to ``qatarairways.com/en/booking.html``
2. Fill the search form (from, to, date, passengers)
3. Submit the form
4. Intercept JSON responses from ``qoreservices.qatarairways.com``
   which contain flight offers, pricing, and availability data

The site is protected by Akamai Bot Manager.  Using a real Chromium
browser (via Playwright) with stealth settings solves the challenge.

Key ``qoreservices`` endpoints observed:

- ``/api/offer/search`` -- main flight search results
- ``/api/offer/calendar`` -- lowest fare calendar
- ``/api/offer/price`` -- pricing for a specific offer
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

_BASE_URL = "https://www.qatarairways.com"
_BOOKING_PAGE = f"{_BASE_URL}/en/booking.html"

# The qoreservices API domain.
_QORE_DOMAIN = "qoreservices.qatarairways.com"

# User-Agent string mimicking a real Chrome browser.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# URL substrings that indicate a flight search result response.
_INTERCEPT_PATTERNS = (
    _QORE_DOMAIN,
    "qoreservices",
    "/api/offer/",
    "/api/flight/",
    "/api/search/",
    "/api/calendar/",
    "flightoffers",
    "FlightOffers",
    "availability",
    "offer/search",
    "offer/calendar",
    "offer/price",
)


class QatarAirwaysClient:
    """Async Playwright client for Qatar Airways flight search.

    Navigates to the QR booking page, fills the search form, submits
    it, and intercepts API responses from ``qoreservices.qatarairways.com``
    containing flight offer data.
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
        """Search flights on qatarairways.com and return intercepted API responses.

        Parameters
        ----------
        origin:
            IATA airport code (e.g. ``ICN``).
        destination:
            IATA airport code (e.g. ``DOH``).
        departure_date:
            Date of departure.
        cabin_class:
            Cabin class string (``ECONOMY``, ``BUSINESS``, ``FIRST``).
        adults:
            Number of adult passengers.

        Returns
        -------
        list[dict]
            List of raw JSON response dicts intercepted from qoreservices.
        """
        intercepted: list[dict[str, Any]] = []
        date_str = departure_date.strftime("%d %b %Y")  # QR format.

        async def _on_response(response: Response) -> None:
            """Capture JSON responses from qoreservices endpoints."""
            url = response.url.lower()
            if not any(p.lower() in url for p in _INTERCEPT_PATTERNS):
                return

            content_type = response.headers.get("content-type", "")
            if "json" not in content_type and "javascript" not in content_type:
                return

            try:
                body = await response.json()
                if isinstance(body, dict) and body:
                    intercepted.append(body)
                    logger.debug(
                        "QR intercepted response from %s (%d bytes)",
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
                # Navigate to the booking page.
                await page.goto(
                    _BOOKING_PAGE,
                    wait_until="domcontentloaded",
                    timeout=self._timeout * 1000,
                )

                # Wait for page to stabilise (Akamai challenge may run).
                try:
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    logger.debug("QR page did not reach networkidle; using fixed delay")
                    await page.wait_for_timeout(8000)

                # Handle cookie consent banner if present.
                consent_selectors = [
                    'button:has-text("Accept")',
                    'button:has-text("OK")',
                    'button:has-text("Got it")',
                    "#onetrust-accept-btn-handler",
                    ".cookie-accept",
                ]
                for sel in consent_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            await el.click(timeout=3000)
                            logger.debug("QR: dismissed consent via %s", sel)
                            break
                    except Exception:
                        continue

                # Verify we are on the right domain.
                if "qatarairways.com" not in page.url:
                    msg = f"QR navigation failed: landed on {page.url}"
                    raise RuntimeError(msg)

                # === Fill the search form ===
                # Qatar Airways uses an Angular SPA for booking.

                # Select one-way trip.
                ow_selectors = [
                    'input[value="oneWay"]',
                    'label:has-text("One Way")',
                    'label:has-text("One way")',
                    '[data-trip-type="OW"]',
                    'input[name="tripType"][value="O"]',
                    "#oneWay",
                    'label[for="oneWay"]',
                    'button:has-text("One way")',
                    '[data-testid="one-way"]',
                ]
                for sel in ow_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            await el.click(timeout=3000)
                            logger.debug("QR: clicked one-way selector %s", sel)
                            break
                    except Exception:
                        continue

                # Fill origin field.
                origin_selectors = [
                    'input[placeholder*="From"]',
                    'input[placeholder*="from"]',
                    'input[aria-label*="From"]',
                    'input[aria-label*="Origin"]',
                    'input[aria-label*="Departing from"]',
                    'input[name="origin"]',
                    'input[id*="origin"]',
                    'input[data-testid*="origin"]',
                    'input[formcontrolname="from"]',
                    "#fromCity",
                    ".origin-input input",
                ]
                await self._fill_airport_field(page, origin_selectors, origin, "origin")

                await page.wait_for_timeout(500)

                # Fill destination field.
                dest_selectors = [
                    'input[placeholder*="To"]',
                    'input[placeholder*="to"]',
                    'input[aria-label*="To"]',
                    'input[aria-label*="Destination"]',
                    'input[aria-label*="Flying to"]',
                    'input[name="destination"]',
                    'input[id*="destination"]',
                    'input[data-testid*="destination"]',
                    'input[formcontrolname="to"]',
                    "#toCity",
                    ".destination-input input",
                ]
                await self._fill_airport_field(
                    page, dest_selectors, destination, "destination"
                )

                await page.wait_for_timeout(500)

                # Fill departure date.
                date_selectors = [
                    'input[placeholder*="Depart"]',
                    'input[placeholder*="depart"]',
                    'input[aria-label*="Depart"]',
                    'input[aria-label*="Departure"]',
                    'input[name="departureDate"]',
                    'input[formcontrolname="departureDate"]',
                    'input[id*="depart"]',
                    'input[data-testid*="depart"]',
                    "#departDate",
                    ".departure-date input",
                ]
                for sel in date_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            await el.click(timeout=3000)
                            # Clear existing value.
                            await el.fill("", timeout=1000)
                            await el.type(date_str, delay=50, timeout=5000)
                            logger.debug("QR: filled departure date via %s", sel)
                            # Press Enter or click away to confirm.
                            await page.keyboard.press("Enter")
                            await page.wait_for_timeout(1000)
                            break
                    except Exception:
                        continue

                # Try to set cabin class if UI allows.
                cabin_selectors = [
                    'select[name="cabinClass"]',
                    'select[formcontrolname="cabinClass"]',
                    "#cabinClass",
                    'select[aria-label*="class"]',
                    'button:has-text("Economy")',
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
                            tag = await el.evaluate("el => el.tagName")
                            if tag == "SELECT":
                                await el.select_option(value=cabin_val, timeout=3000)
                            else:
                                await el.click(timeout=3000)
                                # Look for cabin option in dropdown.
                                cabin_option = page.locator(
                                    f'li:has-text("{cabin_class.title()}")'
                                ).first
                                if await cabin_option.is_visible(timeout=2000):
                                    await cabin_option.click(timeout=3000)
                            logger.debug("QR: selected cabin via %s", sel)
                            break
                    except Exception:
                        continue

                # Click search button.
                search_selectors = [
                    'button[type="submit"]',
                    'button:has-text("Search")',
                    'button:has-text("search")',
                    'button:has-text("Search flights")',
                    'button:has-text("Search Flights")',
                    "#searchFlight",
                    'button[data-testid*="search"]',
                    ".search-button",
                    'input[type="submit"]',
                    'a:has-text("Search")',
                ]
                clicked = False
                for sel in search_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=2000):
                            await el.click(timeout=5000)
                            logger.debug("QR: clicked search via %s", sel)
                            clicked = True
                            break
                    except Exception:
                        continue

                if not clicked:
                    # Fallback: press Enter on the page.
                    await page.keyboard.press("Enter")
                    logger.debug("QR: pressed Enter as search fallback")

                # Wait for search results (intercepted responses from qoreservices).
                await self._wait_for_results(page, intercepted, timeout_ms=60000)

            finally:
                await browser.close()

        if not intercepted:
            logger.warning(
                "QR: no API responses intercepted for %s->%s on %s",
                origin,
                destination,
                departure_date,
            )

        logger.info(
            "QR: intercepted %d API responses for %s->%s on %s",
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
                    await page.wait_for_timeout(2000)
                    # Try to click the first suggestion.
                    suggestion_selectors = [
                        f'li:has-text("{code}")',
                        f'[data-value="{code}"]',
                        f'span:has-text("{code}")',
                        ".autocomplete-item:first-child",
                        ".suggestion-item:first-child",
                        "ul.dropdown li:first-child",
                        ".search-results li:first-child",
                        ".airport-list li:first-child",
                        f'option[value="{code}"]',
                        # QR Angular SPA often uses mat-option.
                        "mat-option:first-child",
                        ".cdk-overlay-pane li:first-child",
                    ]
                    for sug_sel in suggestion_selectors:
                        try:
                            sug = page.locator(sug_sel).first
                            if await sug.is_visible(timeout=2000):
                                await sug.click(timeout=3000)
                                break
                        except Exception:
                            continue
                    logger.debug("QR: filled %s via %s", field_name, sel)
                    return
            except Exception:
                continue

        logger.warning("QR: could not fill %s field with code %s", field_name, code)

    async def _wait_for_results(
        self,
        page: Any,
        intercepted: list[dict[str, Any]],
        *,
        timeout_ms: int = 60000,
    ) -> None:
        """Wait for flight search results to appear.

        Polls for intercepted responses from qoreservices or DOM changes
        indicating search results have loaded.
        """
        poll_interval = 2000
        elapsed = 0

        while elapsed < timeout_ms:
            # Check if we have intercepted meaningful qoreservices responses.
            qore_responses = [
                r
                for r in intercepted
                if any(
                    k in str(r).lower()
                    for k in ("offer", "flight", "fare", "segment", "price")
                )
            ]
            if qore_responses:
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
                ".flight-card",
                ".offer-card",
                ".no-flights",
                ".no-results",
                'text="No flights"',
                'text="no flights"',
                'text="No results"',
                # QR-specific selectors.
                "app-flight-list",
                "app-flight-card",
                ".flight-details",
                ".fare-selection",
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
            "QR: timed out waiting for search results after %dms", timeout_ms
        )

    async def search_via_direct_url(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
    ) -> list[dict[str, Any]]:
        """Alternative: navigate directly to the search results URL.

        Qatar Airways supports deep-linking to search results via URL
        parameters.  This bypasses the form-filling step.

        URL format::

            https://www.qatarairways.com/en/booking/flights.html
            ?widget=QR&searchType=F&addTax498=1&flexibleDate=Off
            &bookingClass=E&tripType=O&from=ICN&to=DOH
            &departing=2026-04-15&adults=1&children=0&infants=0
            &teenager=0&ofw=0&promoCode=&currency=KRW
        """
        intercepted: list[dict[str, Any]] = []
        date_iso = departure_date.isoformat()

        cabin_code_map = {
            "ECONOMY": "E",
            "PREMIUM_ECONOMY": "E",
            "BUSINESS": "J",
            "FIRST": "F",
        }
        booking_class = cabin_code_map.get(cabin_class, "E")

        search_url = (
            f"{_BASE_URL}/en/booking/flights.html"
            f"?widget=QR&searchType=F&addTax498=1&flexibleDate=Off"
            f"&bookingClass={booking_class}&tripType=O"
            f"&from={origin}&to={destination}"
            f"&departing={date_iso}"
            f"&adults={adults}&children=0&infants=0"
            f"&teenager=0&ofw=0&promoCode=&currency=KRW"
        )

        async def _on_response(response: Response) -> None:
            url = response.url.lower()
            if not any(p.lower() in url for p in _INTERCEPT_PATTERNS):
                return

            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return

            try:
                body = await response.json()
                if isinstance(body, dict) and body:
                    intercepted.append(body)
                    logger.debug(
                        "QR intercepted (direct URL) from %s",
                        response.url[:120],
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

            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            page.on("response", _on_response)

            try:
                await page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=self._timeout * 1000,
                )

                # Wait for qoreservices API responses.
                await self._wait_for_results(page, intercepted, timeout_ms=60000)

            finally:
                await browser.close()

        logger.info(
            "QR (direct URL): intercepted %d responses for %s->%s on %s",
            len(intercepted),
            origin,
            destination,
            departure_date,
        )
        return intercepted

    async def health_check(self) -> bool:
        """Check if the Qatar Airways website is reachable."""
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
            logger.exception("QR health check failed")
            return False

    async def close(self) -> None:
        """No-op -- each search opens and closes its own browser."""
