"""Add Phase 12 run lifecycle and timing fields.

Revision ID: 20260902_0005
Revises: 20260831_0004
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0005"
down_revision: str | None = "20260831_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_RUN_ID = "00000000-0000-0000-0000-000000000012"


def upgrade() -> None:
    op.add_column(
        "reconciliation_runs",
        sa.Column("started_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "reconciliation_runs",
        sa.Column("error_message", sa.Text()),
    )
    for name in ("matching_time_ms", "decision_time_ms", "persistence_time_ms"):
        op.add_column(
            "reconciliation_runs",
            sa.Column(name, sa.Integer(), nullable=False, server_default="0"),
        )
    op.execute(
        "UPDATE reconciliation_runs SET started_at = created_at "
        "WHERE started_at IS NULL AND status IN ('running', 'completed')"
    )
    op.execute(
        f"""
        INSERT INTO reconciliation_runs (
            id, source_batch, status, records_processed, matched_count,
            review_count, exception_count, match_rate, processing_time_ms,
            records_per_second, full_cartesian_comparisons,
            candidate_records_examined, comparison_reduction, created_at,
            started_at, completed_at
        )
        SELECT '{LEGACY_RUN_ID}', 'legacy', 'completed',
            (SELECT COUNT(*) FROM reconciliation_results WHERE run_id IS NULL),
            (SELECT COUNT(*) FROM reconciliation_results
                WHERE run_id IS NULL AND status = 'matched'),
            (SELECT COUNT(*) FROM reconciliation_results
                WHERE run_id IS NULL AND status = 'review'),
            (SELECT COUNT(*) FROM reconciliation_results
                WHERE run_id IS NULL AND status = 'exception'),
            0, 0, 0, 0, 0, 0, CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE EXISTS (
            SELECT 1 FROM reconciliation_results WHERE run_id IS NULL
            UNION ALL
            SELECT 1 FROM exceptions WHERE run_id IS NULL
        )
        """
    )
    op.execute(
        f"UPDATE reconciliation_results SET run_id = '{LEGACY_RUN_ID}' "
        "WHERE run_id IS NULL"
    )
    op.execute(
        f"UPDATE exceptions SET run_id = '{LEGACY_RUN_ID}' WHERE run_id IS NULL"
    )
    op.alter_column("reconciliation_results", "run_id", nullable=False)
    op.alter_column("exceptions", "run_id", nullable=False)
    op.create_check_constraint(
        "ck_reconciliation_runs_status",
        "reconciliation_runs",
        "status IN ('pending', 'running', 'completed', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_reconciliation_runs_status",
        "reconciliation_runs",
        type_="check",
    )
    op.alter_column("exceptions", "run_id", nullable=True)
    op.alter_column("reconciliation_results", "run_id", nullable=True)
    op.execute(
        f"UPDATE exceptions SET run_id = NULL WHERE run_id = '{LEGACY_RUN_ID}'"
    )
    op.execute(
        "UPDATE reconciliation_results SET run_id = NULL "
        f"WHERE run_id = '{LEGACY_RUN_ID}'"
    )
    op.execute(
        f"DELETE FROM reconciliation_runs WHERE id = '{LEGACY_RUN_ID}'"
    )
    for name in (
        "persistence_time_ms",
        "decision_time_ms",
        "matching_time_ms",
        "error_message",
        "started_at",
    ):
        op.drop_column("reconciliation_runs", name)
