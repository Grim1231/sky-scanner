"""Search history and price alert models."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import date, datetime  # noqa: TC003
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .flight import CabinClass

if TYPE_CHECKING:
    from .user import User


class SearchHistory(UUIDPrimaryKeyMixin, Base):
    """Search history table - tracks user searches."""

    __tablename__ = "search_history"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[date | None] = mapped_column(Date)
    passengers: Mapped[int] = mapped_column(Integer, default=1)
    cabin_class: Mapped[CabinClass] = mapped_column(default=CabinClass.ECONOMY)
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    results_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    user: Mapped[User] = relationship(back_populates="search_history")

    __table_args__ = (
        Index("ix_search_history_user_id", "user_id"),
        Index("ix_search_history_route", "origin", "destination"),
        Index("ix_search_history_searched_at", "searched_at"),
    )

    def __repr__(self) -> str:
        return f"<SearchHistory {self.origin}-{self.destination}>"


class PriceAlert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Price alerts table - user-configured price notifications."""

    __tablename__ = "price_alerts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[date | None] = mapped_column(Date)
    target_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    current_best_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    user: Mapped[User] = relationship(back_populates="price_alerts")

    __table_args__ = (
        Index("ix_price_alerts_user_id", "user_id"),
        Index("ix_price_alerts_active", "is_active"),
        Index("ix_price_alerts_route", "origin", "destination"),
    )

    def __repr__(self) -> str:
        return (
            f"<PriceAlert {self.origin}-{self.destination} target={self.target_price}>"
        )
