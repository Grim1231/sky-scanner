"""Playwright-based client for Qatar Airways flight search.

Qatar Airways (QR) uses an Angular 14 SPA with a Shadow DOM booking
widget (``app-nbx-explore``) on ``qatarairways.com/en/book.html``.

The booking widget renders inside a Shadow Root, so standard CSS
selectors cannot pierce it.  All form interaction must go through
JavaScript ``evaluate()`` calls that access the shadow root, or via
ARIA-based selectors which Playwright resolves through accessibility
tree traversal (which *does* pierce shadow DOM).

The search flow:

1. Navigate to ``qatarairways.com/en/book.html``
2. Block cross-domain navigation (partner ad scripts redirect the tab)
3. Wait for the Angular widget to render inside Shadow DOM
4. Fill the search form via ARIA selectors (they pierce shadow DOM)
5. Submit and intercept JSON responses from ``booking.qatarairways.com``

Key API domains observed:

- ``booking.qatarairways.com`` -- main booking backend (JSF/xhtml)
- ``qoreservices.qatarairways.com`` -- flight offer API (may not fire
  on all routes)
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

_BASE_URL = "https://www.qatarairways.com"
_BOOKING_PAGE = f"{_BASE_URL}/en/book.html"

# User-Agent string mimicking a real Chrome browser.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# URL substrings that indicate a flight search result response.
_INTERCEPT_PATTERNS = (
    "qoreservices.qatarairways.com",
    "qoreservices",
    "booking.qatarairways.com",
    "/api/offer/",
    "/api/flight/",
    "/api/search/",
    "/api/calendar/",
    "/nsp/",
    "flightoffers",
    "FlightOffers",
    "availability",
    "offer/search",
    "offer/calendar",
    "offer/price",
    "fareSelection",
    "searchLoading",
)

# JavaScript injected before every navigation to prevent partner ad
# scripts from hijacking the tab by navigating to external domains.
_ANTI_REDIRECT_SCRIPT = """
(() => {
  const _blocked = (url) => {
    if (!url) return false;
    const s = String(url);
    return s.length > 0
      && !s.includes('qatarairways.com')
      && !s.startsWith('about:')
      && !s.startsWith('javascript:')
      && !s.startsWith('blob:');
  };
  // Block location.href = ...
  try {
    const origHref = Object.getOwnPropertyDescriptor(
      Location.prototype, 'href'
    );
    if (origHref && origHref.set) {
      Object.defineProperty(Location.prototype, 'href', {
        get: origHref.get,
        set(val) {
          if (_blocked(val)) return;
          origHref.set.call(this, val);
        },
      });
    }
  } catch {}
  // Block location.assign / replace
  for (const method of ['assign', 'replace']) {
    try {
      const orig = Location.prototype[method];
      Location.prototype[method] = function(url) {
        if (_blocked(url)) return;
        return orig.call(this, url);
      };
    } catch {}
  }
  // Block window.open
  try {
    const origOpen = window.open;
    window.open = function(url) {
      if (_blocked(url)) return null;
      return origOpen.apply(this, arguments);
    };
  } catch {}
  // Remove webdriver flag (stealth)
  try {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
  } catch {}
})();
"""


class QatarAirwaysClient:
    """Async Playwright client for Qatar Airways flight search.

    Navigates to the QR booking page, fills the search form via ARIA
    selectors (which pierce Shadow DOM), submits it, and intercepts API
    responses containing flight offer data.
    """

    def __init__(self, *, timeout: int = 45) -> None:
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Browser / context helpers
    # ------------------------------------------------------------------

    async def _launch_context(
        self,
        pw: Any,
    ) -> tuple[Any, Any, Any]:
        """Launch a stealth browser and return (browser, context, page)."""
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-popup-blocking",
            ],
        )
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            locale="en-US",
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        await page.add_init_script(_ANTI_REDIRECT_SCRIPT)
        return browser, context, page

    # ------------------------------------------------------------------
    # Form interaction helpers (ARIA selectors pierce Shadow DOM)
    # ------------------------------------------------------------------

    @staticmethod
    async def _dismiss_cookie_banner(page: Page) -> None:
        """Dismiss the cookie consent dialog if visible."""
        selectors = [
            'button:has-text("Accept all")',
            'button:has-text("Accept")',
            'button:has-text("OK")',
            'button:has-text("Got it")',
            "#onetrust-accept-btn-handler",
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click(timeout=3000)
                    logger.debug("QR: dismissed consent via %s", sel)
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                continue

    @staticmethod
    async def _click_one_way(page: Page) -> None:
        """Select one-way trip type via ARIA radio role."""
        # The a11y tree exposes: radio "One way"
        try:
            ow = page.get_by_role("radio", name="One way")
            if await ow.is_visible(timeout=5000):
                await ow.click(timeout=3000)
                logger.debug("QR: selected one-way trip type")
                await page.wait_for_timeout(300)
                return
        except Exception:
            logger.debug("QR: get_by_role('radio', 'One way') failed")

        # Fallback: try text-based selectors.
        for sel in [
            'label:has-text("One way")',
            'label:has-text("One Way")',
            '[data-trip-type="OW"]',
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click(timeout=3000)
                    logger.debug("QR: selected one-way via %s", sel)
                    await page.wait_for_timeout(300)
                    return
            except Exception:
                continue

        logger.debug("QR: could not find one-way selector (may already be selected)")

    @staticmethod
    async def _fill_airport_field(
        page: Page,
        code: str,
        field_name: str,
        *,
        field_index: int = 0,
    ) -> bool:
        """Fill an airport autocomplete combobox via ARIA selectors.

        The QR Angular widget exposes two comboboxes with
        ``aria-label="Airport autocomplete"`` (From and To).
        Clicking one opens a listbox with option elements whose text
        contains city, country, airport name, and IATA code, e.g.
        ``"Seoul, South Korea Incheon International Airport ICN"``.

        Parameters
        ----------
        page:
            Playwright page.
        code:
            IATA airport code to search for.
        field_name:
            Human-readable name for logging (``"origin"`` or
            ``"destination"``).
        field_index:
            0 for origin (first combobox), 1 for destination (second).

        Returns
        -------
        bool
            True if the field was filled successfully.
        """
        # Locate the combobox by ARIA label.
        comboboxes = page.get_by_role("combobox", name="Airport autocomplete")
        try:
            count = await comboboxes.count()
            if count <= field_index:
                logger.warning(
                    "QR: found %d comboboxes, need index %d for %s",
                    count,
                    field_index,
                    field_name,
                )
                return False
        except Exception:
            logger.warning("QR: could not count comboboxes for %s", field_name)
            return False

        combobox = comboboxes.nth(field_index)

        try:
            # Click to open the dropdown.
            await combobox.click(timeout=5000)
            await page.wait_for_timeout(500)

            # Clear any existing text and type the IATA code to filter.
            await combobox.fill("")
            await combobox.press_sequentially(code, delay=80)
            logger.debug("QR: typed '%s' into %s combobox", code, field_name)

            # Wait for autocomplete to filter results.
            await page.wait_for_timeout(1500)

            # Find and click the matching option in the listbox.
            # Options contain the IATA code at the end, e.g. "... ICN".
            listbox = page.get_by_role("listbox")
            try:
                options = listbox.get_by_role("option")
                option_count = await options.count()
                logger.debug(
                    "QR: %d options visible for %s after typing '%s'",
                    option_count,
                    field_name,
                    code,
                )

                # Look for an option whose text ends with the IATA code.
                for i in range(min(option_count, 20)):
                    opt = options.nth(i)
                    try:
                        text = await opt.inner_text(timeout=1000)
                        # The IATA code appears at the end of the option
                        # text, e.g. "Seoul, South Korea Incheon ... ICN"
                        if text.rstrip().endswith(code):
                            await opt.click(timeout=3000)
                            logger.debug(
                                "QR: selected %s option: %s",
                                field_name,
                                text.strip()[:80],
                            )
                            await page.wait_for_timeout(500)
                            return True
                    except Exception:
                        continue

                # Fallback: click the first option if any exist.
                if option_count > 0:
                    first_opt = options.first
                    await first_opt.click(timeout=3000)
                    try:
                        text = await first_opt.inner_text(timeout=1000)
                    except Exception:
                        text = "(unknown)"
                    logger.debug(
                        "QR: selected first %s option (fallback): %s",
                        field_name,
                        text.strip()[:80],
                    )
                    await page.wait_for_timeout(500)
                    return True

            except Exception:
                logger.debug("QR: listbox/option interaction failed for %s", field_name)

            # Last resort: press Enter to confirm whatever is typed.
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(500)
            return True

        except Exception:
            logger.warning(
                "QR: could not fill %s field with code %s",
                field_name,
                code,
                exc_info=True,
            )
            return False

    @staticmethod
    async def _fill_departure_date(page: Page, date_str: str) -> bool:
        """Fill the departure date textbox.

        The date field has placeholder text:
        ``"Please enter depart date in the format dd space mmm space yyyy"``
        and the value format is ``"15 Feb 2026"``.
        """
        # Use the ARIA-exposed textbox by its placeholder.
        placeholder = "Please enter depart date"
        try:
            # Locate via placeholder substring.
            date_input = page.get_by_placeholder(placeholder, exact=False)
            if await date_input.is_visible(timeout=3000):
                await date_input.click(timeout=3000)
                await page.wait_for_timeout(300)
                # Triple-click to select all existing text.
                await date_input.click(click_count=3, timeout=2000)
                await page.wait_for_timeout(200)
                await date_input.press_sequentially(date_str, delay=50)
                logger.debug("QR: filled departure date: %s", date_str)
                # Press Escape to close any date picker overlay, then Tab
                # to move to the next field.
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)
                return True
        except Exception:
            logger.debug("QR: placeholder-based date fill failed")

        # Fallback: try by aria-label or role.
        for sel in [
            'input[aria-label*="depart"]',
            'input[placeholder*="depart"]',
            'input[placeholder*="Depart"]',
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click(timeout=3000)
                    await el.click(click_count=3, timeout=2000)
                    await el.press_sequentially(date_str, delay=50)
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)
                    logger.debug("QR: filled departure date via %s", sel)
                    return True
            except Exception:
                continue

        logger.warning("QR: could not fill departure date with %s", date_str)
        return False

    @staticmethod
    async def _click_search(page: Page) -> bool:
        """Click the 'Search flights' button."""
        # Primary: ARIA button role with exact name.
        try:
            btn = page.get_by_role("button", name="Search flights")
            if await btn.is_visible(timeout=5000):
                await btn.click(timeout=5000)
                logger.debug("QR: clicked 'Search flights' button")
                return True
        except Exception:
            logger.debug("QR: get_by_role('button', 'Search flights') failed")

        # Fallback selectors.
        for sel in [
            'button:has-text("Search flights")',
            'button:has-text("Search Flights")',
            'button:has-text("Search")',
            'button[type="submit"]',
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click(timeout=5000)
                    logger.debug("QR: clicked search via %s", sel)
                    return True
            except Exception:
                continue

        # Last resort.
        await page.keyboard.press("Enter")
        logger.debug("QR: pressed Enter as search fallback")
        return False

    @staticmethod
    async def _set_cabin_class(page: Page, cabin_class: str) -> None:
        """Attempt to set cabin class via the passengers/class picker.

        The passengers/class field is a readonly textbox that defaults to
        ``"1 Passenger Economy"``.  Clicking it opens a dropdown.
        """
        if cabin_class == "ECONOMY":
            return  # Already the default.

        cabin_label_map = {
            "PREMIUM_ECONOMY": "Premium Economy",
            "BUSINESS": "Business",
            "FIRST": "First",
        }
        label = cabin_label_map.get(cabin_class)
        if not label:
            return

        try:
            pax_field = page.get_by_role("textbox", name="Passengers / Class")
            if await pax_field.is_visible(timeout=3000):
                await pax_field.click(timeout=3000)
                await page.wait_for_timeout(1000)
                # Look for the cabin class option in the opened dropdown.
                cabin_opt = page.get_by_text(label, exact=False).first
                if await cabin_opt.is_visible(timeout=3000):
                    await cabin_opt.click(timeout=3000)
                    logger.debug("QR: selected cabin class: %s", label)
                    await page.wait_for_timeout(500)
        except Exception:
            logger.debug("QR: could not set cabin class to %s", cabin_class)

    # ------------------------------------------------------------------
    # Response interception
    # ------------------------------------------------------------------

    @staticmethod
    def _make_response_handler(
        intercepted: list[dict[str, Any]],
    ) -> Any:
        """Return an async callback that captures JSON API responses."""

        async def _on_response(response: Response) -> None:
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

        return _on_response

    # ------------------------------------------------------------------
    # Wait for search results
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_for_results(
        page: Page,
        intercepted: list[dict[str, Any]],
        *,
        timeout_ms: int = 60000,
    ) -> None:
        """Poll for intercepted API responses or DOM result indicators."""
        poll_interval = 2000
        elapsed = 0

        while elapsed < timeout_ms:
            # Check for meaningful intercepted responses.
            qore_responses = [
                r
                for r in intercepted
                if any(
                    k in str(r).lower()
                    for k in ("offer", "flight", "fare", "segment", "price")
                )
            ]
            if qore_responses:
                await page.wait_for_timeout(3000)
                return

            # Check if the URL changed to booking.qatarairways.com (search
            # results page).
            if "booking.qatarairways.com" in page.url:
                logger.debug("QR: navigated to booking domain: %s", page.url)
                await page.wait_for_timeout(5000)
                return

            # Check DOM for result indicators.
            indicators = [
                ".flight-result",
                ".flight-list",
                ".search-results",
                ".itinerary",
                ".fare-card",
                ".flight-card",
                ".offer-card",
                ".no-flights",
                ".no-results",
                'text="No flights"',
                'text="No results"',
                "app-flight-list",
                "app-flight-card",
                ".flight-details",
                ".fare-selection",
                # booking.qatarairways.com selectors
                ".fareSelComp",
                "#resultInfoArea",
                ".flightSearchArea",
            ]
            for indicator in indicators:
                try:
                    el = page.locator(indicator).first
                    if await el.is_visible(timeout=500):
                        await page.wait_for_timeout(2000)
                        return
                except Exception:
                    continue

            await page.wait_for_timeout(poll_interval)
            elapsed += poll_interval

        logger.warning(
            "QR: timed out waiting for search results after %dms", timeout_ms
        )

    # ------------------------------------------------------------------
    # Public search methods
    # ------------------------------------------------------------------

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

        Uses ARIA-based selectors which pierce the Shadow DOM of the
        Angular booking widget.

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
            List of raw JSON response dicts intercepted from the QR API.
        """
        intercepted: list[dict[str, Any]] = []
        date_str = departure_date.strftime("%d %b %Y")

        async with async_playwright() as pw:
            browser, _ctx, page = await self._launch_context(pw)
            page.on("response", self._make_response_handler(intercepted))

            try:
                # Navigate to the booking page.
                await page.goto(
                    _BOOKING_PAGE,
                    wait_until="domcontentloaded",
                    timeout=self._timeout * 1000,
                )

                # Wait for the Angular widget to render.  The "Search
                # flights" button appears once the widget is ready.
                try:
                    await page.get_by_role("button", name="Search flights").wait_for(
                        state="visible", timeout=20000
                    )
                except Exception:
                    logger.debug(
                        "QR: 'Search flights' button not visible after 20s; "
                        "trying fixed delay"
                    )
                    await page.wait_for_timeout(8000)

                # Verify we are on the right domain (not redirected).
                if "qatarairways.com" not in page.url:
                    msg = f"QR navigation failed: landed on {page.url}"
                    raise RuntimeError(msg)

                # === Fill the search form ===

                await self._dismiss_cookie_banner(page)
                await self._click_one_way(page)

                # Fill origin airport.
                origin_ok = await self._fill_airport_field(
                    page, origin, "origin", field_index=0
                )
                if not origin_ok:
                    logger.warning("QR: could not fill origin field with %s", origin)

                await page.wait_for_timeout(500)

                # Fill destination airport.
                dest_ok = await self._fill_airport_field(
                    page, destination, "destination", field_index=1
                )
                if not dest_ok:
                    logger.warning(
                        "QR: could not fill destination field with %s", destination
                    )

                await page.wait_for_timeout(500)

                # Fill departure date.
                await self._fill_departure_date(page, date_str)

                # Set cabin class (if non-Economy).
                await self._set_cabin_class(page, cabin_class)

                # Click the search button.
                await self._click_search(page)

                # Wait for results (intercepted API responses or DOM).
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

    async def search_via_direct_url(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
    ) -> list[dict[str, Any]]:
        """Alternative: navigate directly to the booking search URL.

        Qatar Airways booking uses ``booking.qatarairways.com`` with
        the ``/nsp/views/search.xhtml`` endpoint.  The form on
        ``/en/book.html`` submits to this backend.  We can also
        construct a URL that pre-fills the search parameters on the
        main site and let Angular handle the rest.
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

        # The main site booking page accepts URL parameters that
        # pre-fill the Angular widget's form fields.
        search_url = (
            f"{_BASE_URL}/en/book.html"
            f"?widget=QR&searchType=F&addTax498=1&flexibleDate=Off"
            f"&bookingClass={booking_class}&tripType=O"
            f"&from={origin}&to={destination}"
            f"&departing={date_iso}"
            f"&adults={adults}&children=0&infants=0"
            f"&teenager=0&ofw=0&promoCode=&currency=KRW"
        )

        async with async_playwright() as pw:
            browser, _ctx, page = await self._launch_context(pw)
            page.on("response", self._make_response_handler(intercepted))

            try:
                await page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=self._timeout * 1000,
                )

                # Wait for the widget to render and possibly auto-submit.
                try:
                    await page.get_by_role("button", name="Search flights").wait_for(
                        state="visible", timeout=15000
                    )
                except Exception:
                    await page.wait_for_timeout(8000)

                if "qatarairways.com" not in page.url:
                    msg = f"QR direct URL: landed on {page.url}"
                    raise RuntimeError(msg)

                await self._dismiss_cookie_banner(page)

                # If the widget auto-filled from URL params, try clicking
                # search directly.
                await self._click_search(page)

                # Wait for API responses.
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
