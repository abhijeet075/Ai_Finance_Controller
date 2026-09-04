"""Explainable 7, 14, and 30-day cash forecasts from persisted finance records."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import BankTransaction, Invoice, Settlement

ZERO = Decimal("0.00")
VALID_HORIZONS = (7, 14, 30)


def build_cash_forecast(
    session: Session,
    horizon_days: int,
    source_batch: str | None = None,
    currency: str | None = None,
    as_of_date: date | None = None,
) -> dict[str, object]:
    if horizon_days not in VALID_HORIZONS:
        raise ValueError("horizon_days must be one of 7, 14, or 30")
    as_of = as_of_date or date.today()
    end_date = as_of + timedelta(days=horizon_days)
    currency_was_inferred = currency is None
    if currency is None:
        currency_filters = []
        if source_batch:
            currency_filters.append(
                BankTransaction.source_batch == source_batch
            )
        currency = session.scalar(
            select(BankTransaction.currency)
            .where(*currency_filters)
            .group_by(BankTransaction.currency)
            .order_by(func.count(BankTransaction.id).desc())
            .limit(1)
        ) or "USD"
    currency = currency.upper()
    common = [BankTransaction.currency == currency]
    if source_batch:
        common.append(BankTransaction.source_batch == source_batch)
    credits = session.scalar(
        select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
            *common,
            BankTransaction.transaction_type == "credit",
            BankTransaction.transaction_date <= as_of,
        )
    ) or ZERO
    debits = session.scalar(
        select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
            *common,
            BankTransaction.transaction_type == "debit",
            BankTransaction.transaction_date <= as_of,
        )
    ) or ZERO
    current_cash = Decimal(credits) - Decimal(debits)

    invoice_filters = [
        Invoice.currency == currency,
        Invoice.status.in_(("open", "partial", "overdue")),
        Invoice.due_date > as_of,
        Invoice.due_date <= end_date,
    ]
    settlement_filters = [
        Settlement.currency == currency,
        Settlement.status == "pending",
        Settlement.transaction_date > as_of,
        Settlement.transaction_date <= end_date,
    ]
    expense_filters = [
        BankTransaction.currency == currency,
        BankTransaction.transaction_type == "debit",
        BankTransaction.transaction_date > as_of,
        BankTransaction.transaction_date <= end_date,
    ]
    if source_batch:
        invoice_filters.append(Invoice.source_batch == source_batch)
        settlement_filters.append(Settlement.source_batch == source_batch)
        expense_filters.append(BankTransaction.source_batch == source_batch)

    receipts_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    receipt_query = select(Invoice.due_date, Invoice.amount).where(
        *invoice_filters
    )
    for due, amount in session.execute(receipt_query):
        receipts_by_date[due] += Decimal(amount)
    pending_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    pending_query = select(
        Settlement.transaction_date,
        Settlement.amount,
    ).where(*settlement_filters)
    for tx_date, amount in session.execute(pending_query):
        pending_by_date[tx_date] += Decimal(amount)
    expenses_by_date: dict[date, Decimal] = defaultdict(lambda: ZERO)
    expense_query = select(
        BankTransaction.transaction_date,
        BankTransaction.amount,
    ).where(*expense_filters)
    for tx_date, amount in session.execute(expense_query):
        expenses_by_date[tx_date] += Decimal(amount)

    running = current_cash
    series = []
    for offset in range(1, horizon_days + 1):
        day = as_of + timedelta(days=offset)
        receipts = receipts_by_date[day]
        expenses = expenses_by_date[day]
        pending = pending_by_date[day]
        running = running + receipts - expenses - pending
        series.append({
            "date": day,
            "expected_receipts": receipts,
            "expected_expenses": expenses,
            "pending_settlements": pending,
            "projected_cash": running,
        })
    return {
        "horizon_days": horizon_days,
        "as_of_date": as_of,
        "source_batch": source_batch,
        "currency": currency,
        "current_cash": current_cash,
        "expected_receipts": sum(receipts_by_date.values(), ZERO),
        "expected_expenses": sum(expenses_by_date.values(), ZERO),
        "pending_settlements": sum(pending_by_date.values(), ZERO),
        "projected_cash": running,
        "series": series,
        "assumptions": [
            "Current cash equals posted credits less posted debits through the as-of date.",
            "Open, partial, and overdue invoices are expected receipts on their due date.",
            "Future dated debits are expected expenses.",
            "Pending settlements are deducted until confirmed completed.",
        ]
        + (
            [f"Currency {currency} was inferred from the source batch."]
            if currency_was_inferred
            else []
        ),
    }
