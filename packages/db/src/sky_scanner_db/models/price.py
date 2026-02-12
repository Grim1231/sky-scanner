"""Price model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from .flight import Flight


class Price(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Prices table - stores price history for flights."""

    __tablename__ = "prices"

    flight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flights.id"), nullable=False
    )
    price_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KRW")
    fare_class: Mapped[str | None] = mapped_column(String(5))
    includes_baggage: Mapped[bool] = mapped_column(Boolean, default=False)
    includes_meal: Mapped[bool] = mapped_column(Boolean, default=False)
    seat_selection_included: Mapped[bool] = mapped_column(Boolean, default=False)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    booking_url: Mapped[str | None] = mapped_column(String(1000))

    # Relationships
    flight: Mapped[Flight] = relationship(back_populates="prices")

    __table_args__ = (
        Index("ix_prices_flight_id", "flight_id"),
        Index("ix_prices_crawled_at", "crawled_at"),
        Index("ix_prices_amount_currency", "price_amount", "currency"),
    )

    def __repr__(self) -> str:
        return f"<Price {self.price_amount} {self.currency}>"
