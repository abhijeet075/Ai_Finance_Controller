"""Pure deterministic reconciliation. This module makes no AI/LLM calls."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Literal

from app.services.normalization import (
    normalize_amount,
    normalize_currency,
    normalize_description,
    normalize_name,
)

Status = Literal["matched", "review", "exception", "no_match"]
Rule = Literal[
    "exact_reference", "exact_amount_customer", "amount_date", "amount_tolerance",
    "duplicate", "ambiguous", "currency_mismatch", "no_match",
]
STOPWORDS = {
    "BANK", "CREDIT", "FROM", "NEFT", "PAYMENT", "RECEIPT", "RECEIVED",
    "TO", "TRANSFER", "UPI",
}


@dataclass(frozen=True)
class BankRecord:
    id: str
    transaction_date: date
    amount: Decimal
    currency: str
    reference: str | None = None
    description: str | None = None
    customer: str | None = None
    transaction_type: str = "credit"


@dataclass(frozen=True)
class InvoiceRecord:
    id: str
    invoice_number: str
    customer: str
    invoice_date: date
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class ReconciliationConfig:
    amount_tolerance: Decimal = Decimal("1.00")
    date_window_days: int = 3
    customer_similarity_threshold: Decimal = Decimal("0.70")

    def __post_init__(self) -> None:
        if self.amount_tolerance < 0 or self.date_window_days < 0:
            raise ValueError("tolerance and date window must be non-negative")
        if not 0 <= self.customer_similarity_threshold <= 1:
            raise ValueError("customer similarity threshold must be between 0 and 1")


@dataclass(frozen=True)
class DuplicateGroup:
    transaction_ids: tuple[str, ...]
    amount: Decimal
    currency: str
    customer_key: str
    transaction_date: date


@dataclass(frozen=True)
class Decision:
    bank_transaction_id: str
    invoice_id: str | None
    status: Status
    confidence: Decimal
    rule: Rule
    reason: str
    amount_difference: Decimal | None = None
    date_difference_days: int | None = None
    customer_similarity: Decimal | None = None


@dataclass(frozen=True)
class BatchResult:
    decisions: tuple[Decision, ...]
    duplicate_groups: tuple[DuplicateGroup, ...]

    @property
    def summary(self) -> dict[str, int]:
        result = {name: 0 for name in ("matched", "review", "exception", "no_match")}
        for decision in self.decisions:
            result[decision.status] += 1
        result["total"] = len(self.decisions)
        result["duplicate_groups"] = len(self.duplicate_groups)
        return result


@dataclass(frozen=True)
class _Candidate:
    bank: BankRecord
    invoice: InvoiceRecord
    rule: Rule
    status: Status
    confidence: Decimal
    priority: int
    amount_difference: Decimal
    date_difference_days: int
    customer_similarity: Decimal

    @property
    def rank(self) -> tuple[object, ...]:
        return (-self.priority, -self.confidence, -self.customer_similarity,
                self.date_difference_days, self.amount_difference, self.invoice.id)

    @property
    def tie(self) -> tuple[object, ...]:
        return self.rank[:-1]


def _reference(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _counterparty(bank: BankRecord) -> str:
    if bank.customer:
        return normalize_name(bank.customer)
    if not bank.description:
        return ""
    words = normalize_description(bank.description).split()
    return normalize_name(" ".join(word for word in words if word not in STOPWORDS))


def customer_similarity(bank: BankRecord, invoice: InvoiceRecord) -> Decimal:
    bank_name = _counterparty(bank)
    invoice_name = normalize_name(invoice.customer)
    if not bank_name:
        return Decimal("0.00")
    bank_tokens, invoice_tokens = set(bank_name.split()), set(invoice_name.split())
    if invoice_tokens and invoice_tokens.issubset(bank_tokens):
        return Decimal("1.00")
    union = bank_tokens | invoice_tokens
    jaccard = len(bank_tokens & invoice_tokens) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, bank_name, invoice_name).ratio()
    return Decimal(str(max(jaccard, sequence))).quantize(Decimal("0.01"))


def detect_duplicates(banks: list[BankRecord]) -> tuple[DuplicateGroup, ...]:
    grouped: dict[tuple[object, ...], list[str]] = defaultdict(list)
    for bank in banks:
        customer = _counterparty(bank)
        if customer:
            key = (normalize_currency(bank.currency), normalize_amount(bank.amount),
                   customer, bank.transaction_date)
            grouped[key].append(bank.id)
    result = []
    for (currency, amount, customer, transaction_date), ids in grouped.items():
        if len(ids) > 1:
            result.append(DuplicateGroup(tuple(sorted(ids)), amount, currency,
                                         customer, transaction_date))
    return tuple(sorted(result, key=lambda item: item.transaction_ids))


def _make_candidate(bank: BankRecord, invoice: InvoiceRecord,
                    config: ReconciliationConfig) -> _Candidate | None:
    if normalize_currency(bank.currency) != normalize_currency(invoice.currency):
        return None
    amount_diff = abs(normalize_amount(bank.amount) - normalize_amount(invoice.amount))
    date_diff = abs((bank.transaction_date - invoice.invoice_date).days)
    similarity = customer_similarity(bank, invoice)
    exact_ref = bool(_reference(bank.reference)) and (
        _reference(bank.reference) == _reference(invoice.invoice_number)
    )
    if exact_ref:
        rule, status, confidence, priority = "exact_reference", "matched", Decimal("100"), 4
    elif amount_diff == 0 and similarity >= config.customer_similarity_threshold:
        rule, status, confidence, priority = "exact_amount_customer", "matched", Decimal("95"), 3
    elif amount_diff == 0 and date_diff <= config.date_window_days:
        rule, status, confidence, priority = "amount_date", "review", Decimal("75"), 2
    elif amount_diff <= config.amount_tolerance:
        rule, status, confidence, priority = "amount_tolerance", "review", Decimal("60"), 1
    else:
        return None
    return _Candidate(bank, invoice, rule, status, confidence, priority,
                      amount_diff, date_diff, similarity)


def _from_candidate(candidate: _Candidate) -> Decision:
    reason = (f"{candidate.rule}; amount_diff={candidate.amount_difference}; "
              f"date_diff_days={candidate.date_difference_days}; "
              f"customer_similarity={candidate.customer_similarity}")
    return Decision(candidate.bank.id, candidate.invoice.id, candidate.status,
                    candidate.confidence, candidate.rule, reason,
                    candidate.amount_difference, candidate.date_difference_days,
                    candidate.customer_similarity)


def reconcile(banks: list[BankRecord], invoices: list[InvoiceRecord],
              config: ReconciliationConfig | None = None) -> BatchResult:
    """Apply the five baseline rules with deterministic, one-to-one assignment."""
    config = config or ReconciliationConfig()
    duplicate_groups = detect_duplicates(banks)
    duplicate_ids = {item for group in duplicate_groups for item in group.transaction_ids}
    decisions: dict[str, Decision] = {}
    proposals: dict[str, _Candidate] = {}
    all_refs: dict[str, list[InvoiceRecord]] = defaultdict(list)
    for invoice in invoices:
        all_refs[_reference(invoice.invoice_number)].append(invoice)
    from app.services.candidate_matching import CandidateMatcher

    candidate_matcher = CandidateMatcher(invoices, [])

    for bank in sorted(banks, key=lambda item: item.id):
        if bank.id in duplicate_ids:
            decisions[bank.id] = Decision(bank.id, None, "exception", Decimal("100"),
                "duplicate", "Duplicate amount + customer + date; automatic match blocked.")
            continue
        if bank.transaction_type.lower() != "credit":
            decisions[bank.id] = Decision(bank.id, None, "no_match", Decimal("100"),
                                           "no_match", "Debit is not a receivable candidate.")
            continue
        candidate_records, _ = candidate_matcher.invoice_records(
            bank,
            absolute_window=config.amount_tolerance,
            percent_window=Decimal("0"),
        )
        candidates = sorted(
            filter(
                None,
                (_make_candidate(bank, invoice, config) for invoice in candidate_records),
            ),
            key=lambda item: item.rank,
        )
        if not candidates:
            ref_matches = all_refs.get(_reference(bank.reference), []) if bank.reference else []
            mismatch = bool(ref_matches)
            decisions[bank.id] = Decision(bank.id, None,
                "exception" if mismatch else "no_match", Decimal("0"),
                "currency_mismatch" if mismatch else "no_match",
                "Exact reference exists in another currency." if mismatch
                else "No deterministic rule produced a candidate.")
        elif len(candidates) > 1 and candidates[0].tie == candidates[1].tie:
            decisions[bank.id] = Decision(bank.id, None, "review", candidates[0].confidence,
                                           "ambiguous", "Equal top-ranked invoice candidates.")
        else:
            proposals[bank.id] = candidates[0]

    by_invoice: dict[str, list[_Candidate]] = defaultdict(list)
    for candidate in proposals.values():
        by_invoice[candidate.invoice.id].append(candidate)
    for invoice_id, candidates in by_invoice.items():
        ranked = sorted(candidates, key=lambda item: item.rank)
        if len(ranked) > 1 and ranked[0].tie == ranked[1].tie:
            winners: list[_Candidate] = []
        else:
            winners = ranked[:1]
        for candidate in winners:
            decisions[candidate.bank.id] = _from_candidate(candidate)
        for candidate in ranked[len(winners):]:
            decisions[candidate.bank.id] = Decision(candidate.bank.id, None, "review",
                candidate.confidence, "ambiguous",
                f"Invoice {invoice_id} has competing bank candidates.")
    ordered = tuple(decisions[bank.id] for bank in sorted(banks, key=lambda item: item.id))
    return BatchResult(ordered, duplicate_groups)
