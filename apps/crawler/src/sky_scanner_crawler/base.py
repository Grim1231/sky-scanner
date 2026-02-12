"""Abstract base class for all crawlers."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sky_scanner_core.schemas import CrawlResult, CrawlTask


class BaseCrawler(abc.ABC):
    """Base class that all source crawlers must implement."""

    @abc.abstractmethod
    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Execute a crawl task and return normalized results."""

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Return True if the source is reachable."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Release any held resources (HTTP clients, browsers, etc.)."""
