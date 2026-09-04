"""Add batch-aware reconciliation orchestration.

Revision ID: 20260831_0003
Revises: 20260820_0002
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0003"
down_revision: str | None = "20260820_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("bank_transactions", "invoices", "settlements"):
        op.add_column(
            table,
            sa.Column("source_batch", sa.String(128), nullable=False, server_default="default"),
        )
        op.create_index(f"ix_{table}_source_batch", table, ["source_batch"])
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_batch", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("records_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exception_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("match_rate", sa.Numeric(7, 6), nullable=False, server_default="0"),
        sa.Column("processing_time_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_per_second", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column(
            "full_cartesian_comparisons", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "candidate_records_examined", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("comparison_reduction", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_reconciliation_runs_source_batch", "reconciliation_runs", ["source_batch"])
    op.create_index("ix_reconciliation_runs_status", "reconciliation_runs", ["status"])
    op.add_column(
        "reconciliation_results",
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("reconciliation_runs.id", ondelete="CASCADE"),
        ),
    )
    op.create_index("ix_reconciliation_results_run_id", "reconciliation_results", ["run_id"])
    op.create_unique_constraint(
        "uq_reconciliation_results_run_bank",
        "reconciliation_results",
        ["run_id", "bank_transaction_id"],
    )
    op.create_unique_constraint(
        "uq_reconciliation_results_run_invoice",
        "reconciliation_results",
        ["run_id", "invoice_id"],
    )
    op.create_unique_constraint(
        "uq_reconciliation_results_run_settlement",
        "reconciliation_results",
        ["run_id", "settlement_id"],
    )
    op.add_column(
        "exceptions",
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("reconciliation_runs.id", ondelete="CASCADE"),
        ),
    )
    op.create_index("ix_exceptions_run_id", "exceptions", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_exceptions_run_id", table_name="exceptions")
    op.drop_column("exceptions", "run_id")
    for name in (
        "uq_reconciliation_results_run_settlement",
        "uq_reconciliation_results_run_invoice",
        "uq_reconciliation_results_run_bank",
    ):
        op.drop_constraint(name, "reconciliation_results", type_="unique")
    op.drop_index("ix_reconciliation_results_run_id", table_name="reconciliation_results")
    op.drop_column("reconciliation_results", "run_id")
    op.drop_table("reconciliation_runs")
    for table in ("settlements", "invoices", "bank_transactions"):
        op.drop_index(f"ix_{table}_source_batch", table_name=table)
        op.drop_column(table, "source_batch")
