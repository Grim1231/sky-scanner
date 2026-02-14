"""Crawler configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class CrawlerSettings(BaseSettings):
    """Settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="CRAWLER_", env_file=".env", extra="ignore"
    )

    # Kiwi Tequila API
    kiwi_api_key: str = ""

    # Rate limits (requests per minute)
    l1_rate_per_min: int = 30
    l2_rate_per_min: int = 60

    # Timeouts (seconds)
    l1_timeout: int = 30
    l2_timeout: int = 30

    # Proxy
    l1_proxy_url: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Currency
    default_currency: str = "KRW"


settings = CrawlerSettings()
