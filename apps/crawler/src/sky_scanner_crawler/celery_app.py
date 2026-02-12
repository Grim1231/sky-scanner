"""Celery application configuration."""

from __future__ import annotations

from celery import Celery

from .config import settings

app = Celery(
    "sky_scanner_crawler",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_routes={
        "sky_scanner_crawler.tasks.crawl_l1": {"queue": "crawl_l1"},
        "sky_scanner_crawler.tasks.crawl_l2": {"queue": "crawl_l2"},
        "sky_scanner_crawler.tasks.crawl_parallel": {"queue": "crawl_dispatch"},
        "sky_scanner_crawler.tasks.merge_and_store": {"queue": "merge"},
    },
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
