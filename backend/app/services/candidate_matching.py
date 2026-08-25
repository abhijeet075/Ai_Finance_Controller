"""Indexed candidate generation and deterministic confidence scoring."""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Generic, Literal, TypeVar

from app.services.baseline_reconciliation import BankRecord, InvoiceRecord
from app.services.normalization import (
    normalize_amount,
    normalize_currency,
    normalize_description,
    normalize_name,
)

T = TypeVar("T")
Kind = Literal["invoice", "settlement"]
ZERO, ONE = Decimal("0"), Decimal("1")
STOPWORDS = {
    "BANK", "CREDIT", "FROM", "NEFT", "PAYMENT", "RECEIPT", "RECEIVED",
    "TO", "TRANSFER", "UPI",
}


@dataclass(frozen=True)
class SettlementRecord:
    id: str
    settlement_reference: str
    customer: str
    transaction_date: date
    amount: Decimal
    currency: str
    processor: str | None = None
    status: str = "completed"


@dataclass(frozen=True)
class CandidateConfig:
    amount_window_percent: Decimal = Decimal("0.10")
    amount_window_absolute: Decimal = Decimal("1.00")
    date_window_days: int = 45
    minimum_customer_similarity: Decimal = Decimal("0.20")
    confidence_threshold: Decimal = Decimal("85.00")
    minimum_winner_margin: Decimal = Decimal("10.00")
    maximum_candidates: int = 3

    def __post_init__(self) -> None:
        if self.amount_window_percent < 0 or self.amount_window_absolute < 0:
            raise ValueError("amount windows must be non-negative")
        if self.date_window_days < 0 or self.minimum_winner_margin < 0:
            raise ValueError("date window and winner margin must be non-negative")
        if not 0 <= self.minimum_customer_similarity <= 1:
            raise ValueError("customer threshold must be between zero and one")
        if not 0 <= self.confidence_threshold <= 100:
            raise ValueError("confidence threshold must be between zero and 100")
        if self.maximum_candidates < 1:
            raise ValueError("maximum_candidates must be positive")


@dataclass(frozen=True)
class ScoreBreakdown:
    reference: Decimal | None
    amount: Decimal
    date: Decimal
    customer: Decimal


@dataclass(frozen=True)
class Candidate:
    kind: Kind
    record_id: str
    score: Decimal
    breakdown: ScoreBreakdown
    amount_difference: Decimal
    date_difference_days: int
    customer_similarity: Decimal


@dataclass(frozen=True)
class TransactionCandidates:
    bank_transaction_id: str
    invoices: tuple[Candidate, ...]
    settlements: tuple[Candidate, ...]
    selected_invoice_id: str | None
    selected_settlement_id: str | None
    invoice_selection_reason: str
    settlement_selection_reason: str
    examined_invoice_records: int
    examined_settlement_records: int


@dataclass(frozen=True)
class CandidateBatch:
    transactions: tuple[TransactionCandidates, ...]
    full_cartesian_comparisons: int
    examined_records: int

    @property
    def comparison_reduction_percent(self) -> Decimal:
        if not self.full_cartesian_comparisons:
            return Decimal("0.00")
        ratio = Decimal(self.examined_records) / Decimal(self.full_cartesian_comparisons)
        return ((ONE - ratio) * 100).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class _Bucket(Generic[T]):
    amounts: tuple[Decimal, ...]
    records: tuple[T, ...]


