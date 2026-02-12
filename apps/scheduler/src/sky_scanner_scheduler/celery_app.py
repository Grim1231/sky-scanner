"""Celery Beat application for scheduling crawl jobs."""

from __future__ import annotations

from celery import Celery

from .config import scheduler_settings

app = Celery(
    "sky_scanner_scheduler",
    broker=scheduler_settings.celery_broker_url,
    backend=scheduler_settings.celery_result_backend,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


def configure_beat() -> None:
    """Configure beat schedule from route config."""
    from .beat_schedule import build_beat_schedule

    app.conf.beat_schedule = build_beat_schedule()
