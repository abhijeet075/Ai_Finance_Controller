"""Central orchestration and read services for reconciliation runs."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter

from sqlalchemy.orm import Session

from app.models.finance import (
    BankTransaction,
    ExceptionRecord,
    Invoice,
    ReconciliationResult,
    ReconciliationRun,
    Settlement,
)
from app.repositories import reconciliation as repository
from app.services.baseline_reconciliation import BankRecord, InvoiceRecord
from app.services.candidate_matching import CandidateConfig, CandidateMatcher, SettlementRecord
from app.services.decision_engine import DecisionBatch, decide_reconciliation

RUN_STATUSES = ("pending", "running", "completed", "failed")


class EmptySourceBatchError(ValueError):
    pass


class ReconciliationRunNotFoundError(LookupError):
    pass


class ReconciliationExecutionError(RuntimeError):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__("Reconciliation failed. Review the failed run for details.")


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
    throughput: Decimal
    matching_time_ms: int
    decision_time_ms: int
    persistence_time_ms: int
    full_cartesian_comparisons: int
    candidate_records_examined: int
    comparison_reduction: Decimal
    created_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


@dataclass(frozen=True)
class ResultItem:
    id: str
    transaction_id: str
    invoice_id: str | None
    settlement_id: str | None
    status: str
    confidence: Decimal
    reason: str
    best_candidate_id: str | None
    best_candidate_type: str | None
    best_candidate_amount: Decimal | None
    amount_difference: Decimal | None


@dataclass(frozen=True)
class ExceptionItem:
    id: str
    transaction_id: str
    predicted_status: str
    exception_type: str
    severity: str
    description: str
    recommended_action: str
    confidence: Decimal
    status: str
    best_candidate_id: str | None
    best_candidate_type: str | None
    invoice_id: str | None
    settlement_id: str | None
    bank_amount: Decimal
    invoice_amount: Decimal | None
    settlement_amount: Decimal | None
    candidate_amount: Decimal | None
    amount_difference: Decimal | None
    currency: str


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
        run_id=run.id,
        source_batch=run.source_batch,
        status=run.status,
        records_processed=run.records_processed,
        matched=run.matched_count,
        review=run.review_count,
        exceptions=run.exception_count,
        match_rate=run.match_rate,
        processing_time_ms=run.processing_time_ms,
        records_per_second=run.records_per_second,
        throughput=run.records_per_second,
        matching_time_ms=run.matching_time_ms,
        decision_time_ms=run.decision_time_ms,
        persistence_time_ms=run.persistence_time_ms,
        full_cartesian_comparisons=run.full_cartesian_comparisons,
        candidate_records_examined=run.candidate_records_examined,
        comparison_reduction=run.comparison_reduction,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
    )


def _build_models(
    run_id: str,
    batch: DecisionBatch,
) -> tuple[list[ReconciliationResult], list[ExceptionRecord]]:
    results = []
    exceptions = []
    for decision in batch.decisions:
        results.append(
            ReconciliationResult(
                run_id=run_id,
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
            exceptions.append(
                ExceptionRecord(
                    run_id=run_id,
                    transaction_id=decision.bank_transaction_id,
                    exception_type=decision.exception_type,
                    severity=decision.severity or "warning",
                    description=decision.reason,
                    recommended_action=(
                        decision.recommended_action or "Review manually."
                    ),
                    confidence=decision.confidence,
                    status="in_review" if decision.status == "review" else "open",
                )
            )
    return results, exceptions


def run_reconciliation(
    session: Session,
    source_batch: str,
    config: CandidateConfig | None = None,
) -> RunSummary:
    """Execute one traceable run without changing matching behavior."""
    started = perf_counter()
    source_batch = source_batch.strip()
    bank_rows, invoice_rows, settlement_rows = repository.load_source_batch(
        session, source_batch
    )
    if not bank_rows:
        raise EmptySourceBatchError(
            f"Source batch '{source_batch}' contains no bank transactions."
        )
    banks, invoices, settlements = _to_domain(
        bank_rows, invoice_rows, settlement_rows
    )

    run = repository.create_run(session, source_batch)
    run_id = run.id
    session.commit()
    run.status = "running"
    run.started_at = datetime.now(UTC)
    session.commit()

    try:
        matching_started = perf_counter()
        candidate_batch = CandidateMatcher(
            invoices, settlements, config
        ).match_batch(banks)
        matching_ms = max(1, round((perf_counter() - matching_started) * 1000))

        decision_started = perf_counter()
        decision_batch = decide_reconciliation(
            candidate_batch, banks, invoices, settlements
        )
        decision_ms = max(1, round((perf_counter() - decision_started) * 1000))

        persistence_started = perf_counter()
        results, exceptions = _build_models(run.id, decision_batch)
        repository.save_results(session, results)
        repository.save_exceptions(session, exceptions)
        session.flush()
        persistence_ms = max(
            1, round((perf_counter() - persistence_started) * 1000)
        )

        records_processed = len(decision_batch.decisions)
        elapsed = max(perf_counter() - started, 0.000001)
        run.records_processed = records_processed
        run.matched_count = decision_batch.matched
        run.review_count = decision_batch.review
        run.exception_count = decision_batch.exceptions
        run.match_rate = (
            Decimal(decision_batch.matched) / Decimal(records_processed)
        ).quantize(Decimal("0.000001"))
        run.processing_time_ms = max(1, round(elapsed * 1000))
        run.records_per_second = (
            Decimal(records_processed) / Decimal(str(elapsed))
        ).quantize(Decimal("0.01"))
        run.matching_time_ms = matching_ms
        run.decision_time_ms = decision_ms
        run.persistence_time_ms = persistence_ms
        run.full_cartesian_comparisons = (
            candidate_batch.full_cartesian_comparisons
        )
        run.candidate_records_examined = candidate_batch.examined_records
        run.comparison_reduction = candidate_batch.comparison_reduction_percent
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.error_message = None
        session.commit()
    except Exception as exc:
        session.rollback()
        failed = repository.get_run(session, run_id)
        if failed is not None:
            failed.status = "failed"
            failed.completed_at = datetime.now(UTC)
            failed.processing_time_ms = max(
                1, round((perf_counter() - started) * 1000)
            )
            failed.error_message = "Reconciliation execution failed."
            session.commit()
        raise ReconciliationExecutionError(run_id) from exc
    return _summary(run)


def _require_run(session: Session, run_id: str) -> ReconciliationRun:
    run = repository.get_run(session, run_id)
    if run is None:
        raise ReconciliationRunNotFoundError(
            f"Reconciliation run '{run_id}' was not found."
        )
    return run


def get_run_summary(session: Session, run_id: str) -> RunSummary:
    return _summary(_require_run(session, run_id))


def list_run_summaries(
    session: Session,
    page: int,
    page_size: int,
    source_batch: str | None = None,
    status: str | None = None,
) -> tuple[list[RunSummary], int]:
    rows, total = repository.list_runs(
        session, page, page_size, source_batch, status
    )
    return [_summary(item) for item in rows], total


def get_results_page(
    session: Session,
    run_id: str,
    page: int,
    page_size: int,
    status: str | None = None,
) -> tuple[list[ResultItem], int]:
    _require_run(session, run_id)
    rows, total = repository.list_results(
        session, run_id, page, page_size, status
    )
    return [
        ResultItem(
            id=item.id,
            transaction_id=item.bank_transaction_id,
            invoice_id=item.invoice_id,
            settlement_id=item.settlement_id,
            status=item.status,
            confidence=item.confidence,
            reason=item.reason,
            best_candidate_id=item.best_candidate_id,
            best_candidate_type=item.best_candidate_type,
            best_candidate_amount=item.best_candidate_amount,
            amount_difference=item.amount_difference,
        )
        for item in rows
    ], total


def _exception_item(
    exception: ExceptionRecord,
    result: ReconciliationResult,
    bank: BankTransaction,
    invoice: Invoice | None,
    settlement: Settlement | None,
) -> ExceptionItem:
    return ExceptionItem(
        id=exception.id,
        transaction_id=exception.transaction_id,
        predicted_status=result.status,
        exception_type=exception.exception_type,
        severity=exception.severity,
        description=exception.description,
        recommended_action=exception.recommended_action,
        confidence=exception.confidence,
        status=exception.status,
        best_candidate_id=result.best_candidate_id,
        best_candidate_type=result.best_candidate_type,
        invoice_id=result.invoice_id,
        settlement_id=result.settlement_id,
        bank_amount=bank.amount,
        invoice_amount=invoice.amount if invoice else None,
        settlement_amount=settlement.amount if settlement else None,
        candidate_amount=result.best_candidate_amount,
        amount_difference=result.amount_difference,
        currency=bank.currency,
    )


def get_exceptions_page(
    session: Session,
    run_id: str,
    page: int,
    page_size: int,
    severity: str | None = None,
    exception_type: str | None = None,
    status: str | None = None,
) -> tuple[list[ExceptionItem], int]:
    _require_run(session, run_id)
    rows, total = repository.list_exceptions(
        session,
        run_id,
        page,
        page_size,
        severity,
        exception_type,
        status,
    )
    return [_exception_item(*row) for row in rows], total


def get_metrics(session: Session, run_id: str) -> dict[str, object]:
    run = _require_run(session, run_id)
    return {
        "run_id": run.id,
        "total_records": run.records_processed,
        "matched": run.matched_count,
        "review": run.review_count,
        "exceptions": run.exception_count,
        "match_rate": run.match_rate,
        "processing_time_ms": run.processing_time_ms,
        "throughput": run.records_per_second,
        "matching_time_ms": run.matching_time_ms,
        "decision_time_ms": run.decision_time_ms,
        "persistence_time_ms": run.persistence_time_ms,
        "precision": None,
        "recall": None,
        "f1": None,
        "false_matches": None,
        "missed_matches": None,
    }


def get_source_batches(session: Session) -> list[dict[str, int | str]]:
    return repository.source_batch_counts(session)


def export_predictions_csv(session: Session, run_id: str) -> str:
    _require_run(session, run_id)
    rows, _ = repository.list_results(session, run_id, 1, 1_000_000)
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
    items, _ = get_exceptions_page(session, run_id, 1, 1_000_000)
    return tuple(
        ExceptionReportItem(
            transaction_id=item.transaction_id,
            predicted_status=item.predicted_status,
            exception_type=item.exception_type,
            best_candidate_id=item.best_candidate_id,
            best_candidate_type=item.best_candidate_type,
            confidence=(item.confidence / Decimal("100")).quantize(
                Decimal("0.0001")
            ),
            reason=item.description,
            bank_amount=item.bank_amount,
            candidate_amount=item.candidate_amount,
            amount_difference=item.amount_difference,
            currency=item.currency,
        )
        for item in items
    )


def export_exception_report_csv(session: Session, run_id: str) -> str:
    rows = get_exception_report(session, run_id)
    output = io.StringIO(newline="")
    fieldnames = tuple(ExceptionReportItem.__dataclass_fields__)
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for item in rows:
        writer.writerow(item.__dict__)
    return output.getvalue()