def _reference(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _bank_customer(bank: BankRecord) -> str:
    if bank.customer:
        return normalize_name(bank.customer)
    if not bank.description:
        return ""
    words = normalize_description(bank.description).split()
    return normalize_name(" ".join(word for word in words if word not in STOPWORDS))


def _similarity(left: str, right: str) -> Decimal:
    if not left:
        return ZERO
    left_tokens, right_tokens = set(left.split()), set(right.split())
    if right_tokens and right_tokens.issubset(left_tokens):
        return ONE
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    return Decimal(str(max(jaccard, sequence))).quantize(Decimal("0.0001"))


def _possible_customer(left: str, right: str, minimum: Decimal) -> bool:
    if not left:
        return False
    if left == right:
        return True
    left_tokens, right_tokens = set(left.split()), set(right.split())
    union = left_tokens | right_tokens
    if not union:
        return False
    overlap = Decimal(len(left_tokens & right_tokens)) / Decimal(len(union))
    return overlap >= minimum


def _buckets(records: list[T]) -> dict[str, _Bucket[T]]:
    grouped: dict[str, list[tuple[Decimal, str, T]]] = defaultdict(list)
    for record in records:
        grouped[normalize_currency(getattr(record, "currency"))].append(
            (normalize_amount(getattr(record, "amount")), getattr(record, "id"), record)
        )
    result = {}
    for currency, values in grouped.items():
        values.sort(key=lambda item: (item[0], item[1]))
        result[currency] = _Bucket(
            tuple(item[0] for item in values), tuple(item[2] for item in values)
        )
    return result


def _proximity(difference: Decimal, window: Decimal) -> Decimal:
    if difference == 0:
        return ONE
    if window <= 0 or difference >= window:
        return ZERO
    return ONE - difference / window


class CandidateMatcher:
    """Reuse currency, amount, reference, and normalized-name indexes per batch."""

    def __init__(
        self,
        invoices: list[InvoiceRecord],
        settlements: list[SettlementRecord],
        config: CandidateConfig | None = None,
    ) -> None:
        self.config = config or CandidateConfig()
        self.invoices = sorted(invoices, key=lambda item: item.id)
        self.settlements = sorted(
            (item for item in settlements if item.status not in {"failed", "reversed"}),
            key=lambda item: item.id,
        )
        self.invoice_names = {item.id: normalize_name(item.customer) for item in invoices}
        self.settlement_names = {
            item.id: normalize_name(item.customer) for item in self.settlements
        }
        self.invoice_buckets = _buckets(self.invoices)
        self.settlement_buckets = _buckets(self.settlements)
        self.invoice_references: dict[tuple[str, str], list[InvoiceRecord]] = defaultdict(list)
        for invoice in self.invoices:
            key = (normalize_currency(invoice.currency), _reference(invoice.invoice_number))
            self.invoice_references[key].append(invoice)

    def _window(self, amount: Decimal) -> Decimal:
        return max(
            self.config.amount_window_absolute,
            abs(amount) * self.config.amount_window_percent,
        )

    @staticmethod
    def _range(bucket: _Bucket[T] | None, amount: Decimal, window: Decimal) -> list[T]:
        if bucket is None:
            return []
        left = bisect_left(bucket.amounts, amount - window)
        right = bisect_right(bucket.amounts, amount + window)
        return list(bucket.records[left:right])

    def invoice_records(
        self,
        bank: BankRecord,
        absolute_window: Decimal | None = None,
        percent_window: Decimal | None = None,
    ) -> tuple[list[InvoiceRecord], int]:
        amount = normalize_amount(bank.amount)
        currency = normalize_currency(bank.currency)
        absolute = (
            self.config.amount_window_absolute
            if absolute_window is None
            else absolute_window
        )
        percent = self.config.amount_window_percent if percent_window is None else percent_window
        records = self._range(
            self.invoice_buckets.get(currency), amount, max(absolute, abs(amount) * percent)
        )
        references = self.invoice_references.get((currency, _reference(bank.reference)), [])
        unique = {item.id: item for item in records + references}
        return sorted(unique.values(), key=lambda item: item.id), len(records) + len(references)

    def _settlement_records(self, bank: BankRecord) -> tuple[list[SettlementRecord], int]:
        amount = normalize_amount(bank.amount)
        records = self._range(
            self.settlement_buckets.get(normalize_currency(bank.currency)),
            amount,
            self._window(amount),
        )
        return records, len(records)

    def _score(
        self,
        bank: BankRecord,
        record: InvoiceRecord | SettlementRecord,
        kind: Kind,
        bank_name: str,
    ) -> Candidate:
        record_date = (
            record.invoice_date if isinstance(record, InvoiceRecord)
            else record.transaction_date
        )
        amount_difference = abs(normalize_amount(bank.amount) - normalize_amount(record.amount))
        date_difference = abs((bank.transaction_date - record_date).days)
        names = self.invoice_names if kind == "invoice" else self.settlement_names
        customer = _similarity(bank_name, names[record.id])
        amount_score = _proximity(amount_difference, self._window(normalize_amount(bank.amount)))
        date_score = _proximity(
            Decimal(date_difference), Decimal(self.config.date_window_days)
        )
        if kind == "invoice":
            reference = ONE if _reference(bank.reference) == _reference(
                record.invoice_number
            ) else ZERO
            score = reference * 30 + amount_score * 30 + date_score * 20 + customer * 20
        else:
            reference = None
            score = amount_score * 45 + date_score * 25 + customer * 30
        return Candidate(
            kind, record.id, score.quantize(Decimal("0.01")),
            ScoreBreakdown(reference, amount_score, date_score, customer),
            amount_difference, date_difference, customer,
        )

    def _select(self, values: tuple[Candidate, ...]) -> tuple[str | None, str]:
        if not values:
            return None, "no_candidates"
        if values[0].score < self.config.confidence_threshold:
            return None, "below_confidence_threshold"
        if len(values) > 1 and (
            values[0].score - values[1].score < self.config.minimum_winner_margin
        ):
            return None, "insufficient_score_margin"
        return values[0].record_id, "selected"

    def match_transaction(self, bank: BankRecord) -> TransactionCandidates:
        invoices, invoice_examined = self.invoice_records(bank)
        settlements, settlement_examined = self._settlement_records(bank)
        bank_name = _bank_customer(bank)
        invoices = [
            item for item in invoices
            if _reference(bank.reference) == _reference(item.invoice_number)
            or abs((bank.transaction_date - item.invoice_date).days) <= self.config.date_window_days
            or _possible_customer(
                bank_name, self.invoice_names[item.id], self.config.minimum_customer_similarity
            )
        ]
        settlements = [
            item for item in settlements
            if abs((bank.transaction_date - item.transaction_date).days)
            <= self.config.date_window_days
            or _possible_customer(
                bank_name,
                self.settlement_names[item.id],
                self.config.minimum_customer_similarity,
            )
        ]
        invoice_scores = tuple(sorted(
            (self._score(bank, item, "invoice", bank_name) for item in invoices),
            key=lambda item: (-item.score, item.record_id),
        )[: self.config.maximum_candidates])
        settlement_scores = tuple(sorted(
            (self._score(bank, item, "settlement", bank_name) for item in settlements),
            key=lambda item: (-item.score, item.record_id),
        )[: self.config.maximum_candidates])
        invoice_id, invoice_reason = self._select(invoice_scores)
        settlement_id, settlement_reason = self._select(settlement_scores)
        return TransactionCandidates(
            bank.id, invoice_scores, settlement_scores, invoice_id, settlement_id,
            invoice_reason, settlement_reason, invoice_examined, settlement_examined,
        )

    def match_batch(self, banks: list[BankRecord]) -> CandidateBatch:
        transactions = tuple(
            self.match_transaction(item) for item in sorted(banks, key=lambda row: row.id)
        )
        examined = sum(
            item.examined_invoice_records + item.examined_settlement_records
            for item in transactions
        )
        full = len(banks) * (len(self.invoices) + len(self.settlements))
        return CandidateBatch(transactions, full, examined)
