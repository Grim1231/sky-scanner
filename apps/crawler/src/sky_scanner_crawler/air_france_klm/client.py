"""Air France-KLM GraphQL L2 client using persisted queries.

Covers flight offers for AF (Air France) and KL (KLM) via the Aviato
GraphQL API at ``POST /gql/v1`` on ``www.klm.com``.

The API uses **persisted queries** identified by ``sha256Hash`` values.
No API key is needed.  Akamai Bot Manager protects the search endpoint
and binds the ``_abck`` cookie to the TLS fingerprint.

Strategy:
1. Use Playwright (system Chrome) to load klm.com/search/advanced
2. From within the browser context, call ``fetch()`` to POST the
   GraphQL persisted query (this inherits the valid Akamai session)
3. Return the JSON response

Key operations (captured from klm.com SPA):
  - ``SearchResultAvailableOffersQuery`` -- flight offers with fares
  - ``SharedSearchLowestFareOffersForSearchQuery`` -- lowest fare calendar
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from playwright._impl._errors import Error as PlaywrightError
from playwright.async_api import async_playwright

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

# Cabin class mapping to AF-KLM GraphQL commercial cabin values.
_CABIN_MAP: dict[str, str] = {
    "ECONOMY": "ECONOMY",
    "PREMIUM_ECONOMY": "PREMIUM",
    "BUSINESS": "BUSINESS",
    "FIRST": "FIRST",
}

# Persisted query hashes captured from klm.com (Aviato SPA).
_SEARCH_OFFERS_HASH = "b56e0be21c30edf8b4a61f3909f7d31960163b5b123ae681e06d7dd7c26f4fc3"
_LOWEST_FARES_HASH = "3129e42881c15d2897fe99c294497f2cfa8f2133109dd93ed6cad720633b0243"

_GQL_PATH = "/gql/v1"
_BASE_URL = "https://www.klm.com"

# Headers sent with GraphQL requests (from browser capture).
_GQL_HEADERS_JS = json.dumps(
    {
        "afkl-travel-host": "KL",
        "afkl-travel-market": "US",
        "afkl-travel-language": "en",
        "afkl-travel-country": "US",
        "x-aviato-host": "www.klm.com",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }
)


class AirFranceKlmClient:
    """HTTP client for the Air France-KLM Aviato GraphQL API.

    Uses Playwright with system Chrome to bypass Akamai Bot Manager.
    GraphQL queries are executed via ``page.evaluate(fetch(...))``
    inside the browser context so they inherit the valid Akamai
    session cookies.
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    async def _execute_graphql(
        self,
        operation_name: str,
        query_hash: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """Open a browser, visit KLM, and execute a GraphQL query.

        The entire flow happens inside a single Playwright session:
        1. Launch system Chrome (new headless mode)
        2. Navigate to klm.com main page (triggers Akamai challenge)
        3. Wait for the page URL to stabilise on ``www.klm.com``
        4. Use ``fetch()`` from the page context to POST the query
        5. Return the parsed JSON response
        """
        body = json.dumps(
            {
                "operationName": operation_name,
                "variables": variables,
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": query_hash,
                    },
                },
            }
        )

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
            )
            page = await context.new_page()

            # Remove webdriver detection flag.
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            try:
                # Navigate to main page (triggers Akamai flow).
                # Using the main page avoids
                # ERR_HTTP2_PROTOCOL_ERROR that occurs with
                # /search/advanced in headless mode.
                await page.goto(
                    f"{_BASE_URL}/",
                    wait_until="domcontentloaded",
                    timeout=self._timeout * 1000,
                )

                # Wait for page to be fully loaded and Akamai
                # JS challenge to settle.  Poll until the URL
                # stabilises on klm.com (Akamai may redirect).
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                # If networkidle times out, fall back to a
                # fixed delay.  The page may still be usable.
                logger.debug(
                    "AF-KLM page load did not reach networkidle; using fixed delay"
                )
                await page.wait_for_timeout(5000)

            # Verify we landed on klm.com.
            current_url = page.url
            if "klm.com" not in current_url:
                await browser.close()
                msg = f"AF-KLM navigation failed: landed on {current_url}"
                raise RuntimeError(msg)

            # Execute GraphQL query from within the browser.
            fetch_js = f"""
            async () => {{
                const resp = await fetch(
                    '{_GQL_PATH}',
                    {{
                        method: 'POST',
                        headers: {_GQL_HEADERS_JS},
                        body: {json.dumps(body)},
                    }}
                );
                if (!resp.ok) {{
                    throw new Error(
                        `HTTP ${{resp.status}}: ${{await resp.text()}}`
                    );
                }}
                return await resp.json();
            }}
            """

            try:
                result = await page.evaluate(fetch_js)
            finally:
                await browser.close()

        # Check for GraphQL-level errors.
        if not isinstance(result, dict):
            msg = f"AF-KLM unexpected response type: {type(result)}"
            raise RuntimeError(msg)

        errors = result.get("errors")
        if errors:
            msg = f"AF-KLM GraphQL errors: {errors}"
            raise RuntimeError(msg)

        return result

    @async_retry(
        max_retries=2,
        base_delay=3.0,
        max_delay=15.0,
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
        """Search available flight offers.

        Uses ``SearchResultAvailableOffersQuery`` persisted query.
        Returns the raw GraphQL response dict.
        """
        cabin = _CABIN_MAP.get(cabin_class, "ECONOMY")
        search_uuid = str(uuid.uuid4())

        passengers = [{"id": i + 1, "type": "ADT"} for i in range(adults)]

        variables: dict[str, Any] = {
            "activeConnectionIndex": 0,
            "bookingFlow": "LEISURE",
            "availableOfferRequestBody": {
                "commercialCabins": [cabin],
                "passengers": passengers,
                "requestedConnections": [
                    {
                        "origin": {
                            "code": origin,
                            "type": "AIRPORT",
                        },
                        "destination": {
                            "code": destination,
                            "type": "AIRPORT",
                        },
                        "departureDate": (departure_date.isoformat()),
                    },
                ],
                "bookingFlow": "LEISURE",
            },
            "searchStateUuid": search_uuid,
        }

        result = await self._execute_graphql(
            "SearchResultAvailableOffersQuery",
            _SEARCH_OFFERS_HASH,
            variables,
        )

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

    @async_retry(
        max_retries=2,
        base_delay=3.0,
        max_delay=15.0,
        exceptions=(RuntimeError, OSError, PlaywrightError),
    )
    async def search_lowest_fares(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
    ) -> dict[str, Any]:
        """Search lowest fare offers.

        Uses ``SharedSearchLowestFareOffersForSearchQuery``.
        Returns the raw GraphQL response dict.
        """
        cabin = _CABIN_MAP.get(cabin_class, "ECONOMY")
        search_uuid = str(uuid.uuid4())

        from datetime import timedelta

        dt = departure_date
        start = (dt - timedelta(days=3)).isoformat()
        end = (dt + timedelta(days=3)).isoformat()
        date_interval = f"{start}/{end}"

        passengers = [{"id": i + 1, "type": "ADT"} for i in range(adults)]

        variables: dict[str, Any] = {
            "lowestFareOffersRequest": {
                "bookingFlow": "LEISURE",
                "withUpsellCabins": True,
                "passengers": passengers,
                "commercialCabins": [cabin],
                "fareOption": None,
                "type": "DAY",
                "requestedConnections": [
                    {
                        "departureDate": (departure_date.isoformat()),
                        "dateInterval": date_interval,
                        "origin": {
                            "type": "AIRPORT",
                            "code": origin,
                        },
                        "destination": {
                            "type": "AIRPORT",
                            "code": destination,
                        },
                    },
                ],
            },
            "activeConnection": 0,
            "searchStateUuid": search_uuid,
            "bookingFlow": "LEISURE",
        }

        return await self._execute_graphql(
            "SharedSearchLowestFareOffersForSearchQuery",
            _LOWEST_FARES_HASH,
            variables,
        )

    async def health_check(self) -> bool:
        """Check if the KLM website is reachable via primp."""
        try:
            import primp

            client = primp.Client(
                impersonate="chrome_131",
                follow_redirects=True,
                timeout=self._timeout,
            )

            import asyncio

            resp = await asyncio.to_thread(client.get, f"{_BASE_URL}/")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each query opens and closes its own browser."""
