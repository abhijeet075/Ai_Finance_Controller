"""Phase 12 lifecycle, pagination, filtering, and API invariants."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_database_session
from app.main import app
from app.models.finance import (
    BankTransaction,
    ExceptionRecord,
    Invoice,
    ReconciliationResult,
    ReconciliationRun,
)
from app.services.reconciliation import (
    ReconciliationExecutionError,
    get_metrics,
    get_results_page,
    list_run_summaries,
    run_reconciliation,
)


def _engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _seed(session: Session, source_batch: str = "phase12") -> None:
    session.add(
        BankTransaction(
            id="B1",
            transaction_date=date(2026, 9, 2),
            amount=Decimal("100"),
            currency="INR",
            description="PAYMENT ALPHA",
            reference="INV-1",
            account_number="XXXX1234",
            transaction_type="credit",
            source_batch=source_batch,
        )
    )
    session.add(
        Invoice(
            id="I1",
            invoice_number="INV-1",
            customer="ALPHA",
            invoice_date=date(2026, 9, 2),
            due_date=date(2026, 9, 30),
            amount=Decimal("100"),
            currency="INR",
            status="open",
            source_batch=source_batch,
        )
    )
    session.commit()


def test_repeated_runs_are_independent_and_paginated() -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        first = run_reconciliation(session, "phase12")
        second = run_reconciliation(session, "phase12")
        assert first.run_id != second.run_id
        assert first.status == second.status == "completed"
        assert first.matched + first.review + first.exceptions == 1
        runs, total = list_run_summaries(session, 1, 1, "phase12", "completed")
        assert total == 2
        assert len(runs) == 1
        results, result_total = get_results_page(session, first.run_id, 1, 50)
        assert result_total == first.records_processed == len(results)
        assert all(item.id for item in results)
        stored = list(
            session.scalars(
                select(ReconciliationResult).where(
                    ReconciliationResult.run_id == first.run_id
                )
            )
        )
        assert all(item.run_id == first.run_id for item in stored)
        metrics = get_metrics(session, first.run_id)
        assert metrics["precision"] is None
        assert metrics["recall"] is None
        assert metrics["f1"] is None
        assert metrics["processing_time_ms"] > 0
        assert metrics["throughput"] > 0


def test_failed_execution_is_traceable(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)

        def fail(*args, **kwargs):
            raise RuntimeError("private database detail")

        monkeypatch.setattr(
            "app.services.reconciliation.CandidateMatcher.match_batch",
            fail,
        )
        with pytest.raises(ReconciliationExecutionError) as captured:
            run_reconciliation(session, "phase12")
        run = session.get(ReconciliationRun, captured.value.run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.error_message == "Reconciliation execution failed."
        assert "private" not in run.error_message
        assert session.scalar(select(ReconciliationResult)) is None
        assert session.scalar(select(ExceptionRecord)) is None


def test_phase12_api_contract_end_to_end() -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        _seed(session)

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = override_session
    try:
        client = TestClient(app)
        batches = client.get("/api/reconciliation/source-batches")
        assert batches.status_code == 200
        assert batches.json()["items"][0]["source_batch"] == "phase12"

        created = client.post(
            "/api/reconciliation/runs",
            json={"source_batch": "phase12"},
        )
        assert created.status_code == 201
        run_id = created.json()["run_id"]

        repeated = client.post(
            "/api/reconciliation/runs",
            json={"source_batch": "phase12"},
        )
        assert repeated.status_code == 201
        assert repeated.json()["run_id"] != run_id

        history = client.get("/api/reconciliation/runs?page=1&page_size=1")
        assert history.status_code == 200
        assert history.json()["total"] == 2
        assert len(history.json()["items"]) == 1

        result = client.get(
            f"/api/reconciliation/runs/{run_id}/results?page=1&page_size=50"
        )
        assert result.status_code == 200
        assert result.json()["total"] == 1

        exceptions = client.get(
            f"/api/reconciliation/runs/{run_id}/exceptions?severity=warning"
        )
        assert exceptions.status_code == 200
        assert exceptions.json()["total"] == 1
        exception = exceptions.json()["items"][0]
        assert exception["invoice_id"] == "I1"
        assert exception["invoice_amount"] == 100.0
        assert exception["settlement_id"] is None

        metrics = client.get(f"/api/reconciliation/runs/{run_id}/metrics")
        assert metrics.status_code == 200
        assert metrics.json()["precision"] is None

        predictions = client.get(
            f"/api/reconciliation/runs/{run_id}/predictions.csv"
        )
        assert predictions.status_code == 200
        assert predictions.headers["content-type"].startswith("text/csv")

        exception_csv = client.get(
            f"/api/reconciliation/runs/{run_id}/exceptions.csv"
        )
        assert exception_csv.status_code == 200
        assert exception_csv.headers["content-type"].startswith("text/csv")

        missing = client.get("/api/reconciliation/runs/missing")
        assert missing.status_code == 404
        invalid = client.get(
            f"/api/reconciliation/runs/{run_id}/results?page_size=101"
        )
        assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()
