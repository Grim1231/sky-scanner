"""Turkish Airlines crawler -- L2 website API, L3 Playwright, or official API.

Supports three modes, tried in priority order:

1. **L2 website scrape** (default) -- reverse-engineered TK Next.js SPA API.
   No API key required but subject to Akamai Bot Manager blocks (DS-30037).

2. **L3 Playwright** (fallback) -- browser-based form automation.
   Navigates to the TK booking page, fills the form, and intercepts the
   internal API response.  Bypasses Akamai because the browser has a valid
   ``_abck`` cookie bound to a genuine TLS fingerprint.

3. **Official developer API** -- requires ``CRAWLER_TK_API_KEY`` and
   ``CRAWLER_TK_API_SECRET`` from https://developer.apim.turkishairlines.com.
   Enabled by setting ``CRAWLER_TK_USE_OFFICIAL_API=true``.

When the official API is configured, the crawler uses ``getAvailability``
first, falls back to ``getTimeTable``.

When using L2+L3, the crawler tries L2 ``flight-matrix`` first, then L2
``cheapest-prices``.  If both fail (Akamai block), it falls back to L3
Playwright-based search.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import TurkishAirlinesClient, TurkishAirlinesOfficialClient
from .l3_client import TurkishAirlinesPlaywrightClient
from .response_parser import (
    parse_cheapest_prices,
    parse_flight_matrix,
    parse_official_availability,
    parse_official_timetable,
)

logger = logging.getLogger(__name__)


class TurkishAirlinesCrawler(BaseCrawler):
    """Multi-tier crawler: Turkish Airlines flight search.

    Uses the official developer API when ``CRAWLER_TK_USE_OFFICIAL_API``
    is set and credentials are configured.  Otherwise uses L2 website
    scrape with L3 Playwright fallback for Akamai-blocked POST endpoints.
    """

    def __init__(self) -> None:
        self._l2_client = TurkishAirlinesClient(timeout=settings.l2_timeout)
        self._l3_client = TurkishAirlinesPlaywrightClient()
        self._official_client: TurkishAirlinesOfficialClient | None = None

        if settings.tk_use_official_api and settings.tk_api_key:
            self._official_client = TurkishAirlinesOfficialClient()
            logger.info("TK crawler: official API mode enabled")
        else:
            logger.info("TK crawler: L2+L3 mode (no official API key)")

    # ------------------------------------------------------------------
    # Official API crawl path
    # ------------------------------------------------------------------

    async def _crawl_official(self, task: CrawlTask) -> CrawlResult:
        """Crawl using the official TK developer API."""
        assert self._official_client is not None
        start = time.monotonic()
        req = task.search_request

        try:
            # Try getAvailability first (has pricing).
            raw = await self._official_client.get_availability(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date,
                cabin_class=req.cabin_class.value,
            )
            flights = parse_official_availability(raw, cabin_class=req.cabin_class)

            # Fallback to timetable if availability returned no flights.
            if not flights:
                raw_tt = await self._official_client.get_timetable(
                    origin=req.origin,
                    destination=req.destination,
                    departure_date=req.departure_date,
                )
                flights = parse_official_timetable(
                    raw_tt,
                    origin=req.origin,
                    destination=req.destination,
                    cabin_class=req.cabin_class,
                )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CrawlResult(
                flights=flights,
                source=DataSource.OFFICIAL_API,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning("TK official API failed, falling back to L2: %s", exc)
            # Fall back to L2 scrape on official API failure.
            return await self._crawl_l2(task, start_time=start)

    # ------------------------------------------------------------------
    # L2 website scrape crawl path
    # ------------------------------------------------------------------

    async def _crawl_l2(
        self, task: CrawlTask, *, start_time: float | None = None
    ) -> CrawlResult:
        """Crawl using the L2 website scrape client.

        If both L2 endpoints fail (Akamai DS-30037), falls back to the
        L3 Playwright-based search.
        """
        start = start_time if start_time is not None else time.monotonic()
        req = task.search_request

        flights: list = []  # type: ignore[type-arg]
        l2_error: str | None = None

        # Try flight-matrix first (includes full flight details).
        try:
            raw_matrix = await self._l2_client.get_flight_matrix(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date,
                cabin_class=req.cabin_class.value,
            )
            flights = parse_flight_matrix(
                raw_matrix,
                cabin_class=req.cabin_class,
            )
        except Exception as exc:
            l2_error = str(exc)
            logger.warning("TK flight-matrix failed, trying cheapest-prices: %s", exc)

        # Fallback to cheapest-prices if matrix returned no flights.
        if not flights:
            try:
                raw_prices = await self._l2_client.get_cheapest_prices(
                    origin=req.origin,
                    destination=req.destination,
                    departure_date=req.departure_date,
                    cabin_class=req.cabin_class.value,
                )
                flights = parse_cheapest_prices(
                    raw_prices,
                    origin=req.origin,
                    destination=req.destination,
                    cabin_class=req.cabin_class,
                )
            except Exception as exc:
                l2_error = str(exc)
                logger.warning(
                    "TK L2 cheapest-prices also failed: %s. "
                    "Falling back to L3 Playwright.",
                    exc,
                )

        # If L2 succeeded, return the result.
        if flights:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CrawlResult(
                flights=flights,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
            )

        # L2 failed entirely -- fall back to L3 Playwright.
        return await self._crawl_l3(task, start_time=start, l2_error=l2_error)

    # ------------------------------------------------------------------
    # L3 Playwright crawl path
    # ------------------------------------------------------------------

    async def _crawl_l3(
        self,
        task: CrawlTask,
        *,
        start_time: float | None = None,
        l2_error: str | None = None,
    ) -> CrawlResult:
        """Crawl using the L3 Playwright browser client.

        Navigates to the TK booking page, fills the search form, and
        intercepts the internal API response.  Uses the same response
        parsers as L2 since the SPA calls the same endpoints.
        """
        start = start_time if start_time is not None else time.monotonic()
        req = task.search_request

        try:
            raw = await self._l3_client.search_flights(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date,
                cabin_class=req.cabin_class.value,
            )

            # The intercepted response has the same format as L2 responses.
            # Determine which endpoint was intercepted by checking the data.
            api_data = raw.get("data", {})
            if "originDestinationInformationList" in api_data:
                flights = parse_flight_matrix(raw, cabin_class=req.cabin_class)
            elif "dailyPriceList" in api_data:
                flights = parse_cheapest_prices(
                    raw,
                    origin=req.origin,
                    destination=req.destination,
                    cabin_class=req.cabin_class,
                )
            else:
                # Try flight-matrix parser as default (it handles missing
                # data gracefully by returning an empty list).
                flights = parse_flight_matrix(raw, cabin_class=req.cabin_class)

            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CrawlResult(
                flights=flights,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            # Include both L2 and L3 errors in the message for debugging.
            error_parts = []
            if l2_error:
                error_parts.append(f"L2: {l2_error}")
            error_parts.append(f"L3: {exc}")
            combined_error = "; ".join(error_parts)

            logger.exception("Turkish Airlines crawl failed (L2 + L3)")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=combined_error,
                success=False,
            )

    # ------------------------------------------------------------------
    # BaseCrawler interface
    # ------------------------------------------------------------------

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch TK flight availability for the requested route/date."""
        if self._official_client is not None:
            return await self._crawl_official(task)
        return await self._crawl_l2(task)

    async def health_check(self) -> bool:
        """Check if the TK API is reachable.

        Checks the official API first (if configured), then falls back
        to the L2 website API health check, then L3 Playwright.
        """
        if self._official_client is not None:
            official_ok = await self._official_client.health_check()
            if official_ok:
                return True
            logger.warning("TK official API health check failed, trying L2")

        l2_ok = await self._l2_client.health_check()
        if l2_ok:
            return True

        # L2 health check uses a GET endpoint which usually works.
        # If even that fails, try L3.
        logger.warning("TK L2 health check failed, trying L3")
        return await self._l3_client.health_check()

    async def close(self) -> None:
        """Release resources."""
        await self._l2_client.close()
        await self._l3_client.close()
        if self._official_client is not None:
            await self._official_client.close()
