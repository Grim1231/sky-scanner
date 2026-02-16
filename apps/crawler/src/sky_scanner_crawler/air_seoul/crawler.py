"""Air Seoul crawler — L2 primp with L3 Playwright fallback.

Uses primp (Chrome TLS impersonation) by default.  When Cloudflare
hard-blocks the primp TLS profile with 403, falls back to L3
Playwright to solve the CF JS challenge, extract cookies, and use
httpx for the actual API call.

Endpoint: ``POST /I/KO/searchFlightInfo.do`` (form-encoded).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import AirSeoulClient
from .response_parser import parse_flight_info

logger = logging.getLogger(__name__)


class AirSeoulCrawler(BaseCrawler):
    """Air Seoul flight search via ``flyairseoul.com``.

    Tries L2 (primp) first for speed, then falls back to L3 (Playwright
    CF cookie bypass) when Cloudflare blocks the TLS fingerprint.

    Unlike the calendar-only Jeju Air and Eastar Jet crawlers, Air Seoul
    returns **individual flights** with actual departure/arrival times,
    flight numbers, and multiple fare tiers (PROMOTIONAL / DISCOUNT /
    NORMAL).
    """

    def __init__(self, *, enable_l3_fallback: bool = True) -> None:
        self._l2_client = AirSeoulClient(timeout=settings.l2_timeout)
        self._enable_l3_fallback = enable_l3_fallback
        self._l3_client = None

    async def _get_l3_client(self):
        """Lazily create the L3 client to avoid importing Playwright when not needed."""
        if self._l3_client is None:
            from .l3_client import AirSeoulL3Client

            self._l3_client = AirSeoulL3Client(timeout=60)
        return self._l3_client

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch flights for the requested date.

        Tries L2 (primp) first, then L3 (Playwright) if L2 fails.
        """
        start = time.monotonic()
        req = task.search_request

        departure_date = req.departure_date.strftime("%Y%m%d")
        adults = req.passengers.adults if req.passengers else 1
        children = req.passengers.children if req.passengers else 0
        infants = (
            req.passengers.infants_in_seat + req.passengers.infants_on_lap
            if req.passengers
            else 0
        )

        # --- Approach 1: L2 primp ---
        try:
            raw = await self._l2_client.search_flight_info(
                origin=req.origin,
                destination=req.destination,
                departure_date=departure_date,
                adults=adults,
                children=children,
                infants=infants,
            )

            flights = parse_flight_info(
                raw,
                origin=req.origin,
                destination=req.destination,
                cabin_class=req.cabin_class,
            )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "Air Seoul L2: %d flights for %s->%s (%dms)",
                len(flights),
                req.origin,
                req.destination,
                elapsed_ms,
            )
            return CrawlResult(
                flights=flights,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
            )

        except Exception:
            fallback_msg = (
                "trying L3 Playwright fallback"
                if self._enable_l3_fallback
                else "no fallback enabled"
            )
            logger.warning(
                "Air Seoul L2 failed for %s->%s, %s",
                req.origin,
                req.destination,
                fallback_msg,
                exc_info=True,
            )

        # --- Approach 2: L3 Playwright CF bypass ---
        if self._enable_l3_fallback:
            try:
                l3_client = await self._get_l3_client()
                raw = await l3_client.search_flight_info(
                    origin=req.origin,
                    destination=req.destination,
                    departure_date=departure_date,
                    adults=adults,
                    children=children,
                    infants=infants,
                )

                flights = parse_flight_info(
                    raw,
                    origin=req.origin,
                    destination=req.destination,
                    cabin_class=req.cabin_class,
                )

                elapsed_ms = int((time.monotonic() - start) * 1000)
                logger.info(
                    "Air Seoul L3: %d flights for %s->%s (%dms)",
                    len(flights),
                    req.origin,
                    req.destination,
                    elapsed_ms,
                )
                return CrawlResult(
                    flights=flights,
                    source=DataSource.DIRECT_CRAWL,
                    crawled_at=datetime.now(tz=UTC),
                    duration_ms=elapsed_ms,
                )
            except Exception:
                logger.warning(
                    "Air Seoul L3 Playwright also failed for %s->%s",
                    req.origin,
                    req.destination,
                    exc_info=True,
                )

        # All approaches exhausted.
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning(
            "Air Seoul: all approaches failed for %s->%s",
            req.origin,
            req.destination,
        )
        return CrawlResult(
            source=DataSource.DIRECT_CRAWL,
            crawled_at=datetime.now(tz=UTC),
            duration_ms=elapsed_ms,
            error="All Air Seoul crawl approaches failed (L2 primp, L3 Playwright)",
            success=False,
        )

    async def health_check(self) -> bool:
        """Check if the Air Seoul API is reachable."""
        # Try L2 first
        if await self._l2_client.health_check():
            return True
        # Fall back to L3 if enabled
        if self._enable_l3_fallback:
            try:
                l3_client = await self._get_l3_client()
                return await l3_client.health_check()
            except Exception:
                return False
        return False

    async def close(self) -> None:
        """Release all clients."""
        await self._l2_client.close()
        if self._l3_client is not None:
            await self._l3_client.close()
