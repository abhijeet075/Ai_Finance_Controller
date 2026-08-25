from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

MONEY_PRECISION = 18
MONEY_SCALE = 2
CONFIDENCE_PRECISION = 5
CONFIDENCE_SCALE = 2


def new_id() -> str:
    return str(uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BankTransaction(Base, TimestampMixin):
    __tablename__ = "bank_transactions"
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('credit', 'debit')",
            name="ck_bank_transactions_transaction_type",
        ),
        Index("ix_bank_transactions_date_amount", "transaction_date", "amount"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(255), index=True)
    account_number: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(16), index=True, nullable=False)


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'partial', 'paid', 'overdue', 'cancelled')",
            name="ck_invoices_status",
        ),
        UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
        Index("ix_invoices_customer_due_date", "customer", "due_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invoice_number: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    customer: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)


class Settlement(Base, TimestampMixin):
    __tablename__ = "settlements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'reversed')",
            name="ck_settlements_status",
        ),
        UniqueConstraint(
            "settlement_reference", name="uq_settlements_settlement_reference"
        ),
        Index("ix_settlements_processor_date", "processor", "transaction_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    settlement_reference: Mapped[str] = mapped_column(
        String(128), index=True, nullable=False
    )
    transaction_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False
    )
    currency: Mapped[str] = mapped_column(
    String(3), index=True, nullable=False
    )
    processor: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    customer: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_reconciliation_results_confidence",
        ),
        CheckConstraint(
            "status IN ('matched', 'review', 'exception')",
            name="ck_reconciliation_results_status",
        ),
        Index("ix_reconciliation_results_status_confidence", "status", "confidence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bank_transaction_id: Mapped[str] = mapped_column(
        ForeignKey("bank_transactions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    invoice_id: Mapped[str | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="SET NULL"), index=True
    )
    settlement_id: Mapped[str | None] = mapped_column(
        ForeignKey("settlements.id", ondelete="SET NULL"), index=True
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(CONFIDENCE_PRECISION, CONFIDENCE_SCALE), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExceptionRecord(Base, TimestampMixin):
    __tablename__ = "exceptions"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_exceptions_confidence",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_exceptions_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'in_review', 'resolved', 'dismissed')",
            name="ck_exceptions_status",
        ),
        Index("ix_exceptions_status_severity", "status", "severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("bank_transactions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    exception_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(CONFIDENCE_PRECISION, CONFIDENCE_SCALE), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)


class CashForecast(Base):
    __tablename__ = "cash_forecasts"
    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'critical')",
            name="ck_cash_forecasts_risk_level",
        ),
        UniqueConstraint("forecast_date", name="uq_cash_forecasts_forecast_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    forecast_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False
    )
    expected_receipts: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False
    )
    expected_expenses: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False
    )
    pending_settlements: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False
    )
    projected_balance: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False
    )
    risk_level: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
