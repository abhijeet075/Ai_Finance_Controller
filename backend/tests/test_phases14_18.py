"""Regression coverage for forecasting, guarded AI, auth, and audit."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.auth import require_api_identity
from app.database import Base
from app.models.finance import (
    BankTransaction,
    ExceptionRecord,
    Invoice,
    ReconciliationResult,
    ReconciliationRun,
    Settlement,
)
from app.services.forecasting import VALID_HORIZONS, build_cash_forecast
from app.services.intelligence import (
    analyze_exception,
    answer_finance_question,
    suggest_ambiguous_match,
)
from app.services.llm import LLMUnavailableError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _bank(
    transaction_id: str,
    transaction_date: date,
    amount: str,
    transaction_type: str = "credit",
    source_batch: str = "phase18",
) -> BankTransaction:
    return BankTransaction(
        id=transaction_id,
        transaction_date=transaction_date,
        amount=Decimal(amount),
        currency="USD",
        description="ACME subscription payment",
        reference="INV-ACME-1",
        account_number="TEST-001",
        transaction_type=transaction_type,
        source_batch=source_batch,
    )


def test_forecast_horizons_and_formula() -> None:
    assert VALID_HORIZONS == (7, 14, 30)
    as_of = date(2026, 9, 3)
    with _session() as session:
        session.add_all(
            [
                _bank("B-CREDIT", as_of - timedelta(days=2), "1000"),
                _bank(
                    "B-DEBIT",
                    as_of - timedelta(days=1),
                    "200",
                    "debit",
                ),
                _bank(
                    "B-FUTURE",
                    as_of + timedelta(days=3),
                    "50",
                    "debit",
                ),
                Invoice(
                    id="I1",
                    invoice_number="INV-1",
                    customer="Customer",
                    invoice_date=as_of,
                    due_date=as_of + timedelta(days=2),
                    amount=Decimal("300"),
                    currency="USD",
                    status="open",
                    source_batch="phase18",
                ),
                Settlement(
                    id="S1",
                    settlement_reference="SET-1",
                    transaction_date=as_of + timedelta(days=1),
                    amount=Decimal("100"),
                    currency="USD",
                    processor="Processor",
                    customer="Customer",
                    status="pending",
                    source_batch="phase18",
                ),
            ]
        )
        session.commit()
        result = build_cash_forecast(
            session,
            7,
            "phase18",
            "USD",
            as_of,
        )
    assert result["current_cash"] == Decimal("800")
    assert result["expected_receipts"] == Decimal("300")
    assert result["expected_expenses"] == Decimal("50")
    assert result["pending_settlements"] == Decimal("100")
    assert result["projected_cash"] == Decimal("950")
    assert len(result["series"]) == 7


def test_forecast_rejects_non_standard_horizon() -> None:
    with _session() as session, pytest.raises(ValueError):
        build_cash_forecast(session, 10)


def test_exception_classification_cannot_be_overridden_by_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _session() as session:
        session.add(_bank("B1", date(2026, 9, 3), "100"))
        session.add(
            ReconciliationRun(
                id="R1",
                source_batch="phase18",
                status="completed",
            )
        )
        session.add(
            ReconciliationResult(
                id="RR1",
                run_id="R1",
                bank_transaction_id="B1",
                confidence=Decimal("70"),
                status="exception",
                reason="Amounts differ",
                amount_difference=Decimal("10"),
            )
        )
        session.add(
            ExceptionRecord(
                id="E1",
                run_id="R1",
                transaction_id="B1",
                exception_type="amount_mismatch",
                severity="warning",
                description="Amounts differ",
                recommended_action="Review invoice balance.",
                confidence=Decimal("70"),
                status="open",
            )
        )
        session.commit()
        monkeypatch.setattr(
            "app.services.intelligence.complete_json",
            lambda *args: {
                "exception_type": "NO_MATCH",
                "severity": "LOW",
                "explanation": "Review supplied evidence.",
                "recommended_action": "Review.",
                "confidence": 0.9,
            },
        )
        result = analyze_exception(session, "E1")
    assert result["exception_type"] == "AMOUNT_MISMATCH"
    assert result["severity"] == "HIGH"
    assert result["generated_by"] == "llm"
    assert len(result["evidence"]) == 4


def test_ai_matching_receives_only_deterministically_viable_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_completion(system: str, user: str, schema_name: str):
        import json

        captured.update(json.loads(user))
        return {
            "candidate_id": "I-VALID",
            "candidate_type": "invoice",
            "explanation": "Name variation appears equivalent.",
            "confidence": 0.88,
        }

    as_of = date(2026, 9, 3)
    with _session() as session:
        session.add(_bank("B1", as_of, "100"))
        session.add(
            ReconciliationRun(
                id="R1",
                source_batch="phase18",
                status="completed",
            )
        )
        session.add(
            ReconciliationResult(
                id="RR1",
                run_id="R1",
                bank_transaction_id="B1",
                confidence=Decimal("60"),
                status="review",
                reason="Ambiguous candidate",
            )
        )
        session.add_all(
            [
                Invoice(
                    id="I-VALID",
                    invoice_number="INV-ACME-1",
                    customer="ACME Incorporated",
                    invoice_date=as_of,
                    due_date=as_of + timedelta(days=10),
                    amount=Decimal("100"),
                    currency="USD",
                    status="open",
                    source_batch="phase18",
                ),
                Invoice(
                    id="I-WRONG-AMOUNT",
                    invoice_number="INV-2",
                    customer="ACME",
                    invoice_date=as_of,
                    due_date=as_of,
                    amount=Decimal("500"),
                    currency="USD",
                    status="open",
                    source_batch="phase18",
                ),
            ]
        )
        session.commit()
        monkeypatch.setattr(
            "app.services.intelligence.complete_json",
            fake_completion,
        )
        result = suggest_ambiguous_match(session, "R1", "B1")
    assert [item["id"] for item in captured["candidates"]] == ["I-VALID"]
    assert result["candidate_id"] == "I-VALID"
    assert result["deterministic_checks_passed"] is True
    assert result["applied"] is False


def test_finance_qa_falls_back_to_database_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*args):
        raise LLMUnavailableError("not configured")

    today = date.today()
    with _session() as session:
        session.add_all(
            [
                _bank("B-C", today, "150"),
                _bank("B-D", today, "40", "debit"),
            ]
        )
        session.commit()
        monkeypatch.setattr(
            "app.services.intelligence.complete_json",
            unavailable,
        )
        result = answer_finance_question(
            session,
            "Why did cash decrease this week?",
            "phase18",
        )
    values = {item["label"]: item["value"] for item in result["evidence"]}
    assert values["Net cash movement"] == "USD 110.00"
    assert result["generated_by"] == "deterministic_fallback"
    assert "queried from the database" in result["answer"]


def test_auth_is_optional_only_when_no_secret_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.auth.get_settings",
        lambda: SimpleNamespace(app_api_key=None),
    )
    assert require_api_identity() == "local-development"


def test_auth_rejects_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.auth.get_settings",
        lambda: SimpleNamespace(app_api_key="secret"),
    )
    with pytest.raises(Exception) as raised:
        require_api_identity(x_api_key="wrong")
    assert raised.value.status_code == 401
