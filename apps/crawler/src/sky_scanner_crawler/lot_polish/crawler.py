"""LOT Polish Airlines L2 crawler -- watchlist price boxes API."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import LotPolishClient
from .response_parser import parse_price_boxes

logger = logging.getLogger(__name__)


class LotPolishCrawler(BaseCrawler):
    """L2 crawler: LOT Polish Airlines via ``watchlistPriceBoxesSearch``.

    LOT's AEM-powered site exposes a watchlist price-boxes API that
    returns curated fare offers for a route.  Each route typically has
    economy and business class offers with round-trip prices.

    Requires primp TLS fingerprinting and a session cookie from the
    LOT homepage.  Currency depends on the locale used (default ``pl/en``
    returns PLN; ``kr/ko`` returns KRW).
    """

    def __init__(self, *, locale: str = "kr/ko") -> None:
        self._client = LotPolishClient(
            timeout=settings.l2_timeout,
            locale=locale,
        )

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch price box fares for the requested route."""
        start = time.monotonic()
        req = task.search_request

        try:
            raw = await self._client.get_price_boxes(
                origin=req.origin,
                destination=req.destination,
            )

            flights = parse_price_boxes(
                raw,
                origin=req.origin,
                destination=req.destination,
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
            logger.exception("LOT Polish crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the LOT fare API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Shut down the HTTP client."""
        await self._client.close()
