"""User and user preferences models."""

from __future__ import annotations

import enum
import uuid  # noqa: TC003
from datetime import datetime, time  # noqa: TC003
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .flight import CabinClass  # noqa: TC001

if TYPE_CHECKING:
    from .search import PriceAlert, SearchHistory


class Alliance(enum.StrEnum):
    """Airline alliance for user preference."""

    STAR = "Star"
    ONEWORLD = "Oneworld"
    SKYTEAM = "SkyTeam"
    NONE = "None"


class Priority(enum.StrEnum):
    """User priority for flight selection."""

    PRICE = "PRICE"
    TIME = "TIME"
    COMFORT = "COMFORT"
    BALANCED = "BALANCED"


class User(UUIDPrimaryKeyMixin, Base):
    """Users table."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    preferences: Mapped[UserPreference | None] = relationship(
        back_populates="user", uselist=False
    )
    search_history: Mapped[list[SearchHistory]] = relationship(back_populates="user")
    price_alerts: Mapped[list[PriceAlert]] = relationship(back_populates="user")

    __table_args__ = (Index("ix_users_email", "email"),)

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class UserPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """User preferences table - personalization profile."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    min_seat_pitch: Mapped[float | None] = mapped_column(Float)
    min_seat_width: Mapped[float | None] = mapped_column(Float)
    preferred_departure_time_start: Mapped[time | None] = mapped_column(Time)
    preferred_departure_time_end: Mapped[time | None] = mapped_column(Time)
    preferred_days: Mapped[dict | None] = mapped_column(JSONB)
    max_layover_hours: Mapped[int | None] = mapped_column(Integer)
    max_stops: Mapped[int | None] = mapped_column(Integer)
    preferred_alliance: Mapped[Alliance | None] = mapped_column()
    preferred_airlines: Mapped[dict | None] = mapped_column(JSONB)
    excluded_airlines: Mapped[dict | None] = mapped_column(JSONB)
    baggage_required: Mapped[bool] = mapped_column(Boolean, default=False)
    meal_required: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_cabin_class: Mapped[CabinClass | None] = mapped_column()
    priority: Mapped[Priority] = mapped_column(default=Priority.BALANCED)
    notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    user: Mapped[User] = relationship(back_populates="preferences")

    __table_args__ = (Index("ix_user_preferences_user_id", "user_id"),)

    def __repr__(self) -> str:
        return f"<UserPreference user_id={self.user_id}>"
