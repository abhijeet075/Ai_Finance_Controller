"""Guarded AI assistance that never mutates canonical reconciliation results."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import (
    AuditLog,
    BankTransaction,
    ExceptionRecord,
    Invoice,
    ReconciliationResult,
    ReconciliationRun,
    Settlement,
)
from app.services.llm import LLMUnavailableError, complete_json


def write_audit(
    session: Session,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    outcome: str,
    detail: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            detail_json=json.dumps(detail or {}, sort_keys=True),
        )
    )
    session.commit()


def _normalize_confidence(value: object, fallback: float) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return fallback


def analyze_exception(
    session: Session,
    exception_id: str,
) -> dict[str, object]:
    statement = (
        select(ExceptionRecord, BankTransaction, ReconciliationResult)
        .join(
            BankTransaction,
            BankTransaction.id == ExceptionRecord.transaction_id,
        )
        .join(
            ReconciliationResult,
            (ReconciliationResult.run_id == ExceptionRecord.run_id)
            & (
                ReconciliationResult.bank_transaction_id
                == ExceptionRecord.transaction_id
            ),
        )
        .where(ExceptionRecord.id == exception_id)
    )
    row = session.execute(statement).first()
    if not row:
        raise LookupError("Exception was not found.")
    exception, bank, result = row
    evidence = [
        (
            f"Transaction {bank.id}: {bank.currency} {bank.amount} "
            f"on {bank.transaction_date}"
        ),
        (
            f"Deterministic status={result.status}; "
            f"confidence={result.confidence}/100"
        ),
        (
            f"Best candidate={result.best_candidate_type or 'none'}:"
            f"{result.best_candidate_id or 'none'}"
        ),
        (
            "Amount difference="
            f"{result.amount_difference if result.amount_difference is not None else 'unknown'}"
        ),
    ]
    severity = {
        "info": "LOW",
        "warning": "HIGH",
        "critical": "CRITICAL",
    }[exception.severity]
    fallback = {
        "exception_type": exception.exception_type.upper(),
        "severity": severity,
        "explanation": exception.description,
        "recommended_action": exception.recommended_action,
        "confidence": float(
            Decimal(exception.confidence) / Decimal("100")
        ),
        "evidence": evidence,
        "generated_by": "deterministic_fallback",
    }
    try:
        raw = complete_json(
            (
                "You are a finance exception analyst. Use only supplied "
                "evidence. Never invent records. Return JSON keys "
                "exception_type, severity, explanation, "
                "recommended_action, confidence."
            ),
            json.dumps(
                {
                    "evidence": evidence,
                    "deterministic_reason": exception.description,
                }
            ),
            "exception analysis",
        )
    except (LLMUnavailableError, httpx.HTTPError):
        return fallback
    result_data = {
        # Classification remains deterministic; the LLM explains it.
        "exception_type": exception.exception_type.upper(),
        "severity": severity,
        "explanation": str(
            raw.get("explanation", exception.description)
        ),
        "recommended_action": str(
            raw.get("recommended_action", exception.recommended_action)
        ),
        "confidence": _normalize_confidence(
            raw.get("confidence"), float(fallback["confidence"])
        ),
        "evidence": evidence,
        "generated_by": "llm",
    }
    return result_data


def suggest_ambiguous_match(
    session: Session,
    run_id: str,
    transaction_id: str,
) -> dict[str, object]:
    result = session.scalar(
        select(ReconciliationResult).where(
            ReconciliationResult.run_id == run_id,
            ReconciliationResult.bank_transaction_id == transaction_id,
        )
    )
    bank = session.get(BankTransaction, transaction_id)
    run = session.get(ReconciliationRun, run_id)
    if not result or not bank or not run:
        raise LookupError("Run transaction was not found.")
    if result.status == "matched":
        return {
            "status": "not_eligible",
            "candidate_id": None,
            "candidate_type": None,
            "explanation": "Deterministic matching already produced a match.",
            "confidence": 1.0,
            "deterministic_checks_passed": True,
            "applied": False,
        }
    amount_window = max(
        Decimal("1.00"),
        abs(Decimal(bank.amount)) * Decimal("0.10"),
    )
    minimum_amount = Decimal(bank.amount) - amount_window
    maximum_amount = Decimal(bank.amount) + amount_window
    minimum_date = bank.transaction_date - timedelta(days=45)
    maximum_date = bank.transaction_date + timedelta(days=45)
    invoices = list(
        session.scalars(
            select(Invoice)
            .where(
                Invoice.source_batch == run.source_batch,
                Invoice.currency == bank.currency,
                Invoice.status != "cancelled",
                Invoice.amount.between(minimum_amount, maximum_amount),
                Invoice.invoice_date.between(minimum_date, maximum_date),
            )
            .limit(20)
        )
    )
    settlements = list(
        session.scalars(
            select(Settlement)
            .where(
                Settlement.source_batch == run.source_batch,
                Settlement.currency == bank.currency,
                Settlement.status.in_(("pending", "completed")),
                Settlement.amount.between(minimum_amount, maximum_amount),
                Settlement.transaction_date.between(
                    minimum_date, maximum_date
                ),
            )
            .limit(20)
        )
    )
    candidates = [
        {
            "id": row.id,
            "type": "invoice",
            "name": row.customer,
            "description": row.invoice_number,
            "amount": str(row.amount),
            "currency": row.currency,
            "date": str(row.invoice_date),
        }
        for row in invoices
    ]
    candidates.extend(
        {
            "id": row.id,
            "type": "settlement",
            "name": row.customer,
            "description": row.settlement_reference,
            "amount": str(row.amount),
            "currency": row.currency,
            "date": str(row.transaction_date),
        }
        for row in settlements
    )
    if not candidates:
        return {
            "status": "not_eligible",
            "candidate_id": None,
            "candidate_type": None,
            "explanation": (
                "No currency-compatible candidates exist in the source batch."
            ),
            "confidence": 0.0,
            "deterministic_checks_passed": False,
            "applied": False,
        }
    prompt = {
        "transaction": {
            "id": bank.id,
            "description": bank.description,
            "reference": bank.reference,
            "amount": str(bank.amount),
            "currency": bank.currency,
            "date": str(bank.transaction_date),
        },
        "candidates": candidates,
    }
    try:
        raw = complete_json(
            (
                "Assist deterministic reconciliation only for ambiguous "
                "cases. Select at most one supplied candidate using name and "
                "description variations or unusual relationships. Never "
                "override amount or currency controls. Return candidate_id, "
                "candidate_type, explanation, confidence."
            ),
            json.dumps(prompt),
            "AI match suggestion",
        )
    except (LLMUnavailableError, httpx.HTTPError):
        return {
            "status": "unavailable",
            "candidate_id": None,
            "candidate_type": None,
            "explanation": (
                "Configure LLM_API_KEY and LLM_MODEL for an AI suggestion."
            ),
            "confidence": 0.0,
            "deterministic_checks_passed": False,
            "applied": False,
        }
    candidate = next(
        (
            item
            for item in candidates
            if item["id"] == raw.get("candidate_id")
            and item["type"] == raw.get("candidate_type")
        ),
        None,
    )
    if not candidate:
        return {
            "status": "suggested",
            "candidate_id": None,
            "candidate_type": None,
            "explanation": (
                "The LLM did not identify a valid supplied candidate."
            ),
            "confidence": 0.0,
            "deterministic_checks_passed": False,
            "applied": False,
        }
    amount_ok = (
        abs(Decimal(candidate["amount"]) - Decimal(bank.amount))
        <= amount_window
    )
    currency_ok = candidate["currency"] == bank.currency
    candidate_date = date.fromisoformat(str(candidate["date"]))
    date_ok = abs((candidate_date - bank.transaction_date).days) <= 45
    return {
        "status": "suggested",
        "candidate_id": candidate["id"],
        "candidate_type": candidate["type"],
        "explanation": str(
            raw.get("explanation", "Advisory semantic relationship.")
        ),
        "confidence": _normalize_confidence(raw.get("confidence"), 0.0),
        "deterministic_checks_passed": amount_ok and currency_ok and date_ok,
        "applied": False,
    }


def answer_finance_question(
    session: Session,
    question: str,
    source_batch: str | None,
    currency: str | None = None,
) -> dict[str, object]:
    today = date.today()
    start = today - timedelta(days=7)
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
    transaction_filters = [
        BankTransaction.transaction_date >= start,
        BankTransaction.transaction_date <= today,
        BankTransaction.currency == currency,
    ]
    if source_batch:
        transaction_filters.append(
            BankTransaction.source_batch == source_batch
        )
    amount_total = func.coalesce(func.sum(BankTransaction.amount), 0)
    credits = Decimal(
        session.scalar(
            select(amount_total).where(
                *transaction_filters,
                BankTransaction.transaction_type == "credit",
            )
        )
        or 0
    )
    debits = Decimal(
        session.scalar(
            select(amount_total).where(
                *transaction_filters,
                BankTransaction.transaction_type == "debit",
            )
        )
        or 0
    )
    exception_filters = [
        ExceptionRecord.status.in_(("open", "in_review")),
        BankTransaction.currency == currency,
    ]
    if source_batch:
        exception_filters.append(
            ReconciliationRun.source_batch == source_batch
        )
    exceptions = int(
        session.scalar(
            select(func.count(ExceptionRecord.id))
            .join(
                ReconciliationRun,
                ReconciliationRun.id == ExceptionRecord.run_id,
            )
            .join(
                BankTransaction,
                BankTransaction.id == ExceptionRecord.transaction_id,
            )
            .where(*exception_filters)
        )
        or 0
    )
    run_filters = [ReconciliationRun.status == "completed"]
    if source_batch:
        run_filters.append(ReconciliationRun.source_batch == source_batch)
    latest_run = session.scalar(
        select(ReconciliationRun)
        .where(*run_filters)
        .order_by(ReconciliationRun.completed_at.desc())
        .limit(1)
    )
    pending_filters = [
        Settlement.status == "pending",
        Settlement.currency == currency,
    ]
    if source_batch:
        pending_filters.append(Settlement.source_batch == source_batch)
    pending = Decimal(
        session.scalar(
            select(func.coalesce(func.sum(Settlement.amount), 0)).where(
                *pending_filters
            )
        )
        or 0
    )
    evidence = [
        {
            "label": "Credits, last 7 days",
            "value": f"{currency} {credits}",
            "source": "bank_transactions",
        },
        {
            "label": "Debits, last 7 days",
            "value": f"{currency} {debits}",
            "source": "bank_transactions",
        },
        {
            "label": "Net cash movement",
            "value": f"{currency} {credits - debits}",
            "source": "bank_transactions",
        },
        {
            "label": "Open reconciliation exceptions",
            "value": str(exceptions),
            "source": "exceptions",
        },
        {
            "label": "Pending settlements",
            "value": f"{currency} {pending}",
            "source": "settlements",
        },
        {
            "label": "Latest run match rate",
            "value": str(
                latest_run.match_rate if latest_run else "not available"
            ),
            "source": "reconciliation_runs",
        },
    ]
    fallback_answer = (
        f"Over the last 7 days, posted {currency} credits were {credits} "
        f"and debits were {debits}, for a net cash movement of "
        f"{credits - debits}. "
        f"There are {exceptions} open reconciliation exceptions and "
        f"{pending} in pending settlements. These figures were queried "
        "from the database."
    )
    try:
        raw = complete_json(
            (
                "Answer using only supplied database evidence. Cite evidence "
                "labels and do not invent causes. Return JSON with answer."
            ),
            json.dumps({"question": question, "evidence": evidence}),
            "finance answer",
        )
        answer = str(raw.get("answer", fallback_answer))
        generated_by = "llm"
    except (LLMUnavailableError, httpx.HTTPError):
        answer = fallback_answer
        generated_by = "deterministic_fallback"
    return {
        "answer": answer,
        "evidence": evidence,
        "generated_by": generated_by,
        "as_of": datetime.now(UTC),
    }
