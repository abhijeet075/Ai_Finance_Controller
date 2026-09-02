"""Persist best-candidate evidence for Phase 11 exception reports.

Revision ID: 20260831_0004
Revises: 20260831_0003
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260831_0004"
down_revision: str | None = "20260831_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reconciliation_results",
        sa.Column("best_candidate_id", sa.String(36)),
    )
    op.add_column(
        "reconciliation_results",
        sa.Column("best_candidate_type", sa.String(16)),
    )
    op.add_column(
        "reconciliation_results",
        sa.Column("best_candidate_amount", sa.Numeric(18, 2)),
    )
    op.add_column(
        "reconciliation_results",
        sa.Column("amount_difference", sa.Numeric(18, 2)),
    )
    op.create_check_constraint(
        "ck_reconciliation_results_best_candidate_type",
        "reconciliation_results",
        "best_candidate_type IS NULL OR "
        "best_candidate_type IN ('invoice', 'settlement')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_reconciliation_results_best_candidate_type",
        "reconciliation_results",
        type_="check",
    )
    for column in (
        "amount_difference",
        "best_candidate_amount",
        "best_candidate_type",
        "best_candidate_id",
    ):
        op.drop_column("reconciliation_results", column)
