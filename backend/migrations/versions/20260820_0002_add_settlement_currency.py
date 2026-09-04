"""Add currency to settlements for safe multi-source ingestion.

Revision ID: 20260820_0002
Revises: 20260820_0001
Create Date: 2026-08-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0002"
down_revision: str | None = "20260820_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settlements",
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
    )
    op.alter_column("settlements", "currency", server_default=None)


def downgrade() -> None:
    op.drop_column("settlements", "currency")
