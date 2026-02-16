"""Thai Airways (TG) crawler -- L2 primp (Sputnik + popular-fares) with L3 fallback.

Uses two L2 HTTP approaches by default, falling back to L3 Playwright only
when both fail:

1. **Sputnik API** (primary) -- EveryMundo fare search via primp, same
   pattern as JL/NZ/ET crawlers.  Returns daily lowest fares across
   the TG route network.
2. **Popular-fares API** (secondary) -- direct POST to
   ``/common/calendarPricing/popular-fares`` via primp.  Returns
   cheapest fare per route from a given origin.
3. **L3 Playwright** (optional fallback) -- form-based search via the
   Amadeus OSCI booking widget.  Disabled by default due to duplicate
   element ID issues in the SPA.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .l2_client import ThaiAirwaysL2Client
from .l2_parser import parse_popular_fares, parse_sputnik_fares

logger = logging.getLogger(__name__)


class ThaiAirwaysCrawler(BaseCrawler):
    """L2 crawler: Thai Airways fares via Sputnik + popular-fares APIs.

    Tries Sputnik first (daily lowest fares), then popular-fares
    (cheapest per route/date), then optionally the L3 Playwright client
    as a last resort.
    """

    def __init__(self, *, enable_l3_fallback: bool = False) -> None:
        self._l2_client = ThaiAirwaysL2Client(timeout=settings.l2_timeout)
        self._enable_l3_fallback = enable_l3_fallback

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Search fares on Thai Airways and return normalised results."""
        start = time.monotonic()
        req = task.search_request

        # --- Approach 1: Sputnik API ---
        try:
            raw = await self._l2_client.search_fares(
                origin=req.origin,
                destination=req.destination if req.destination else None,
            )
            flights = parse_sputnik_fares(
                raw,
                origin_filter=req.origin,
                destination_filter=req.destination if req.destination else None,
                cabin_class=req.cabin_class,
            )
            if flights:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                logger.info(
                    "TG L2 Sputnik: %d flights for %s->%s (%dms)",
                    len(flights),
                    req.origin,
                    req.destination or "*",
                    elapsed_ms,
                )
                return CrawlResult(
                    flights=flights,
                    source=DataSource.DIRECT_CRAWL,
                    crawled_at=datetime.now(tz=UTC),
                    duration_ms=elapsed_ms,
                )
            logger.info("TG Sputnik returned 0 flights, trying popular-fares")
        except Exception:
            logger.warning("TG Sputnik failed, trying popular-fares", exc_info=True)

        # --- Approach 2: popular-fares API ---
        try:
            popular_data = await self._l2_client.search_popular_fares(req.origin)
            flights = parse_popular_fares(
                popular_data,
                origin_filter=req.origin,
                destination_filter=req.destination if req.destination else None,
                cabin_class=req.cabin_class,
            )
            if flights:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                logger.info(
                    "TG L2 popular-fares: %d flights for %s->%s (%dms)",
                    len(flights),
                    req.origin,
                    req.destination or "*",
                    elapsed_ms,
                )
                return CrawlResult(
                    flights=flights,
                    source=DataSource.DIRECT_CRAWL,
                    crawled_at=datetime.now(tz=UTC),
                    duration_ms=elapsed_ms,
                )
            logger.info("TG popular-fares returned 0 flights")
        except Exception:
            logger.warning("TG popular-fares failed", exc_info=True)

        # --- Approach 3: L3 Playwright fallback (optional) ---
        if self._enable_l3_fallback:
            try:
                from .client import ThaiAirwaysClient
                from .response_parser import parse_intercepted_responses

                logger.info("TG: falling back to L3 Playwright")
                l3_client = ThaiAirwaysClient(timeout=30)
                try:
                    raw_responses = await l3_client.search_flights(
                        origin=req.origin,
                        destination=req.destination,
                        departure_date=req.departure_date,
                        cabin_class=req.cabin_class.value,
                    )
                    flights = parse_intercepted_responses(
                        raw_responses,
                        origin=req.origin,
                        destination=req.destination,
                        cabin_class=req.cabin_class,
                    )
                    if flights:
                        elapsed_ms = int((time.monotonic() - start) * 1000)
                        logger.info(
                            "TG L3 Playwright: %d flights (%dms)",
                            len(flights),
                            elapsed_ms,
                        )
                        return CrawlResult(
                            flights=flights,
                            source=DataSource.DIRECT_CRAWL,
                            crawled_at=datetime.now(tz=UTC),
                            duration_ms=elapsed_ms,
                        )
                finally:
                    await l3_client.close()
            except Exception:
                logger.warning("TG L3 Playwright fallback failed", exc_info=True)

        # All approaches exhausted.
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning(
            "TG: all approaches failed for %s->%s",
            req.origin,
            req.destination or "*",
        )
        return CrawlResult(
            source=DataSource.DIRECT_CRAWL,
            crawled_at=datetime.now(tz=UTC),
            duration_ms=elapsed_ms,
            error="All TG crawl approaches failed (Sputnik, popular-fares)",
            success=False,
        )

    async def health_check(self) -> bool:
        """Check if the Thai Airways Sputnik API is reachable."""
        return await self._l2_client.health_check()

    async def close(self) -> None:
        """Release resources."""
        await self._l2_client.close()
