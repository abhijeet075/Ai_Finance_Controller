from datetime import date
from decimal import Decimal

from app.database import Base
from app.models.finance import (
    BankTransaction,
    ExceptionRecord,
    Invoice,
    ReconciliationResult,
    Settlement,
)
from app.services.reconciliation import (
    export_exception_report_csv,
    export_predictions_csv,
    get_exception_report,
    run_reconciliation,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def test_service_persists_run_results_and_export() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            BankTransaction(
                id="B1",
                transaction_date=date(2026, 8, 31),
                amount=Decimal("100"),
                currency="INR",
                description="PAYMENT ALPHA",
                reference="INV-1",
                account_number="XXXX1234",
                transaction_type="credit",
                source_batch="demo",
            )
        )
        session.add(
            Invoice(
                id="I1",
                invoice_number="INV-1",
                customer="ALPHA",
                invoice_date=date(2026, 8, 31),
                due_date=date(2026, 9, 7),
                amount=Decimal("100"),
                currency="INR",
                status="open",
                source_batch="demo",
            )
        )
        session.add(
            Settlement(
                id="S1",
                settlement_reference="SET-1",
                transaction_date=date(2026, 8, 31),
                amount=Decimal("100"),
                currency="INR",
                processor="RAZORPAY",
                customer="ALPHA",
                status="completed",
                source_batch="demo",
            )
        )
        session.commit()
        summary = run_reconciliation(session, "demo")
        assert summary.records_processed == 1
        assert summary.status == "completed"
        assert summary.matched == 1
        assert summary.match_rate == Decimal("1.000000")
        assert summary.processing_time_ms > 0
        assert summary.records_per_second > 0
        assert summary.started_at is not None
        assert summary.completed_at is not None
        result = session.scalar(select(ReconciliationResult))
        assert result is not None
        assert result.run_id == summary.run_id
        assert session.scalar(select(ExceptionRecord)) is None
        exported = export_predictions_csv(session, summary.run_id)
        assert exported.splitlines()[0] == (
            "transaction_id,invoice_id,settlement_id,predicted_status"
        )
        assert "B1,I1,S1,matched" in exported


def test_service_exports_honest_exception_evidence() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            BankTransaction(
                id="B1",
                transaction_date=date(2026, 8, 31),
                amount=Decimal("90"),
                currency="INR",
                description="PAYMENT ALPHA",
                reference="INV-1",
                account_number="XXXX1234",
                transaction_type="credit",
                source_batch="exceptions",
            )
        )
        session.add(
            Invoice(
                id="I1",
                invoice_number="INV-1",
                customer="ALPHA",
                invoice_date=date(2026, 8, 31),
                due_date=date(2026, 9, 7),
                amount=Decimal("100"),
                currency="INR",
                status="open",
                source_batch="exceptions",
            )
        )
        session.commit()
        summary = run_reconciliation(session, "exceptions")
        report = get_exception_report(session, summary.run_id)
        assert len(report) == 1
        assert report[0].transaction_id == "B1"
        assert report[0].exception_type == "amount_mismatch"
        assert report[0].best_candidate_id == "I1"
        assert report[0].bank_amount == Decimal("90.00")
        assert report[0].candidate_amount == Decimal("100.00")
        assert report[0].amount_difference == Decimal("10.00")
        exported = export_exception_report_csv(session, summary.run_id)
        assert "transaction_id,predicted_status,exception_type" in exported
        assert "B1,exception,amount_mismatch,I1,invoice" in exported
