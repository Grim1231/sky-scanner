"""Scheduler configuration via environment variables."""

from pydantic_settings import BaseSettings


class SchedulerSettings(BaseSettings):
    """Settings loaded from environment variables."""

    model_config = {"env_prefix": "SCHEDULER_"}

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Schedule intervals (seconds)
    tier1_interval: int = 600  # 10 minutes
    tier2_interval: int = 7200  # 2 hours

    # Default search params
    default_currency: str = "KRW"
    default_cabin: str = "ECONOMY"
    search_days_ahead: int = 60


scheduler_settings = SchedulerSettings()
