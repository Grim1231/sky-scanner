"""Air France-KLM L3 crawler -- flight offers via Aviato GraphQL API.

Covers AF (Air France) and KL (KLM Royal Dutch Airlines).

Uses persisted GraphQL queries captured from the klm.com Angular SPA.
Requires Playwright (system Chrome) to solve the Akamai Bot Manager
challenge, then executes ``fetch()`` from within the browser context.
No API key is needed.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from .client import AirFranceKlmClient
from .response_parser import parse_available_offers

logger = logging.getLogger(__name__)


class AirFranceKlmCrawler(BaseCrawler):
    """L3 crawler: Air France-KLM flight offers via Aviato GraphQL.

    Sends a ``SearchResultAvailableOffersQuery`` persisted query to
    ``POST /gql/v1`` on ``www.klm.com`` using Playwright to bypass
    Akamai Bot Manager.
    """

    def __init__(self) -> None:
        self._client = AirFranceKlmClient()

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch AF-KLM flight offers for the requested route/date."""
        start = time.monotonic()
        req = task.search_request

        try:
            raw = await self._client.search_available_offers(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date,
                cabin_class=req.cabin_class.value,
            )

            flights = parse_available_offers(
                raw,
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
            logger.exception("Air France-KLM crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the KLM GraphQL API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the client (no-op for primp)."""
        await self._client.close()
