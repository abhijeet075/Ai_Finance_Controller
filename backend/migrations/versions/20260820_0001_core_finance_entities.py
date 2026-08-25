"""Create the six core finance entities.

Revision ID: 20260820_0001
Revises: None
Create Date: 2026-08-20
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260820_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("reference", sa.String(255)),
        sa.Column("account_number", sa.String(128), nullable=False),
        sa.Column("transaction_type", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("transaction_type IN ('credit', 'debit')", name="ck_bank_transactions_transaction_type"),
    )
    op.create_index("ix_bank_transactions_transaction_date", "bank_transactions", ["transaction_date"])
    op.create_index("ix_bank_transactions_reference", "bank_transactions", ["reference"])
    op.create_index("ix_bank_transactions_account_number", "bank_transactions", ["account_number"])
    op.create_index("ix_bank_transactions_transaction_type", "bank_transactions", ["transaction_type"])
    op.create_index("ix_bank_transactions_date_amount", "bank_transactions", ["transaction_date", "amount"])

    op.create_table(
        "invoices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_number", sa.String(128), nullable=False),
        sa.Column("customer", sa.String(255), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('open', 'partial', 'paid', 'overdue', 'cancelled')", name="ck_invoices_status"),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
    )
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"])
    op.create_index("ix_invoices_customer", "invoices", ["customer"])
    op.create_index("ix_invoices_due_date", "invoices", ["due_date"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_customer_due_date", "invoices", ["customer", "due_date"])

    op.create_table(
        "settlements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("settlement_reference", sa.String(128), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("processor", sa.String(128), nullable=False),
        sa.Column("customer", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'completed', 'failed', 'reversed')", name="ck_settlements_status"),
        sa.UniqueConstraint("settlement_reference", name="uq_settlements_settlement_reference"),
    )
    op.create_index("ix_settlements_settlement_reference", "settlements", ["settlement_reference"])
    op.create_index("ix_settlements_transaction_date", "settlements", ["transaction_date"])
    op.create_index("ix_settlements_processor", "settlements", ["processor"])
    op.create_index("ix_settlements_customer", "settlements", ["customer"])
    op.create_index("ix_settlements_status", "settlements", ["status"])
    op.create_index("ix_settlements_processor_date", "settlements", ["processor", "transaction_date"])

    op.create_table(
        "reconciliation_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bank_transaction_id", sa.String(36), sa.ForeignKey("bank_transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id", ondelete="SET NULL")),
        sa.Column("settlement_id", sa.String(36), sa.ForeignKey("settlements.id", ondelete="SET NULL")),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_reconciliation_results_confidence"),
        sa.CheckConstraint("status IN ('matched', 'review', 'exception')", name="ck_reconciliation_results_status"),
    )
    for column in ("bank_transaction_id", "invoice_id", "settlement_id", "status"):
        op.create_index(f"ix_reconciliation_results_{column}", "reconciliation_results", [column])
    op.create_index("ix_reconciliation_results_status_confidence", "reconciliation_results", ["status", "confidence"])

    op.create_table(
        "exceptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("bank_transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exception_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_exceptions_confidence"),
        sa.CheckConstraint("severity IN ('info', 'warning', 'critical')", name="ck_exceptions_severity"),
        sa.CheckConstraint("status IN ('open', 'in_review', 'resolved', 'dismissed')", name="ck_exceptions_status"),
    )
    for column in ("transaction_id", "exception_type", "severity", "status"):
        op.create_index(f"ix_exceptions_{column}", "exceptions", [column])
    op.create_index("ix_exceptions_status_severity", "exceptions", ["status", "severity"])

    op.create_table(
        "cash_forecasts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("opening_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("expected_receipts", sa.Numeric(18, 2), nullable=False),
        sa.Column("expected_expenses", sa.Numeric(18, 2), nullable=False),
        sa.Column("pending_settlements", sa.Numeric(18, 2), nullable=False),
        sa.Column("projected_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("risk_level IN ('low', 'medium', 'high', 'critical')", name="ck_cash_forecasts_risk_level"),
        sa.UniqueConstraint("forecast_date", name="uq_cash_forecasts_forecast_date"),
    )
    op.create_index("ix_cash_forecasts_forecast_date", "cash_forecasts", ["forecast_date"])
    op.create_index("ix_cash_forecasts_risk_level", "cash_forecasts", ["risk_level"])


def downgrade() -> None:
    op.drop_table("cash_forecasts")
    op.drop_table("exceptions")
    op.drop_table("reconciliation_results")
    op.drop_table("settlements")
    op.drop_table("invoices")
    op.drop_table("bank_transactions")
