"""Google Flights L1 crawler orchestrator."""

from __future__ import annotations

import logging
import time
from datetime import datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource
from sky_scanner_crawler.base import BaseCrawler
from sky_scanner_crawler.config import settings

from .cookie_manager import CookieManager
from .fetcher import fetch_flights_page
from .html_parser import parse_html
from .js_parser import parse_js_data
from .protobuf_builder import TFSData

logger = logging.getLogger(__name__)


class GoogleFlightsCrawler(BaseCrawler):
    """L1 crawler: Google Flights via protobuf query + JS/HTML parsing."""

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        start = time.monotonic()
        try:
            # 1. Build protobuf TFS data from SearchRequest
            tfs = TFSData.from_search_request(task.search_request)
            tfs_b64 = tfs.as_b64().decode("utf-8")

            params = {
                "tfs": tfs_b64,
                "hl": "en",
                "tfu": "EgQIABABIgA",
                "curr": task.search_request.currency or settings.default_currency,
            }

            # 2. Generate cookies
            cookies = CookieManager.generate()

            # 3. Fetch Google Flights page
            html = await fetch_flights_page(params, cookies)

            # 4. Try JS parsing first, fallback to HTML parsing
            flights = parse_js_data(html, task.search_request.cabin_class)
            if not flights:
                logger.info("JS parsing returned no results, trying HTML parser")
                flights = parse_html(html, task.search_request.cabin_class)

            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CrawlResult(
                flights=flights,
                source=DataSource.GOOGLE_PROTOBUF,
                crawled_at=datetime.now(),
                duration_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.exception("Google Flights crawl failed")
            return CrawlResult(
                source=DataSource.GOOGLE_PROTOBUF,
                crawled_at=datetime.now(),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Try fetching the Google Flights homepage."""
        try:
            html = await fetch_flights_page(
                {"hl": "en"},
                CookieManager.generate(),
            )
            return len(html) > 0
        except Exception:
            logger.exception("Google Flights health check failed")
            return False

    async def close(self) -> None:
        """No persistent resources to release."""
