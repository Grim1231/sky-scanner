"""Celery tasks for flight crawling."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from celery import chord, group

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource, SearchRequest

from .celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="sky_scanner_crawler.tasks.crawl_l1", bind=True, max_retries=2)
def crawl_l1(self, search_request_dict: dict) -> dict:  # type: ignore[override]
    """L1: Google Flights Protobuf crawl."""
    from .google.crawler import GoogleFlightsCrawler

    search_req = SearchRequest.model_validate(search_request_dict)
    task = CrawlTask(
        search_request=search_req,
        source=DataSource.GOOGLE_PROTOBUF,
    )

    async def _run() -> CrawlResult:
        crawler = GoogleFlightsCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    return result.model_dump(mode="json")


@app.task(name="sky_scanner_crawler.tasks.crawl_l2", bind=True, max_retries=2)
def crawl_l2(self, search_request_dict: dict) -> dict:  # type: ignore[override]
    """L2: Kiwi Tequila API crawl."""
    from .kiwi.crawler import KiwiCrawler

    search_req = SearchRequest.model_validate(search_request_dict)
    task = CrawlTask(
        search_request=search_req,
        source=DataSource.KIWI_API,
    )

    async def _run() -> CrawlResult:
        crawler = KiwiCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    return result.model_dump(mode="json")


@app.task(name="sky_scanner_crawler.tasks.merge_and_store")
def merge_and_store(results: list[dict]) -> dict:
    """Merge crawl results from multiple sources and store to DB."""
    from .pipeline.merger import merge_results
    from .pipeline.store import FlightStore

    crawl_results = [CrawlResult.model_validate(r) for r in results]
    merged = merge_results(crawl_results)

    async def _store() -> int:
        from sky_scanner_db.database import async_session_factory

        store = FlightStore()
        async with async_session_factory() as session:
            count = await store.store_flights(merged, session)
            await session.commit()
            return count

    count = asyncio.run(_store())
    logger.info("Stored %d flights to DB", count)
    return {
        "stored_count": count,
        "merged_count": len(merged),
        "sources": [r.source.value for r in crawl_results],
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.task(name="sky_scanner_crawler.tasks.crawl_parallel")
def crawl_parallel(search_request_dict: dict) -> None:
    """Dispatch L1+L2 crawls in parallel, then merge and store."""
    callback = merge_and_store.s()
    job = chord(
        group(
            crawl_l1.s(search_request_dict),
            crawl_l2.s(search_request_dict),
        )
    )(callback)
    logger.info("Dispatched parallel crawl job: %s", job.id)
