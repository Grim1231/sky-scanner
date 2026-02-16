"""Air France-KLM L2 crawler -- daily lowest fares via EveryMundo Sputnik API.

Covers AF (Air France) and KL (KLM Royal Dutch Airlines).

Uses the EveryMundo Sputnik fare search API to fetch daily lowest fares
across the AF and KL route networks.  The API returns up to ~300 days of
fare data per query with no authentication beyond a public ``em-api-key``.

This replaces the previous L3 Playwright approach which was permanently
blocked by Akamai HTTP/2 TLS fingerprinting on all AF-KLM domains
(``klm.us``, ``klm.com``, ``airfrance.com`` -- all return
``ERR_HTTP2_PROTOCOL_ERROR`` for both bundled Chromium and system Chrome).

The Sputnik API is the same platform used by Air New Zealand, Ethiopian
Airlines, JAL, and other airlines for publishing fare data.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .sputnik_client import AirFranceKlmSputnikClient
from .sputnik_parser import parse_sputnik_fares

logger = logging.getLogger(__name__)


class AirFranceKlmCrawler(BaseCrawler):
    """L2 crawler: Air France-KLM daily lowest fares via Sputnik API.

    Air France and KLM publish fares through EveryMundo's airTrfx platform.
    The Sputnik fare search endpoint returns up to ~300 days of daily
    lowest one-way fares across the entire AF/KL route network.

    The API does not require session cookies -- only a public ``em-api-key``
    header and correct ``Referer`` / ``Origin`` headers.

    If ``origin`` and ``destination`` are specified in the search request,
    the crawler filters results to that specific route.  Otherwise it
    returns fares for all routes from the given origin.

    Both AF and KL tenants are queried and results are merged, providing
    combined coverage of the SkyTeam alliance hubs (CDG and AMS).
    """

    def __init__(self) -> None:
        self._client = AirFranceKlmSputnikClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch daily lowest fares for the requested route."""
        start = time.monotonic()
        req = task.search_request

        try:
            all_flights = []

            # Query both AF and KL tenants for maximum coverage.
            for tenant in ("AF", "KL"):
                raw = await self._client.search_fares(
                    tenant=tenant,
                    origin=req.origin,
                    destination=req.destination if req.destination else None,
                )

                flights = parse_sputnik_fares(
                    raw,
                    airline_code=tenant,
                    origin_filter=req.origin,
                    destination_filter=req.destination if req.destination else None,
                    cabin_class=req.cabin_class,
                )
                all_flights.extend(flights)

            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CrawlResult(
                flights=all_flights,
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
        """Check if the AF-KLM Sputnik API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the client (no-op; each request creates a fresh HTTP client)."""
        await self._client.close()
