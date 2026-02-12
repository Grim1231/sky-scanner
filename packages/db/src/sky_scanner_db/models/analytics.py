"""Analytics models for DA (Data Analysis) tables."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    import uuid
    from datetime import date, datetime


class PriceFeature(UUIDPrimaryKeyMixin, Base):
    """Price features table - features for price prediction models."""

    __tablename__ = "price_features"

    route: Mapped[str] = mapped_column(String(10), nullable=False)
    airline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("airlines.id"), nullable=False
    )
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    days_before_departure: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False)
    demand_index: Mapped[float | None] = mapped_column(Float)
    competitor_price_avg: Mapped[float | None] = mapped_column(Numeric(12, 2))
    historical_avg_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    historical_min_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    seat_fill_rate: Mapped[float | None] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_price_features_route", "route"),
        Index("ix_price_features_airline_id", "airline_id"),
        Index("ix_price_features_departure_date", "departure_date"),
        Index("ix_price_features_recorded_at", "recorded_at"),
    )

    def __repr__(self) -> str:
        return f"<PriceFeature {self.route} days_before={self.days_before_departure}>"


class BookingTimeAnalysis(UUIDPrimaryKeyMixin, Base):
    """Booking time analysis table - optimal purchase timing from DA."""

    __tablename__ = "booking_time_analysis"

    route: Mapped[str] = mapped_column(String(10), nullable=False)
    airline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("airlines.id"), nullable=False
    )
    optimal_days_before: Mapped[int] = mapped_column(Integer, nullable=False)
    price_at_optimal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    price_at_30days: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_at_14days: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_at_7days: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_at_1day: Mapped[float | None] = mapped_column(Numeric(12, 2))
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_booking_time_route", "route"),
        Index("ix_booking_time_airline_id", "airline_id"),
        Index("ix_booking_time_analyzed_at", "analyzed_at"),
    )

    def __repr__(self) -> str:
        return f"<BookingTimeAnalysis {self.route} optimal={self.optimal_days_before}d>"
