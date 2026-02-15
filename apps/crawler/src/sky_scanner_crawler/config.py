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

    # Amadeus GDS API
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_hostname: str = "test"  # "test" or "production"

    # Lufthansa Group API (developer.lufthansa.com)
    lufthansa_client_id: str = ""
    lufthansa_client_secret: str = ""
    lufthansa_hostname: str = "api.lufthansa.com"  # or "api-test.lufthansa.com"

    # Singapore Airlines NDC API (developer.singaporeair.com)
    singapore_api_key: str = ""

    # Air France-KLM: no config needed (L2 GraphQL via primp, no API key)

    # Turkish Airlines Official API (developer.apim.turkishairlines.com)
    tk_api_key: str = ""
    tk_api_secret: str = ""
    tk_api_hostname: str = "api.turkishairlines.com"  # production
    tk_use_official_api: bool = False  # set True once API key is obtained

    # Currency
    default_currency: str = "KRW"


settings = CrawlerSettings()
