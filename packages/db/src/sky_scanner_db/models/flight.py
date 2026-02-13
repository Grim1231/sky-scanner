"""Flight model."""

from __future__ import annotations

import enum
import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .airline import Airline
    from .airport import Airport
    from .price import Price


class DataSource(enum.StrEnum):
    """Source of crawled flight data."""

    GOOGLE_PROTOBUF = "GOOGLE_PROTOBUF"
    KIWI_API = "KIWI_API"
    DIRECT_CRAWL = "DIRECT_CRAWL"
    GDS = "GDS"


class CabinClass(enum.StrEnum):
    """Cabin class for the flight."""

    ECONOMY = "ECONOMY"
    PREMIUM_ECONOMY = "PREMIUM_ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"


class Flight(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Flights table - stores crawled flight data."""

    __tablename__ = "flights"

    airline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("airlines.id"), nullable=False
    )
    flight_number: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_airport_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("airports.id"), nullable=False
    )
    destination_airport_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("airports.id"), nullable=False
    )
    departure_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    arrival_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    aircraft_type: Mapped[str | None] = mapped_column(String(50))
    cabin_class: Mapped[CabinClass] = mapped_column(nullable=False)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[DataSource] = mapped_column(nullable=False)
    stops: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Relationships
    airline: Mapped[Airline] = relationship(back_populates="flights")
    origin_airport: Mapped[Airport] = relationship(foreign_keys=[origin_airport_id])
    destination_airport: Mapped[Airport] = relationship(
        foreign_keys=[destination_airport_id]
    )
    prices: Mapped[list[Price]] = relationship(back_populates="flight")

    __table_args__ = (
        Index("ix_flights_airline_id", "airline_id"),
        Index(
            "ix_flights_origin_destination",
            "origin_airport_id",
            "destination_airport_id",
        ),
        Index("ix_flights_departure_time", "departure_time"),
        Index("ix_flights_source", "source"),
        Index("ix_flights_crawled_at", "crawled_at"),
    )

    def __repr__(self) -> str:
        return f"<Flight {self.flight_number} ({self.source.value})>"
