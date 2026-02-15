"""T'way Air L2 crawler — fares via travel agency portal."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import TwayAirClient
from .response_parser import parse_lowest_fares

logger = logging.getLogger(__name__)


class TwayAirCrawler(BaseCrawler):
    """L2 crawler: T'way Air daily lowest fares.

    The main site (``www.twayair.com``) is protected by Akamai Bot
    Manager, but the travel agency portal (``tagency.twayair.com``)
    exposes the same ``getLowestFare`` API without Akamai.

    Returns daily lowest fares (~252 days ahead) with fare class,
    sold-out status, and total price including taxes.
    """

    def __init__(self) -> None:
        self._client = TwayAirClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch daily lowest fares for the requested route."""
        start = time.monotonic()
        req = task.search_request

        try:
            raw = await self._client.get_lowest_fares(
                origin=req.origin,
                destination=req.destination,
            )

            flights = parse_lowest_fares(
                raw,
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
            logger.exception("T'way Air crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the T'way agency portal is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release resources."""
        await self._client.close()
