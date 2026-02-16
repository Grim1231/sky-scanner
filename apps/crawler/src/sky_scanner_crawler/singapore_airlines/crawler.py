"""Singapore Airlines L2 crawler -- daily lowest fares via EveryMundo Sputnik API.

Primary: EveryMundo Sputnik fare search (no auth, public API key).
Fallback: SQ NDC UAT API (requires ``CRAWLER_SINGAPORE_API_KEY``).

The Sputnik API returns daily lowest one-way fares across the SQ route network
for up to ~300 days ahead, with pricing in native market currencies.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .sputnik_client import SqSputnikClient
from .sputnik_parser import parse_fares

logger = logging.getLogger(__name__)


class SingaporeAirlinesCrawler(BaseCrawler):
    """L2 crawler: Singapore Airlines daily lowest fares via Sputnik API.

    Singapore Airlines publishes fares through EveryMundo's airTrfx
    platform at ``www.singaporeair.com``.  The Sputnik fare search
    endpoint returns up to ~300 days of daily lowest one-way fares
    across the entire SQ route network.

    The API does not require session cookies -- only a public
    ``em-api-key`` header and correct ``Referer`` / ``Origin`` headers.

    If ``origin`` and ``destination`` are specified in the search
    request, the crawler filters results to that specific route.
    Otherwise it returns fares for all routes from the given origin.

    Hub: Singapore Changi Airport (SIN).
    IATA code: SQ.
    """

    def __init__(self) -> None:
        self._client = SqSputnikClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch daily lowest fares for the requested route."""
        start = time.monotonic()
        req = task.search_request

        try:
            raw = await self._client.search_fares(
                origin=req.origin,
                destination=req.destination if req.destination else None,
            )

            flights = parse_fares(
                raw,
                origin_filter=req.origin,
                destination_filter=req.destination if req.destination else None,
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
            logger.exception("Singapore Airlines crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Singapore Airlines Sputnik API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the HTTP client."""
        await self._client.close()
