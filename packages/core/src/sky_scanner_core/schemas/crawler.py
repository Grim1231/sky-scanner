"""Crawler task and result schemas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from datetime import datetime

    from .enums import DataSource
    from .flight import NormalizedFlight
    from .search import SearchRequest


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
