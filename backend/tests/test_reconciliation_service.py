from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.finance import (
    BankTransaction,
    ExceptionRecord,
    Invoice,
    ReconciliationResult,
    Settlement,
)
from app.services.reconciliation import export_predictions_csv, run_reconciliation


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
        assert summary.matched == 1
        assert summary.match_rate == Decimal("1.000000")
        result = session.scalar(select(ReconciliationResult))
        assert result is not None
        assert result.run_id == summary.run_id
        assert session.scalar(select(ExceptionRecord)) is None
        exported = export_predictions_csv(session, summary.run_id)
        assert exported.splitlines()[0] == (
            "transaction_id,invoice_id,settlement_id,predicted_status"
        )
        assert "B1,I1,S1,matched" in exported
