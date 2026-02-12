"""SQLAlchemy ORM models for Sky Scanner."""

from .airline import Airline, AirlineType, Alliance
from .airport import Airport
from .analytics import BookingTimeAnalysis, PriceFeature
from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .flight import CabinClass, DataSource, Flight
from .price import Price
from .search import PriceAlert, SearchHistory
from .seat_spec import SeatSpec
from .user import Priority, User, UserPreference

__all__ = [
    "Airline",
    "AirlineType",
    "Airport",
    "Alliance",
    "Base",
    "BookingTimeAnalysis",
    "CabinClass",
    "DataSource",
    "Flight",
    "Price",
    "PriceAlert",
    "PriceFeature",
    "Priority",
    "SearchHistory",
    "SeatSpec",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserPreference",
]
