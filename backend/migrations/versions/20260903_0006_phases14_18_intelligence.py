"""Phases 14-18 forecasting, intelligence, and audit controls.

Revision ID: 20260903_0006
Revises: 20260902_0005
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0006"
down_revision: str | None = "20260902_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(36)),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column(
            "detail_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_audit_logs_created_at",
        "audit_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_audit_logs_resource",
        "audit_logs",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audit_logs_resource",
        table_name="audit_logs",
    )
    op.drop_index(
        "ix_audit_logs_created_at",
        table_name="audit_logs",
    )
    op.drop_table("audit_logs")
