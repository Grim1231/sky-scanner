"""Turkish Airlines crawler -- flight availability via L2 website API or official API.

Supports two modes:

1. **L2 website scrape** (default) -- reverse-engineered TK Next.js SPA API.
   No API key required but subject to Akamai Bot Manager blocks.

2. **Official developer API** -- requires ``CRAWLER_TK_API_KEY`` and
   ``CRAWLER_TK_API_SECRET`` from https://developer.apim.turkishairlines.com.
   Enabled by setting ``CRAWLER_TK_USE_OFFICIAL_API=true``.

When the official API is configured, the crawler uses ``getAvailability``
first (includes pricing), falls back to ``getTimeTable`` (schedule only).
When using the L2 scrape, it tries ``flight-matrix`` first, then falls
back to ``cheapest-prices``.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import TurkishAirlinesClient, TurkishAirlinesOfficialClient
from .response_parser import (
    parse_cheapest_prices,
    parse_flight_matrix,
    parse_official_availability,
    parse_official_timetable,
)

logger = logging.getLogger(__name__)


class TurkishAirlinesCrawler(BaseCrawler):
    """L2 crawler: Turkish Airlines flight search.

    Uses the official developer API when ``CRAWLER_TK_USE_OFFICIAL_API``
    is set and credentials are configured; otherwise falls back to the
    L2 website scrape client.
    """

    def __init__(self) -> None:
        self._l2_client = TurkishAirlinesClient(timeout=settings.l2_timeout)
        self._official_client: TurkishAirlinesOfficialClient | None = None

        if settings.tk_use_official_api and settings.tk_api_key:
            self._official_client = TurkishAirlinesOfficialClient()
            logger.info("TK crawler: official API mode enabled")
        else:
            logger.info("TK crawler: L2 website scrape mode (no official API key)")

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
    # L2 website scrape crawl path (existing logic)
    # ------------------------------------------------------------------

    async def _crawl_l2(
        self, task: CrawlTask, *, start_time: float | None = None
    ) -> CrawlResult:
        """Crawl using the L2 website scrape client."""
        start = start_time if start_time is not None else time.monotonic()
        req = task.search_request

        try:
            # Try flight-matrix first (includes full flight details).
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

            # Fallback to cheapest-prices if matrix returned no flights.
            if not flights:
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

            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CrawlResult(
                flights=flights,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.exception("Turkish Airlines crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
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
        to the L2 website API health check.
        """
        if self._official_client is not None:
            official_ok = await self._official_client.health_check()
            if official_ok:
                return True
            logger.warning("TK official API health check failed, trying L2")
        return await self._l2_client.health_check()

    async def close(self) -> None:
        """Release resources."""
        await self._l2_client.close()
        if self._official_client is not None:
            await self._official_client.close()
