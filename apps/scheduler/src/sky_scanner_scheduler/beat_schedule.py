"""Dynamic Celery Beat schedule builder."""

from __future__ import annotations

from datetime import date, timedelta

from .config import scheduler_settings
from .route_config import TIER1_ROUTES, TIER2_ROUTES


def _build_route_tasks(
    routes: list[tuple[str, str]],
    interval_seconds: int,
    tier_name: str,
) -> dict:
    """Build beat schedule entries for a list of routes."""
    schedule = {}
    today = date.today()

    for origin, destination in routes:
        # Schedule crawls for the next N days
        for days_ahead in range(1, scheduler_settings.search_days_ahead + 1, 7):
            dep_date = today + timedelta(days=days_ahead)
            task_name = f"{tier_name}-{origin}-{destination}-{dep_date.isoformat()}"
            schedule[task_name] = {
                "task": "sky_scanner_crawler.tasks.crawl_parallel",
                "schedule": interval_seconds,
                "args": [
                    {
                        "origin": origin,
                        "destination": destination,
                        "departure_date": dep_date.isoformat(),
                        "cabin_class": scheduler_settings.default_cabin,
                        "trip_type": "ONE_WAY",
                        "currency": scheduler_settings.default_currency,
                    }
                ],
            }
    return schedule


def build_beat_schedule() -> dict:
    """Build the complete Celery Beat schedule."""
    schedule: dict = {}

    # Tier 1: Popular routes - every 10 minutes
    schedule.update(
        _build_route_tasks(
            TIER1_ROUTES,
            scheduler_settings.tier1_interval,
            "tier1",
        )
    )

    # Tier 2: Other routes - every 2 hours
    schedule.update(
        _build_route_tasks(
            TIER2_ROUTES,
            scheduler_settings.tier2_interval,
            "tier2",
        )
    )

    return schedule
