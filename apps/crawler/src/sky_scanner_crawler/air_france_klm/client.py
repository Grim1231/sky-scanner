"""Air France-KLM L3 Playwright client with response interception.

Covers flight offers for AF (Air France) and KL (KLM) via the Aviato
GraphQL API at ``POST /gql/v1`` on ``www.klm.com``.

The API uses **persisted queries** identified by ``sha256Hash`` values.
No API key is needed.  Akamai Bot Manager protects the search endpoint
and binds the ``_abck`` cookie to the TLS fingerprint.

L3 Strategy (response interception):
1. Use Playwright to navigate to ``klm.com/search/advanced``
2. Dismiss the cookie consent banner
3. Fill the search form (origin, destination, date, cabin, trip type)
4. Click "Search flights" to trigger the SPA's own GraphQL call
5. Intercept the ``/gql/v1`` response containing flight offers
6. Return the raw JSON data

This approach is more robust than the previous L2 ``fetch()`` injection
because the GraphQL request originates entirely from KLM's Angular SPA,
inheriting all Akamai session cookies, headers, and HTTP/2 settings
that the bot manager expects.
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

logger = logging.getLogger(__name__)

# Airline codes served by this API.
AFKLM_AIRLINES = frozenset({"AF", "KL"})

AIRLINE_NAMES: dict[str, str] = {
    "AF": "Air France",
    "KL": "KLM Royal Dutch Airlines",
}

# Cabin class mapping: our CabinClass enum values -> KLM form option text.
_CABIN_FORM_MAP: dict[str, str] = {
    "ECONOMY": "Economy",
    "PREMIUM_ECONOMY": "Premium Comfort",
    "BUSINESS": "Business",
    "FIRST": "Business",  # KLM has no first class option; map to Business
}

_BASE_URL = "https://www.klm.com"
_SEARCH_URL = f"{_BASE_URL}/search/advanced"

# GraphQL operation names that carry flight offer data.
_OFFERS_OPERATION = "SearchResultAvailableOffersQuery"

# Timeouts (milliseconds).
_PAGE_LOAD_TIMEOUT_MS = 30_000
_FORM_WAIT_TIMEOUT_MS = 15_000
_SEARCH_RESULT_TIMEOUT_MS = 60_000
_AUTOCOMPLETE_DELAY_MS = 1500


class AirFranceKlmPlaywrightClient:
    """L3 Playwright client for Air France-KLM flight search.

    Automates the KLM search form and intercepts the GraphQL response
    that the Angular SPA fires when search results load.

    Each ``search_available_offers`` call launches a fresh browser
    session, fills the form, and captures the API response.  No cookies
    or sessions are reused across calls.
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    async def _dismiss_cookie_banner(self, page: Any) -> None:
        """Dismiss the KLM cookie consent banner if present."""
        try:
            reject_btn = page.locator(
                'dialog:has-text("cookies") >> button:has-text("Reject")'
            )
            if await reject_btn.is_visible(timeout=3000):
                await reject_btn.click()
                logger.debug("AF-KLM cookie banner dismissed (rejected)")
                await page.wait_for_timeout(500)
                return
        except Exception:
            pass

        # Fallback: try Accept button.
        try:
            accept_btn = page.locator(
                'dialog:has-text("cookies") >> button:has-text("Accept")'
            )
            if await accept_btn.is_visible(timeout=1000):
                await accept_btn.click()
                logger.debug("AF-KLM cookie banner dismissed (accepted)")
                await page.wait_for_timeout(500)
        except Exception:
            logger.debug("AF-KLM no cookie banner found")

    async def _wait_for_search_form(self, page: Any) -> None:
        """Wait for the KLM search form to load."""
        await page.wait_for_selector(
            '[role="search"]',
            timeout=_FORM_WAIT_TIMEOUT_MS,
        )
        logger.debug("AF-KLM search form loaded")

    async def _select_trip_type(self, page: Any, one_way: bool = True) -> None:
        """Set the trip type dropdown."""
        trip_combo = page.get_by_role("combobox", name="Trip")
        option = "One-way" if one_way else "Round trip"
        await trip_combo.select_option(option)
        await page.wait_for_timeout(300)
        logger.debug("AF-KLM trip type set to %s", option)

    async def _fill_airport(
        self,
        page: Any,
        label: str,
        iata_code: str,
    ) -> None:
        """Fill an airport combobox (origin or destination).

        Types the IATA code, waits for the autocomplete dropdown, and
        clicks the first matching option.
        """
        combo = page.get_by_role("combobox", name=label)
        await combo.click()
        await combo.fill(iata_code)
        await page.wait_for_timeout(_AUTOCOMPLETE_DELAY_MS)

        # Click the first option in the autocomplete listbox that
        # contains the IATA code in its text.
        selector = f'[role="listbox"] [role="option"]:has-text("{iata_code}")'
        option = page.locator(selector)
        first_option = option.first
        try:
            await first_option.click(timeout=5000)
        except Exception:
            # Fallback: click any option in the listbox.
            fallback = page.locator('[role="listbox"] [role="option"]').first
            await fallback.click(timeout=5000)

        await page.wait_for_timeout(300)
        logger.debug("AF-KLM airport %s set to %s", label, iata_code)

    async def _select_date(self, page: Any, departure_date: date) -> None:
        """Select the departure date from the calendar picker.

        Clicks the date button to open the calendar, navigates forward
        by month if needed, and clicks the target date cell.
        """
        # Click the date area to open the calendar.
        date_btn = page.locator('button:has-text("choose a date")')
        if not await date_btn.is_visible(timeout=3000):
            # The date area might use different text after form update.
            date_btn = page.locator('[role="search"] button').filter(
                has=page.locator('text="Departure date"')
            )
        await date_btn.first.click()
        await page.wait_for_timeout(500)

        # Format the target date as KLM expects: "DD Month YYYY".
        target_label = departure_date.strftime("%d %B %Y")
        # Remove leading zero from day (KLM uses "1 March 2026" not "01 March 2026").
        if target_label.startswith("0"):
            target_label = target_label[1:]

        # Try to find the date button directly. If not visible, navigate months.
        for _attempt in range(12):
            date_cell = page.get_by_role("button", name=target_label, exact=True)
            if await date_cell.is_visible(timeout=1000):
                await date_cell.click()
                break
            # Click "Next month" to advance the calendar.
            next_btn = page.get_by_role("button", name="Next month")
            if await next_btn.is_visible(timeout=1000):
                await next_btn.click()
                await page.wait_for_timeout(300)
            else:
                break
        else:
            msg = f"AF-KLM could not find date {target_label} in calendar"
            raise RuntimeError(msg)

        await page.wait_for_timeout(300)

        # Confirm the date selection.
        confirm_btn = page.get_by_role("button", name="Confirm dates")
        if await confirm_btn.is_visible(timeout=2000):
            await confirm_btn.click()
            await page.wait_for_timeout(300)

        logger.debug("AF-KLM date set to %s", departure_date)

    async def _select_cabin_class(self, page: Any, cabin_class: str) -> None:
        """Select the cabin class from the dropdown."""
        form_value = _CABIN_FORM_MAP.get(cabin_class, "Economy")
        cabin_combo = page.get_by_role("combobox", name="Class")
        await cabin_combo.select_option(form_value)
        await page.wait_for_timeout(300)
        logger.debug("AF-KLM cabin class set to %s", form_value)

    async def _intercept_offers_response(
        self,
        page: Any,
    ) -> dict[str, Any]:
        """Set up response interception, click search, and capture the result.

        Registers a ``page.on("response")`` handler that captures any
        response whose URL contains ``/gql/v1`` and whose body contains
        the ``SearchResultAvailableOffersQuery`` operation name (or
        contains ``availableOffers`` / ``offerItineraries`` keys).
        """
        captured: dict[str, Any] = {}
        capture_event = asyncio.Event()

        async def _on_response(response: Response) -> None:
            """Callback for intercepted responses."""
            if captured:
                return  # Already captured.
            url = response.url
            if "/gql/v1" not in url:
                return
            if response.status != 200:
                return

            try:
                body = await response.json()
            except Exception:
                return

            if not isinstance(body, dict):
                return

            # Check if this is the offers response.
            data = body.get("data", {})
            if "availableOffers" in data:
                captured.update(body)
                capture_event.set()
                logger.debug("AF-KLM intercepted offers response")

        page.on("response", _on_response)

        # Click the search button.
        search_btn = page.get_by_role("button", name="Search flights")
        await search_btn.click()
        logger.debug("AF-KLM search button clicked, waiting for GraphQL response")

        # Wait for the offers response (or timeout).
        try:
            await asyncio.wait_for(
                capture_event.wait(),
                timeout=_SEARCH_RESULT_TIMEOUT_MS / 1000,
            )
        except TimeoutError:
            msg = "AF-KLM timed out waiting for GraphQL offers response"
            raise RuntimeError(msg) from None

        return captured

    @async_retry(
        max_retries=2,
        base_delay=5.0,
        max_delay=20.0,
        exceptions=(RuntimeError, OSError, PlaywrightError),
    )
    async def search_available_offers(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
    ) -> dict[str, Any]:
        """Search available flight offers via Playwright form automation.

        Navigates to KLM search page, fills the form, clicks search,
        and intercepts the GraphQL response containing flight offers.

        Parameters
        ----------
        origin:
            IATA airport code (e.g. ``AMS``).
        destination:
            IATA airport code (e.g. ``ICN``).
        departure_date:
            Departure date.
        cabin_class:
            Cabin class string (``ECONOMY``, ``PREMIUM_ECONOMY``,
            ``BUSINESS``, ``FIRST``).
        adults:
            Number of adult passengers (currently always 1).

        Returns
        -------
        dict
            Raw GraphQL JSON response containing ``data.availableOffers``.
        """
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--headless=new",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh;"
                    " Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
            )
            page = await context.new_page()

            # Remove webdriver detection flag.
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            try:
                # 1. Navigate to the KLM search page.
                logger.debug("AF-KLM navigating to %s", _SEARCH_URL)
                await page.goto(
                    _SEARCH_URL,
                    wait_until="domcontentloaded",
                    timeout=_PAGE_LOAD_TIMEOUT_MS,
                )

                # 2. Dismiss cookie consent banner.
                await self._dismiss_cookie_banner(page)

                # 3. Wait for the search form to render.
                await self._wait_for_search_form(page)

                # 4. Fill the search form.
                await self._select_trip_type(page, one_way=True)
                await self._fill_airport(page, "Departing from", origin)
                await self._fill_airport(page, "Arriving at", destination)
                await self._select_date(page, departure_date)
                await self._select_cabin_class(page, cabin_class)

                # 5. Intercept the GraphQL response and click search.
                result = await self._intercept_offers_response(page)

            finally:
                await browser.close()

        # Validate the response.
        if not isinstance(result, dict):
            msg = f"AF-KLM unexpected response type: {type(result)}"
            raise RuntimeError(msg)

        errors = result.get("errors")
        if errors:
            msg = f"AF-KLM GraphQL errors: {errors}"
            raise RuntimeError(msg)

        offers = result.get("data", {}).get("availableOffers", {})
        n_itins = len(offers.get("offerItineraries", []))
        logger.info(
            "AF-KLM search %s->%s (%s): %d itineraries",
            origin,
            destination,
            departure_date,
            n_itins,
        )
        return result

    async def health_check(self) -> bool:
        """Check if the KLM search page is reachable."""
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    channel="chrome",
                    args=["--headless=new"],
                )
                page = await browser.new_page()
                resp = await page.goto(
                    f"{_BASE_URL}/",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                await browser.close()
                return resp is not None and resp.ok
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each search opens and closes its own browser."""
