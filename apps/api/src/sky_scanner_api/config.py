"""API configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    database_url: str = "postgresql+asyncpg://localhost:5432/sky_scanner"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: list[str] = ["http://localhost:3000"]
    rate_limit_per_minute: int = 60

    # Cache TTLs in seconds
    search_cache_ttl: int = 300  # 5 min
    search_cache_swr: int = 120  # 2 min grace
    price_cache_ttl: int = 600  # 10 min
    reference_cache_ttl: int = 3600  # 1 hour

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"

    model_config = SettingsConfigDict(
        env_prefix="API_", env_file=".env", extra="ignore"
    )


settings = ApiSettings()
