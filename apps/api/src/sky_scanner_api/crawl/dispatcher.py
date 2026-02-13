"""Dispatch crawl tasks to the Celery worker pool."""

from __future__ import annotations

import logging

from celery import Celery

from sky_scanner_api.config import settings

logger = logging.getLogger(__name__)

_celery_app = Celery(broker=settings.celery_broker_url)


async def dispatch_crawl(search_request_dict: dict) -> str | None:
    """Send a crawl task and return the Celery task ID, or *None* on failure."""
    try:
        result = _celery_app.send_task(
            "sky_scanner_crawler.tasks.crawl_parallel",
            args=[search_request_dict],
        )
        logger.info("Dispatched crawl task %s for %s", result.id, search_request_dict)
        return result.id  # type: ignore[return-value]
    except Exception:
        logger.exception("Failed to dispatch crawl task")
        return None
