"""Jin Air L2 crawler — daily lowest fares from public S3 bucket."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import JinAirClient
from .response_parser import parse_total_fares

logger = logging.getLogger(__name__)


class JinAirCrawler(BaseCrawler):
    """L2 crawler: Jin Air daily lowest fares via ``fare.jinair.com``.

    Jin Air publishes pre-computed daily lowest fares in a public
    S3 bucket (no auth required).  Each route has a JSON file with
    ``{YYYYMMDD: totalPrice}`` entries covering ~6 months ahead.

    Unlike Cloudflare-protected booking endpoints, the fare bucket
    on CloudFront is fully accessible with plain ``httpx``.
    """

    def __init__(self) -> None:
        self._client = JinAirClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch daily lowest fares for the requested route."""
        start = time.monotonic()
        req = task.search_request

        try:
            raw = await self._client.get_total_fares(
                origin=req.origin,
                destination=req.destination,
            )

            flights = parse_total_fares(
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
            logger.exception("Jin Air crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Jin Air fare bucket is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Shut down the HTTP client."""
        await self._client.close()
