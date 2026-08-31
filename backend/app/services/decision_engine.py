"""Canonical deterministic decisions and global one-to-one assignment."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.services.baseline_reconciliation import BankRecord, InvoiceRecord
from app.services.candidate_matching import Candidate, CandidateBatch, SettlementRecord
from app.services.normalization import normalize_amount, normalize_currency, normalize_description
from app.services.normalization import normalize_name

DecisionStatus = Literal["matched", "review", "exception"]
ExceptionType = Literal[
    "currency_mismatch",
    "duplicate_payment",
    "missing_settlement",
    "amount_mismatch",
    "ambiguous_match",
    "no_match",
]


@dataclass(frozen=True)
class CanonicalDecision:
    bank_transaction_id: str
    invoice_id: str | None
    settlement_id: str | None
    confidence: Decimal
    status: DecisionStatus
    reason: str
    exception_type: ExceptionType | None = None
    severity: Literal["info", "warning", "critical"] | None = None
    recommended_action: str | None = None


@dataclass(frozen=True)
class DecisionBatch:
    decisions: tuple[CanonicalDecision, ...]

    @property
    def matched(self) -> int:
        return sum(item.status == "matched" for item in self.decisions)

    @property
    def review(self) -> int:
        return sum(item.status == "review" for item in self.decisions)

    @property
    def exceptions(self) -> int:
        return sum(item.status == "exception" for item in self.decisions)


def _duplicate_ids(banks: list[BankRecord]) -> set[str]:
    groups: dict[tuple[object, ...], list[str]] = defaultdict(list)
    for bank in banks:
        if bank.customer:
            identity = normalize_name(bank.customer)
        elif bank.description:
            identity = normalize_description(bank.description)
        else:
            continue
        if not identity:
            continue
        key = (
            normalize_currency(bank.currency),
            normalize_amount(bank.amount),
            bank.transaction_date,
            identity,
        )
        groups[key].append(bank.id)
    return {item for values in groups.values() if len(values) > 1 for item in values}


def _global_assignment(
    batch: CandidateBatch,
    kind: Literal["invoice", "settlement"],
    blocked: set[str],
) -> tuple[dict[str, Candidate], set[str]]:
    edges: list[tuple[Candidate, str]] = []
    for transaction in batch.transactions:
        if transaction.bank_transaction_id in blocked:
            continue
        selected_id = (
            transaction.selected_invoice_id
            if kind == "invoice"
            else transaction.selected_settlement_id
        )
        candidates = transaction.invoices if kind == "invoice" else transaction.settlements
        if selected_id:
            edge = next(item for item in candidates if item.record_id == selected_id)
            edges.append((edge, transaction.bank_transaction_id))
    edges.sort(key=lambda item: (-item[0].score, item[1], item[0].record_id))
    assigned: dict[str, Candidate] = {}
    conflicts: set[str] = set()
    used_records: set[str] = set()
    for candidate, bank_id in edges:
        if candidate.record_id in used_records:
            conflicts.add(bank_id)
            continue
        used_records.add(candidate.record_id)
        assigned[bank_id] = candidate
    return assigned, conflicts


def _reference(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _is_currency_mismatch(
    bank: BankRecord,
    invoices: list[InvoiceRecord],
    settlements: list[SettlementRecord],
) -> bool:
    amount = normalize_amount(bank.amount)
    currency = normalize_currency(bank.currency)
    records = [*invoices, *settlements]
    return any(
        normalize_amount(item.amount) == amount
        and normalize_currency(item.currency) != currency
        and not (
            isinstance(item, SettlementRecord)
            and item.status in {"failed", "reversed"}
        )
        for item in records
    )


def _has_reference_amount_mismatch(bank: BankRecord, invoices: list[InvoiceRecord]) -> bool:
    reference = _reference(bank.reference)
    if not reference:
        return False
    for invoice in invoices:
        invoice_reference = _reference(invoice.invoice_number)
        if invoice_reference == reference and normalize_amount(invoice.amount) != normalize_amount(
            bank.amount
        ):
            return True
    return False


def _exception_details(
    exception_type: ExceptionType,
) -> tuple[Literal["info", "warning", "critical"], str, str]:
    details = {
        "currency_mismatch": (
            "critical",
            "Amount evidence exists in another currency.",
            "Verify source currency and exchange-rate treatment before matching.",
        ),
        "duplicate_payment": (
            "critical",
            "A repeated amount, date, currency, and description was detected.",
            "Review both bank entries and block duplicate allocation.",
        ),
        "missing_settlement": (
            "warning",
            "An invoice candidate was assigned but no settlement was resolved.",
            "Obtain or verify the processor settlement record.",
        ),
        "amount_mismatch": (
            "warning",
            "Reference evidence exists but the amounts do not agree.",
            "Review fees, partial payment, tolerance, and invoice balance.",
        ),
        "ambiguous_match": (
            "warning",
            "Candidate evidence was ambiguous or competed for an assigned record.",
            "Select the correct unused record during manual review.",
        ),
        "no_match": (
            "info",
            "No candidate met deterministic reconciliation requirements.",
            "Review the transaction or request missing source records.",
        ),
    }
    return details[exception_type]


def decide_reconciliation(
    candidates: CandidateBatch,
    banks: list[BankRecord],
    invoices: list[InvoiceRecord],
    settlements: list[SettlementRecord],
) -> DecisionBatch:
    """Convert candidate scores into one canonical, globally assigned decision per bank row."""
    by_bank = {item.bank_transaction_id: item for item in candidates.transactions}
    duplicates = _duplicate_ids(banks)
    ineligible = {
        item.id for item in banks if item.transaction_type.lower() != "credit"
    }
    blocked = duplicates | ineligible
    invoice_assignments, invoice_conflicts = _global_assignment(
        candidates, "invoice", blocked
    )
    settlement_assignments, settlement_conflicts = _global_assignment(
        candidates, "settlement", blocked
    )
    decisions: list[CanonicalDecision] = []
    for bank in sorted(banks, key=lambda item: item.id):
        transaction = by_bank[bank.id]
        invoice = invoice_assignments.get(bank.id)
        settlement = settlement_assignments.get(bank.id)
        conflict = bank.id in invoice_conflicts or bank.id in settlement_conflicts
        if bank.id in ineligible:
            exception_type: ExceptionType = "no_match"
            status: DecisionStatus = "exception"
            invoice = settlement = None
        elif bank.id in duplicates:
            exception_type: ExceptionType = "duplicate_payment"
            status: DecisionStatus = "exception"
            invoice = settlement = None
        elif conflict or "insufficient_score_margin" in {
            transaction.invoice_selection_reason,
            transaction.settlement_selection_reason,
        }:
            exception_type = "ambiguous_match"
            status = "review"
        elif invoice and settlement:
            confidence = ((invoice.score + settlement.score) / 2).quantize(Decimal("0.01"))
            decisions.append(
                CanonicalDecision(
                    bank.id,
                    invoice.record_id,
                    settlement.record_id,
                    confidence,
                    "matched",
                    "invoice_and_settlement_assigned",
                )
            )
            continue
        elif invoice:
            exception_type = "missing_settlement"
            status = "review"
        elif settlement:
            exception_type = "ambiguous_match"
            status = "review"
        elif _is_currency_mismatch(bank, invoices, settlements):
            exception_type = "currency_mismatch"
            status = "exception"
        elif _has_reference_amount_mismatch(bank, invoices):
            exception_type = "amount_mismatch"
            status = "exception"
        else:
            exception_type = "no_match"
            status = "exception"
        scores = [item.score for item in (*transaction.invoices, *transaction.settlements)]
        confidence = max(scores, default=Decimal("0.00"))
        severity, description, action = _exception_details(exception_type)
        decisions.append(
            CanonicalDecision(
                bank.id,
                invoice.record_id if invoice else None,
                settlement.record_id if settlement else None,
                confidence,
                status,
                description,
                exception_type,
                severity,
                action,
            )
        )
    return DecisionBatch(tuple(decisions))
