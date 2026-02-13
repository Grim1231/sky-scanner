"""add flight stops column

Revision ID: b4c8d2e5f6a3
Revises: a3b7c9d1e4f2
Create Date: 2026-02-13 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c8d2e5f6a3"
down_revision: str | Sequence[str] | None = "a3b7c9d1e4f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add stops column to flights table."""
    op.add_column(
        "flights", sa.Column("stops", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    """Remove stops column from flights table."""
    op.drop_column("flights", "stops")
