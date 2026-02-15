"""Hainan Airlines L2 crawler -- fetches daily lowest fares via the fare-trends API.

.. note::
   The ``airFareTrends`` endpoint only supports **domestic Chinese
   routes** (e.g. PEK-HAK, PEK-CAN, PEK-SZX, PEK-CTU).  International
   routes will return an empty result (no error, just zero flights).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import _CABIN_MAP, HainanAirlinesClient
from .response_parser import parse_fare_trends

logger = logging.getLogger(__name__)


class HainanAirlinesCrawler(BaseCrawler):
    """L2 crawler: Hainan Airlines fare-trends calendar API.

    Uses the publicly accessible ``app.hnair.com`` fare-trends endpoint
    (no authentication required beyond HMAC-SHA1 signing).  Returns one
    ``NormalizedFlight`` per day over a ~136-day window, containing the
    lowest available fare in CNY.

    **Limitation:** Only domestic Chinese routes are supported by this
    endpoint.  For international Hainan Airlines routes, use the L1
    (Google Protobuf) or L2 (Kiwi API) crawlers instead.
    """

    def __init__(self) -> None:
        self._client = HainanAirlinesClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch daily lowest fares starting from the departure date."""
        start = time.monotonic()
        req = task.search_request

        cabin = _CABIN_MAP.get(req.cabin_class.value, "Y")

        try:
            raw = await self._client.search_fare_trends(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date.isoformat(),
                cabin=cabin,
            )

            flights = parse_fare_trends(
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
            logger.exception("Hainan Airlines crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Hainan Airlines fare-trends API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the HTTP client."""
        await self._client.close()
