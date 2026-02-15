"""Air Busan L2 crawler — fares via Naver Yeti UA bypass."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import AirBusanClient
from .response_parser import parse_flights_avail

logger = logging.getLogger(__name__)


class AirBusanCrawler(BaseCrawler):
    """L2 crawler: Air Busan flight availability.

    Cloudflare is bypassed using the Naver Yeti search-crawler
    User-Agent, which is whitelisted in Air Busan's robots.txt.
    No cookies, sessions, or CSRF tokens are needed.

    Returns individual flights with per-class pricing (S/L/A/E),
    seat availability, and tax breakdown.
    """

    def __init__(self) -> None:
        self._client = AirBusanClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch flight availability for the requested route and date."""
        start = time.monotonic()
        req = task.search_request

        departure_date = req.departure_date.strftime("%Y%m%d")

        try:
            raw = await self._client.get_flights_avail(
                origin=req.origin,
                destination=req.destination,
                departure_date=departure_date,
            )

            flights = parse_flights_avail(
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
            logger.exception("Air Busan crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Air Busan API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release resources."""
        await self._client.close()
