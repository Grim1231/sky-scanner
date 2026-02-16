"""Air Premia crawler — L2 primp by default, L3 Playwright as fallback."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .l2_client import AirPremiaL2Client
from .response_parser import parse_low_fares

logger = logging.getLogger(__name__)


class AirPremiaCrawler(BaseCrawler):
    """Air Premia daily lowest-fare calendar crawler.

    Uses the L2 primp client (Chrome TLS impersonation) by default to
    bypass Cloudflare without Playwright overhead.  Falls back to the
    L3 Playwright-assisted client when ``use_l3=True``.
    """

    def __init__(self, *, use_l3: bool = False) -> None:
        self._use_l3 = use_l3
        if use_l3:
            from .client import AirPremiaClient

            self._l3_client = AirPremiaClient(timeout=settings.l2_timeout)
            self._l2_client: AirPremiaL2Client | None = None
        else:
            self._l2_client = AirPremiaL2Client(timeout=settings.l2_timeout)
            self._l3_client = None  # type: ignore[assignment]

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch lowest fares for a 30-day window from the departure date."""
        start = time.monotonic()
        req = task.search_request

        begin_date = req.departure_date.isoformat()
        end_date = (req.departure_date + timedelta(days=30)).isoformat()

        try:
            if self._use_l3:
                raw = await self._l3_client.get_low_fares(
                    origin=req.origin,
                    destination=req.destination,
                    begin_date=begin_date,
                    end_date=end_date,
                )
            else:
                assert self._l2_client is not None
                raw = await self._l2_client.get_low_fares(
                    origin=req.origin,
                    destination=req.destination,
                    begin_date=begin_date,
                    end_date=end_date,
                )

            flights = parse_low_fares(
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
            level = "3" if self._use_l3 else "2"
            logger.exception("Air Premia crawl failed (L%s)", level)
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Air Premia API is reachable."""
        if self._use_l3:
            return await self._l3_client.health_check()
        assert self._l2_client is not None
        return await self._l2_client.health_check()

    async def close(self) -> None:
        """Release underlying clients."""
        if self._use_l3:
            await self._l3_client.close()
        elif self._l2_client is not None:
            await self._l2_client.close()
