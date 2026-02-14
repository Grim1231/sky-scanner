"""Crawler task and result schemas."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, Field

from .enums import DataSource  # noqa: TC001
from .flight import NormalizedFlight  # noqa: TC001
from .search import SearchRequest  # noqa: TC001


class SourceConfig(BaseModel):
    """Configuration for a data source."""

    name: DataSource
    rate_limit_per_min: int = 30
    timeout_seconds: int = 30
    enabled: bool = True


class CrawlTask(BaseModel):
    """A single crawl job dispatched to a crawler."""

    search_request: SearchRequest
    source: DataSource
    priority: int = Field(default=0, ge=0, le=10)


class CrawlResult(BaseModel):
    """Result from a single crawler execution."""

    flights: list[NormalizedFlight] = Field(default_factory=list)
    source: DataSource
    crawled_at: datetime
    duration_ms: int = 0
    error: str | None = None
    success: bool = True
