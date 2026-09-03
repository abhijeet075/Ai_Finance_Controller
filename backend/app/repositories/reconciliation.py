"""Database access for reconciliation runs, results, and exceptions."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.finance import (
    BankTransaction,
    ExceptionRecord,
    Invoice,
    ReconciliationResult,
    ReconciliationRun,
    Settlement,
)


def load_source_batch(
    session: Session,
    source_batch: str,
) -> tuple[list[BankTransaction], list[Invoice], list[Settlement]]:
    def rows(model: type, order_column: object) -> list:
        return list(
            session.scalars(
                select(model)
                .where(model.source_batch == source_batch)
                .order_by(order_column)
            )
        )

    return (
        rows(BankTransaction, BankTransaction.id),
        rows(Invoice, Invoice.id),
        rows(Settlement, Settlement.id),
    )


def create_run(session: Session, source_batch: str) -> ReconciliationRun:
    run = ReconciliationRun(source_batch=source_batch, status="pending")
    session.add(run)
    session.flush()
    return run


def get_run(session: Session, run_id: str) -> ReconciliationRun | None:
    return session.get(ReconciliationRun, run_id)


def _paged(
    session: Session,
    statement: Select,
    count_statement: Select,
    page: int,
    page_size: int,
) -> tuple[list, int]:
    total = int(session.scalar(count_statement) or 0)
    items = list(
        session.scalars(
            statement.offset((page - 1) * page_size).limit(page_size)
        )
    )
    return items, total


def list_runs(
    session: Session,
    page: int,
    page_size: int,
    source_batch: str | None = None,
    status: str | None = None,
) -> tuple[list[ReconciliationRun], int]:
    filters = []
    if source_batch:
        filters.append(ReconciliationRun.source_batch == source_batch)
    if status:
        filters.append(ReconciliationRun.status == status)
    statement = (
        select(ReconciliationRun)
        .where(*filters)
        .order_by(ReconciliationRun.created_at.desc(), ReconciliationRun.id.desc())
    )
    count_statement = select(func.count(ReconciliationRun.id)).where(*filters)
    return _paged(session, statement, count_statement, page, page_size)


def list_results(
    session: Session,
    run_id: str,
    page: int,
    page_size: int,
    status: str | None = None,
) -> tuple[list[ReconciliationResult], int]:
    filters = [ReconciliationResult.run_id == run_id]
    if status:
        filters.append(ReconciliationResult.status == status)
    statement = (
        select(ReconciliationResult)
        .where(*filters)
        .order_by(ReconciliationResult.bank_transaction_id)
    )
    count_statement = select(func.count(ReconciliationResult.id)).where(*filters)
    return _paged(session, statement, count_statement, page, page_size)


def list_exceptions(
    session: Session,
    run_id: str,
    page: int,
    page_size: int,
    severity: str | None = None,
    exception_type: str | None = None,
    status: str | None = None,
) -> tuple[
    list[
        tuple[
            ExceptionRecord,
            ReconciliationResult,
            BankTransaction,
            Invoice | None,
            Settlement | None,
        ]
    ],
    int,
]:
    filters = [ExceptionRecord.run_id == run_id]
    if severity:
        filters.append(ExceptionRecord.severity == severity)
    if exception_type:
        filters.append(ExceptionRecord.exception_type == exception_type)
    if status:
        filters.append(ExceptionRecord.status == status)
    joins = (
        select(
            ExceptionRecord,
            ReconciliationResult,
            BankTransaction,
            Invoice,
            Settlement,
        )
        .join(
            ReconciliationResult,
            (ReconciliationResult.run_id == ExceptionRecord.run_id)
            & (
                ReconciliationResult.bank_transaction_id
                == ExceptionRecord.transaction_id
            ),
        )
        .join(BankTransaction, BankTransaction.id == ExceptionRecord.transaction_id)
        .outerjoin(Invoice, Invoice.id == ReconciliationResult.invoice_id)
        .outerjoin(Settlement, Settlement.id == ReconciliationResult.settlement_id)
        .where(*filters)
        .order_by(ExceptionRecord.created_at, ExceptionRecord.id)
    )
    total = int(
        session.scalar(select(func.count(ExceptionRecord.id)).where(*filters)) or 0
    )
    rows = list(
        session.execute(
            joins.offset((page - 1) * page_size).limit(page_size)
        ).tuples()
    )
    return rows, total


def save_results(
    session: Session,
    results: Sequence[ReconciliationResult],
) -> None:
    session.add_all(results)


def save_exceptions(
    session: Session,
    exceptions: Sequence[ExceptionRecord],
) -> None:
    session.add_all(exceptions)


def source_batch_counts(session: Session) -> list[dict[str, int | str]]:
    counts: dict[str, dict[str, int | str]] = {}
    mappings = (
        (BankTransaction, "bank_transactions"),
        (Invoice, "invoices"),
        (Settlement, "settlements"),
    )
    for model, key in mappings:
        statement = (
            select(model.source_batch, func.count(model.id))
            .group_by(model.source_batch)
            .order_by(model.source_batch)
        )
        for source_batch, count in session.execute(statement):
            item = counts.setdefault(
                source_batch,
                {
                    "source_batch": source_batch,
                    "bank_transactions": 0,
                    "invoices": 0,
                    "settlements": 0,
                },
            )
            item[key] = int(count)
    return [counts[key] for key in sorted(counts)]
