"""add user password_hash

Revision ID: a3b7c9d1e4f2
Revises: 10d205e86221
Create Date: 2026-02-13 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b7c9d1e4f2"
down_revision: str | Sequence[str] | None = "10d205e86221"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add password_hash column to users table."""
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    """Remove password_hash column from users table."""
    op.drop_column("users", "password_hash")
