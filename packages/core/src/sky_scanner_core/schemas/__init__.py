"""Core schemas for Sky Scanner."""

from .crawler import CrawlResult, CrawlTask, SourceConfig
from .enums import CabinClass, DataSource, TripType
from .flight import NormalizedFlight, NormalizedPrice
from .search import PassengerCount, SearchRequest

__all__ = [
    "CabinClass",
    "CrawlResult",
    "CrawlTask",
    "DataSource",
    "NormalizedFlight",
    "NormalizedPrice",
    "PassengerCount",
    "SearchRequest",
    "SourceConfig",
    "TripType",
]
