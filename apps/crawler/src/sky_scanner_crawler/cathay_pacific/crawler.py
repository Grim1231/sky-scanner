"""Cathay Pacific L2 crawler -- flight timetable and fare calendar via website APIs.

Covers CX (Cathay Pacific Airways) by calling the same internal JSON APIs
that the cathaypacific.com SPA uses.

Target endpoints (reverse-engineered):
    GET  api.cathaypacific.com/flightinformation/flightschedule/v2/flightTimetable
        -- flight schedule (currently broken server-side: HTTP 406)
    GET  book.cathaypacific.com/CathayPacificV3/dyn/air/api/instant/histogram
        -- fare calendar with monthly cheapest return fares
    GET  book.cathaypacific.com/CathayPacificV3/dyn/air/api/instant/open-search
        -- cheapest fares from an origin to all destinations

The booking-domain endpoints (histogram, open-search) do not require
Akamai cookie warm-up and work reliably with ``primp`` Chrome TLS
impersonation alone.

Strategy:
1. Try the histogram endpoint first (reliable, returns fare calendar).
2. If histogram returns no results (e.g. unsupported airport code for
   multi-airport cities), fall back to open-search and filter by the
   requested destination.
3. The timetable endpoint is attempted last because it is currently
   broken (HTTP 406) but may be restored by CX in the future.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import CathayPacificClient
from .response_parser import parse_histogram, parse_open_search, parse_timetable

logger = logging.getLogger(__name__)


class CathayPacificCrawler(BaseCrawler):
    """L2 crawler: Cathay Pacific flight search via website APIs.

    Attempts the ``histogram`` endpoint first (reliable fare calendar
    data).  Falls back to ``open-search`` if the histogram returns no
    results, and finally tries the ``timetable`` endpoint (currently
    broken server-side) for potential future compatibility.
    """

    def __init__(self) -> None:
        self._client = CathayPacificClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch CX flight availability for the requested route/date."""
        start = time.monotonic()
        req = task.search_request

        try:
            flights = []

            # 1. Try histogram first (most reliable).
            try:
                raw_histogram = await self._client.search_histogram(
                    origin=req.origin,
                    destination=req.destination,
                    cabin_class=req.cabin_class.value,
                )

                flights = parse_histogram(
                    raw_histogram,
                    origin=req.origin,
                    destination=req.destination,
                    cabin_class=req.cabin_class,
                )
            except Exception:
                logger.warning(
                    "CX histogram failed for %s->%s, trying open-search",
                    req.origin,
                    req.destination,
                    exc_info=True,
                )

            # 2. Fallback to open-search if histogram returned nothing.
            if not flights:
                try:
                    raw_open = await self._client.search_open(
                        origin=req.origin,
                        cabin_class=req.cabin_class.value,
                    )
                    flights = parse_open_search(
                        raw_open,
                        origin=req.origin,
                        destination=req.destination,
                        cabin_class=req.cabin_class,
                    )
                except Exception:
                    logger.warning(
                        "CX open-search also failed for %s->%s",
                        req.origin,
                        req.destination,
                        exc_info=True,
                    )

            # 3. Last resort: timetable (currently broken, HTTP 406).
            if not flights:
                try:
                    raw_timetable = await self._client.search_timetable(
                        origin=req.origin,
                        destination=req.destination,
                        departure_date=req.departure_date,
                        cabin_class=req.cabin_class.value,
                    )

                    flights = parse_timetable(
                        raw_timetable,
                        origin=req.origin,
                        destination=req.destination,
                        cabin_class=req.cabin_class,
                    )
                except Exception:
                    logger.debug(
                        "CX timetable also failed for %s->%s "
                        "(expected -- endpoint returns 406)",
                        req.origin,
                        req.destination,
                        exc_info=True,
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
            logger.exception("Cathay Pacific crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Cathay Pacific API is reachable.

        Uses the IBE origin-destination endpoint which has lower
        protection than the timetable/search endpoints.
        """
        return await self._client.health_check()

    async def close(self) -> None:
        """Release resources (no-op for primp per-request clients)."""
        await self._client.close()
