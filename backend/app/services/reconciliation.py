"""Database-backed reconciliation orchestration for one uploaded source batch."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import (
    BankTransaction,
    ExceptionRecord,
    Invoice,
    ReconciliationResult,
    ReconciliationRun,
    Settlement,
)
from app.services.baseline_reconciliation import BankRecord, InvoiceRecord
from app.services.candidate_matching import CandidateConfig, CandidateMatcher, SettlementRecord
from app.services.decision_engine import DecisionBatch, decide_reconciliation


class EmptySourceBatchError(ValueError):
    pass


class ReconciliationRunNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    source_batch: str
    status: str
    records_processed: int
    matched: int
    review: int
    exceptions: int
    match_rate: Decimal
    processing_time_ms: int
    records_per_second: Decimal
    full_cartesian_comparisons: int
    candidate_records_examined: int
    comparison_reduction: Decimal


@dataclass(frozen=True)
class ExceptionReportItem:
    transaction_id: str
    predicted_status: str
    exception_type: str
    best_candidate_id: str | None
    best_candidate_type: str | None
    confidence: Decimal
    reason: str
    bank_amount: Decimal
    candidate_amount: Decimal | None
    amount_difference: Decimal | None
    currency: str


def _to_domain(
    bank_rows: list[BankTransaction],
    invoice_rows: list[Invoice],
    settlement_rows: list[Settlement],
) -> tuple[list[BankRecord], list[InvoiceRecord], list[SettlementRecord]]:
    banks = [
        BankRecord(
            item.id,
            item.transaction_date,
            item.amount,
            item.currency,
            item.reference,
            item.description,
            transaction_type=item.transaction_type,
        )
        for item in bank_rows
    ]
    invoices = [
        InvoiceRecord(
            item.id,
            item.invoice_number,
            item.customer,
            item.invoice_date,
            item.amount,
            item.currency,
        )
        for item in invoice_rows
        if item.status != "cancelled"
    ]
    settlements = [
        SettlementRecord(
            item.id,
            item.settlement_reference,
            item.customer,
            item.transaction_date,
            item.amount,
            item.currency,
            item.processor,
            item.status,
        )
        for item in settlement_rows
    ]
    return banks, invoices, settlements


def _summary(run: ReconciliationRun) -> RunSummary:
    return RunSummary(
        run.id,
        run.source_batch,
        run.status,
        run.records_processed,
        run.matched_count,
        run.review_count,
        run.exception_count,
        run.match_rate,
        run.processing_time_ms,
        run.records_per_second,
        run.full_cartesian_comparisons,
        run.candidate_records_examined,
        run.comparison_reduction,
    )


def _persist_decisions(
    session: Session,
    run: ReconciliationRun,
    batch: DecisionBatch,
) -> None:
    for decision in batch.decisions:
        session.add(
            ReconciliationResult(
                run_id=run.id,
                bank_transaction_id=decision.bank_transaction_id,
                invoice_id=decision.invoice_id,
                settlement_id=decision.settlement_id,
                confidence=decision.confidence,
                status=decision.status,
                reason=decision.reason,
                best_candidate_id=decision.best_candidate_id,
                best_candidate_type=decision.best_candidate_type,
                best_candidate_amount=decision.best_candidate_amount,
                amount_difference=decision.amount_difference,
            )
        )
        if decision.exception_type:
            session.add(
                ExceptionRecord(
                    run_id=run.id,
                    transaction_id=decision.bank_transaction_id,
                    exception_type=decision.exception_type,
                    severity=decision.severity or "warning",
                    description=decision.reason,
                    recommended_action=decision.recommended_action or "Review manually.",
                    confidence=decision.confidence,
                    status="in_review" if decision.status == "review" else "open",
                )
            )


def run_reconciliation(
    session: Session,
    source_batch: str,
    config: CandidateConfig | None = None,
) -> RunSummary:
    """Load, match, globally assign, classify, and atomically persist one batch."""
    started = perf_counter()
    bank_rows = list(
        session.scalars(
            select(BankTransaction)
            .where(BankTransaction.source_batch == source_batch)
            .order_by(BankTransaction.id)
        )
    )
    if not bank_rows:
        raise EmptySourceBatchError(f"No bank transactions found for batch '{source_batch}'.")
    invoice_rows = list(
        session.scalars(
            select(Invoice)
            .where(Invoice.source_batch == source_batch)
            .order_by(Invoice.id)
        )
    )
    settlement_rows = list(
        session.scalars(
            select(Settlement)
            .where(Settlement.source_batch == source_batch)
            .order_by(Settlement.id)
        )
    )
    banks, invoices, settlements = _to_domain(bank_rows, invoice_rows, settlement_rows)
    candidate_batch = CandidateMatcher(invoices, settlements, config).match_batch(banks)
    decision_batch = decide_reconciliation(candidate_batch, banks, invoices, settlements)
    records_processed = len(decision_batch.decisions)
    match_rate = (
        Decimal(decision_batch.matched) / Decimal(records_processed)
    ).quantize(Decimal("0.000001"))
    run = ReconciliationRun(
        source_batch=source_batch,
        status="running",
        records_processed=records_processed,
        matched_count=decision_batch.matched,
        review_count=decision_batch.review,
        exception_count=decision_batch.exceptions,
        match_rate=match_rate,
        processing_time_ms=0,
        records_per_second=Decimal("0"),
        full_cartesian_comparisons=candidate_batch.full_cartesian_comparisons,
        candidate_records_examined=candidate_batch.examined_records,
        comparison_reduction=candidate_batch.comparison_reduction_percent,
    )
    try:
        session.add(run)
        session.flush()
        _persist_decisions(session, run, decision_batch)
        session.flush()
        elapsed = max(perf_counter() - started, 0.000001)
        run.processing_time_ms = max(1, round(elapsed * 1000))
        run.records_per_second = (
            Decimal(records_processed) / Decimal(str(elapsed))
        ).quantize(Decimal("0.01"))
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return _summary(run)


def get_run_summary(session: Session, run_id: str) -> RunSummary:
    run = session.get(ReconciliationRun, run_id)
    if run is None:
        raise ReconciliationRunNotFoundError(f"Reconciliation run '{run_id}' was not found.")
    return _summary(run)


def export_predictions_csv(session: Session, run_id: str) -> str:
    if session.get(ReconciliationRun, run_id) is None:
        raise ReconciliationRunNotFoundError(f"Reconciliation run '{run_id}' was not found.")
    rows = list(
        session.scalars(
            select(ReconciliationResult)
            .where(ReconciliationResult.run_id == run_id)
            .order_by(ReconciliationResult.bank_transaction_id)
        )
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "transaction_id",
            "invoice_id",
            "settlement_id",
            "predicted_status",
        ),
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "transaction_id": row.bank_transaction_id,
                "invoice_id": row.invoice_id or "",
                "settlement_id": row.settlement_id or "",
                "predicted_status": row.status,
            }
        )
    return output.getvalue()


def get_exception_report(
    session: Session,
    run_id: str,
) -> tuple[ExceptionReportItem, ...]:
    if session.get(ReconciliationRun, run_id) is None:
        raise ReconciliationRunNotFoundError(f"Reconciliation run '{run_id}' was not found.")
    results = list(
        session.scalars(
            select(ReconciliationResult)
            .where(
                ReconciliationResult.run_id == run_id,
                ReconciliationResult.status != "matched",
            )
            .order_by(ReconciliationResult.bank_transaction_id)
        )
    )
    transaction_ids = [item.bank_transaction_id for item in results]
    banks = {
        item.id: item
        for item in session.scalars(
            select(BankTransaction).where(BankTransaction.id.in_(transaction_ids))
        )
    }
    exceptions = {
        item.transaction_id: item
        for item in session.scalars(
            select(ExceptionRecord)
            .where(ExceptionRecord.run_id == run_id)
            .order_by(ExceptionRecord.transaction_id, ExceptionRecord.id)
        )
    }
    report = []
    for result in results:
        bank = banks[result.bank_transaction_id]
        exception = exceptions.get(result.bank_transaction_id)
        report.append(
            ExceptionReportItem(
                transaction_id=result.bank_transaction_id,
                predicted_status=result.status,
                exception_type=exception.exception_type if exception else "unclassified",
                best_candidate_id=result.best_candidate_id,
                best_candidate_type=result.best_candidate_type,
                confidence=(result.confidence / Decimal("100")).quantize(
                    Decimal("0.0001")
                ),
                reason=result.reason,
                bank_amount=bank.amount,
                candidate_amount=result.best_candidate_amount,
                amount_difference=result.amount_difference,
                currency=bank.currency,
            )
        )
    return tuple(report)


def export_exception_report_csv(session: Session, run_id: str) -> str:
    rows = get_exception_report(session, run_id)
    output = io.StringIO(newline="")
    fieldnames = tuple(ExceptionReportItem.__dataclass_fields__)
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for item in rows:
        writer.writerow(item.__dict__)
    return output.getvalue()
