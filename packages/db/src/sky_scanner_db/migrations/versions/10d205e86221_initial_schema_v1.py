"""initial schema v1

Revision ID: 10d205e86221
Revises:
Create Date: 2026-02-13 04:25:55.534589

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "10d205e86221"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all tables for initial schema v1."""

    # -- airlines --
    op.create_table(
        "airlines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(2), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "type",
            sa.Enum("FSC", "LCC", "ULCC", name="airlinetype", create_type=True),
            nullable=False,
        ),
        sa.Column(
            "alliance",
            sa.Enum(
                "Star", "Oneworld", "SkyTeam", "None", name="alliance", create_type=True
            ),
            nullable=False,
        ),
        sa.Column("base_country", sa.String(100), nullable=False),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_airlines_code", "airlines", ["code"])

    # -- airports --
    op.create_table(
        "airports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(3), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("city", sa.String(255), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_airports_code", "airports", ["code"])
    op.create_index("ix_airports_city", "airports", ["city"])
    op.create_index("ix_airports_country", "airports", ["country"])

    # -- flights --
    op.create_table(
        "flights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "airline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("airlines.id"),
            nullable=False,
        ),
        sa.Column("flight_number", sa.String(10), nullable=False),
        sa.Column(
            "origin_airport_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("airports.id"),
            nullable=False,
        ),
        sa.Column(
            "destination_airport_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("airports.id"),
            nullable=False,
        ),
        sa.Column("departure_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("aircraft_type", sa.String(50), nullable=True),
        sa.Column(
            "cabin_class",
            sa.Enum(
                "ECONOMY",
                "PREMIUM_ECONOMY",
                "BUSINESS",
                "FIRST",
                name="cabinclass",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "GOOGLE_PROTOBUF",
                "KIWI_API",
                "DIRECT_CRAWL",
                "GDS",
                name="datasource",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_flights_airline_id", "flights", ["airline_id"])
    op.create_index(
        "ix_flights_origin_destination",
        "flights",
        ["origin_airport_id", "destination_airport_id"],
    )
    op.create_index("ix_flights_departure_time", "flights", ["departure_time"])
    op.create_index("ix_flights_source", "flights", ["source"])
    op.create_index("ix_flights_crawled_at", "flights", ["crawled_at"])

    # -- prices --
    op.create_table(
        "prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "flight_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flights.id"),
            nullable=False,
        ),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("fare_class", sa.String(5), nullable=True),
        sa.Column(
            "includes_baggage", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "includes_meal", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "seat_selection_included",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("booking_url", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_prices_flight_id", "prices", ["flight_id"])
    op.create_index("ix_prices_crawled_at", "prices", ["crawled_at"])
    op.create_index("ix_prices_amount_currency", "prices", ["price_amount", "currency"])

    # -- seat_specs --
    op.create_table(
        "seat_specs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "airline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("airlines.id"),
            nullable=False,
        ),
        sa.Column("aircraft_type", sa.String(50), nullable=False),
        sa.Column(
            "cabin_class",
            sa.Enum(
                "ECONOMY",
                "PREMIUM_ECONOMY",
                "BUSINESS",
                "FIRST",
                name="cabinclass",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("seat_pitch_inches", sa.Float(), nullable=True),
        sa.Column("seat_width_inches", sa.Float(), nullable=True),
        sa.Column("recline_degrees", sa.Float(), nullable=True),
        sa.Column(
            "has_power_outlet", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("has_usb", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("has_ife", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_seat_specs_airline_id", "seat_specs", ["airline_id"])
    op.create_index(
        "ix_seat_specs_airline_aircraft_cabin",
        "seat_specs",
        ["airline_id", "aircraft_type", "cabin_class"],
        unique=True,
    )

    # -- users --
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # -- user_preferences --
    op.create_table(
        "user_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("min_seat_pitch", sa.Float(), nullable=True),
        sa.Column("min_seat_width", sa.Float(), nullable=True),
        sa.Column("preferred_departure_time_start", sa.Time(), nullable=True),
        sa.Column("preferred_departure_time_end", sa.Time(), nullable=True),
        sa.Column("preferred_days", postgresql.JSONB(), nullable=True),
        sa.Column("max_layover_hours", sa.Integer(), nullable=True),
        sa.Column("max_stops", sa.Integer(), nullable=True),
        sa.Column(
            "preferred_alliance",
            sa.Enum(
                "Star",
                "Oneworld",
                "SkyTeam",
                "None",
                name="alliance",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("preferred_airlines", postgresql.JSONB(), nullable=True),
        sa.Column("excluded_airlines", postgresql.JSONB(), nullable=True),
        sa.Column(
            "baggage_required", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "meal_required", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "preferred_cabin_class",
            sa.Enum(
                "ECONOMY",
                "PREMIUM_ECONOMY",
                "BUSINESS",
                "FIRST",
                name="cabinclass",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "priority",
            sa.Enum(
                "PRICE",
                "TIME",
                "COMFORT",
                "BALANCED",
                name="priority",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])

    # -- search_history --
    op.create_table(
        "search_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("origin", sa.String(3), nullable=False),
        sa.Column("destination", sa.String(3), nullable=False),
        sa.Column("departure_date", sa.Date(), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=True),
        sa.Column("passengers", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "cabin_class",
            sa.Enum(
                "ECONOMY",
                "PREMIUM_ECONOMY",
                "BUSINESS",
                "FIRST",
                name="cabinclass",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "searched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("results_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_search_history_user_id", "search_history", ["user_id"])
    op.create_index(
        "ix_search_history_route", "search_history", ["origin", "destination"]
    )
    op.create_index("ix_search_history_searched_at", "search_history", ["searched_at"])

    # -- price_alerts --
    op.create_table(
        "price_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("origin", sa.String(3), nullable=False),
        sa.Column("destination", sa.String(3), nullable=False),
        sa.Column("departure_date", sa.Date(), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=True),
        sa.Column("target_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("current_best_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_price_alerts_user_id", "price_alerts", ["user_id"])
    op.create_index("ix_price_alerts_active", "price_alerts", ["is_active"])
    op.create_index("ix_price_alerts_route", "price_alerts", ["origin", "destination"])

    # -- price_features (DA) --
    op.create_table(
        "price_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("route", sa.String(10), nullable=False),
        sa.Column(
            "airline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("airlines.id"),
            nullable=False,
        ),
        sa.Column("departure_date", sa.Date(), nullable=False),
        sa.Column("days_before_departure", sa.Integer(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("is_holiday", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("demand_index", sa.Float(), nullable=True),
        sa.Column("competitor_price_avg", sa.Numeric(12, 2), nullable=True),
        sa.Column("historical_avg_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("historical_min_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("seat_fill_rate", sa.Float(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_price_features_route", "price_features", ["route"])
    op.create_index("ix_price_features_airline_id", "price_features", ["airline_id"])
    op.create_index(
        "ix_price_features_departure_date", "price_features", ["departure_date"]
    )
    op.create_index("ix_price_features_recorded_at", "price_features", ["recorded_at"])

    # -- booking_time_analysis (DA) --
    op.create_table(
        "booking_time_analysis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("route", sa.String(10), nullable=False),
        sa.Column(
            "airline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("airlines.id"),
            nullable=False,
        ),
        sa.Column("optimal_days_before", sa.Integer(), nullable=False),
        sa.Column("price_at_optimal", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_at_30days", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_at_14days", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_at_7days", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_at_1day", sa.Numeric(12, 2), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_booking_time_route", "booking_time_analysis", ["route"])
    op.create_index(
        "ix_booking_time_airline_id", "booking_time_analysis", ["airline_id"]
    )
    op.create_index(
        "ix_booking_time_analyzed_at", "booking_time_analysis", ["analyzed_at"]
    )


def downgrade() -> None:
    """Drop all tables in reverse order."""
    op.drop_table("booking_time_analysis")
    op.drop_table("price_features")
    op.drop_table("price_alerts")
    op.drop_table("search_history")
    op.drop_table("user_preferences")
    op.drop_table("users")
    op.drop_table("seat_specs")
    op.drop_table("prices")
    op.drop_table("flights")
    op.drop_table("airports")
    op.drop_table("airlines")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS priority")
    op.execute("DROP TYPE IF EXISTS datasource")
    op.execute("DROP TYPE IF EXISTS cabinclass")
    op.execute("DROP TYPE IF EXISTS alliance")
    op.execute("DROP TYPE IF EXISTS airlinetype")
