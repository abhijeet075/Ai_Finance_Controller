"""Generate reproducible synthetic finance datasets for reconciliation testing.

The generator creates source CSVs that match the Phase 3 database entities and
keeps evaluation-only labels in a separate ground-truth directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Callable
from uuid import NAMESPACE_DNS, uuid5

SUPPORTED_PRESETS = (100, 500, 1_000, 5_000, 10_000)
SOURCE_COLUMNS = {
    "bank_transactions": (
        "id",
        "transaction_date",
        "amount",
        "currency",
        "description",
        "reference",
        "account_number",
        "transaction_type",
    ),
    "invoices": (
        "id",
        "invoice_number",
        "customer",
        "invoice_date",
        "due_date",
        "amount",
        "currency",
        "status",
    ),
    "settlements": (
        "id",
        "settlement_reference",
        "transaction_date",
        "amount",
        "currency",
        "processor",
        "customer",
        "status",
    ),
}
ENTITY_TRUTH_COLUMNS = (
    "record_id",
    "source_type",
    "case_id",
    "scenario",
    "true_match_group_id",
    "expected_outcome",
)
RECONCILIATION_TRUTH_COLUMNS = (
    "case_id",
    "scenario",
    "bank_transaction_id",
    "expected_invoice_id",
    "expected_settlement_id",
    "true_match",
    "expected_status",
    "expected_reason",
    "true_match_group_id",
)

CUSTOMERS = (
    ("ABC Technologies Private Limited", "ABC Tech"),
    ("BlueRiver Consulting Services Pvt Ltd", "BlueRiver Consulting"),
    ("Crescent Retail Solutions Limited", "Crescent Retail"),
    ("Delta Manufacturing Industries Pvt Ltd", "Delta Mfg"),
    ("Evergreen Digital Commerce Private Limited", "Evergreen Digital"),
    ("Falcon Logistics and Supply Chain Ltd", "Falcon Logistics"),
    ("Greenfield Healthcare Systems Pvt Ltd", "Greenfield Health"),
    ("Horizon Business Services Private Limited", "Horizon Services"),
    ("Indus Data Analytics Solutions Ltd", "Indus Analytics"),
    ("Jupiter Financial Technology Pvt Ltd", "Jupiter FinTech"),
)
PROCESSORS = ("Razorpay", "Stripe", "Cashfree", "PayU", "Adyen")
AMOUNTS = (
    Decimal("10000.00"),
    Decimal("12500.00"),
    Decimal("20000.00"),
    Decimal("25000.00"),
    Decimal("50000.00"),
    Decimal("75000.00"),
    Decimal("100000.00"),
)
SCENARIO_WEIGHTS = {
    "normal": 42,
    "amount_mismatch": 10,
    "missing_settlement": 8,
    "duplicate_payment": 7,
    "date_mismatch": 8,
    "name_variation": 10,
    "currency_mismatch": 5,
    "partial_payment": 6,
    "unrelated": 4,
}
SCENARIO_ROW_COUNTS = {
    "normal": 3,
    "amount_mismatch": 3,
    "missing_settlement": 2,
    "duplicate_payment": 3,
    "date_mismatch": 3,
    "name_variation": 3,
    "currency_mismatch": 3,
    "partial_payment": 3,
    "unrelated": 3,
}


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@dataclass
class GeneratedData:
    bank_transactions: list[dict[str, str]] = field(default_factory=list)
    invoices: list[dict[str, str]] = field(default_factory=list)
    settlements: list[dict[str, str]] = field(default_factory=list)
    entity_ground_truth: list[dict[str, str]] = field(default_factory=list)
    reconciliation_ground_truth: list[dict[str, str]] = field(default_factory=list)
    scenario_counts: Counter[str] = field(default_factory=Counter)

    @property
    def source_record_count(self) -> int:
        return len(self.bank_transactions) + len(self.invoices) + len(self.settlements)


class SyntheticFinanceGenerator:
    """Build deterministic cases while keeping ground truth out of source CSVs."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.namespace = uuid5(NAMESPACE_DNS, f"ai-finance-controller:{seed}")
        self.sequence = 0
        self.case_sequence = 0
        self.data = GeneratedData()

    def _id(self, prefix: str) -> str:
        self.sequence += 1
        return str(uuid5(self.namespace, f"{prefix}:{self.sequence}"))

    def _case_id(self) -> str:
        self.case_sequence += 1
        return f"CASE-{self.case_sequence:06d}"

    def _base_date(self) -> date:
        return date(2026, 1, 1) + timedelta(days=self.rng.randint(0, 330))

    def _amount(self) -> Decimal:
        if self.rng.random() < 0.75:
            return self.rng.choice(AMOUNTS)
        return Decimal(self.rng.randrange(1_000, 250_001, 100)).quantize(Decimal("0.01"))

    def _customer(self) -> tuple[str, str]:
        return self.rng.choice(CUSTOMERS)

    def _invoice(
        self,
        case_id: str,
        customer: str,
        invoice_date: date,
        amount: Decimal,
        currency: str,
        status: str,
    ) -> dict[str, str]:
        invoice_id = self._id("invoice")
        return {
            "id": invoice_id,
            "invoice_number": f"INV-{case_id.removeprefix('CASE-')}",
            "customer": customer,
            "invoice_date": invoice_date.isoformat(),
            "due_date": (invoice_date + timedelta(days=self.rng.choice((15, 30, 45)))).isoformat(),
            "amount": money(amount),
            "currency": currency,
            "status": status,
        }

    def _bank(
        self,
        customer: str,
        transaction_date: date,
        amount: Decimal,
        currency: str,
        reference: str,
        description: str | None = None,
    ) -> dict[str, str]:
        return {
            "id": self._id("bank"),
            "transaction_date": transaction_date.isoformat(),
            "amount": money(amount),
            "currency": currency,
            "description": description or f"NEFT receipt from {customer}",
            "reference": reference,
            "account_number": f"XXXX{self.rng.randint(1000, 9999)}",
            "transaction_type": "credit",
        }

    def _settlement(
        self,
        case_id: str,
        customer: str,
        transaction_date: date,
        amount: Decimal,
    ) -> dict[str, str]:
        return {
            "id": self._id("settlement"),
            "settlement_reference": f"SET-{case_id.removeprefix('CASE-')}",
            "transaction_date": transaction_date.isoformat(),
            "amount": money(amount),
            "currency": "INR",
            "processor": self.rng.choice(PROCESSORS),
            "customer": customer,
            "status": "completed",
        }

    def _truth_entity(
        self,
        record: dict[str, str],
        source_type: str,
        case_id: str,
        scenario: str,
        group_id: str,
        outcome: str,
    ) -> None:
        self.data.entity_ground_truth.append(
            {
                "record_id": record["id"],
                "source_type": source_type,
                "case_id": case_id,
                "scenario": scenario,
                "true_match_group_id": group_id,
                "expected_outcome": outcome,
            }
        )

    def _truth_reconciliation(
        self,
        case_id: str,
        scenario: str,
        bank: dict[str, str],
        invoice: dict[str, str] | None,
        settlement: dict[str, str] | None,
        status: str,
        reason: str,
        group_id: str,
    ) -> None:
        self.data.reconciliation_ground_truth.append(
            {
                "case_id": case_id,
                "scenario": scenario,
                "bank_transaction_id": bank["id"],
                "expected_invoice_id": invoice["id"] if invoice else "",
                "expected_settlement_id": settlement["id"] if settlement else "",
                "true_match": "true" if group_id else "false",
                "expected_status": status,
                "expected_reason": reason,
                "true_match_group_id": group_id,
            }
        )

    def _commit_case(
        self,
        scenario: str,
        case_id: str,
        banks: list[dict[str, str]],
        invoices: list[dict[str, str]],
        settlements: list[dict[str, str]],
        status: str,
        reason: str,
        related: bool = True,
    ) -> None:
        group_id = self._id("group") if related else ""
        self.data.bank_transactions.extend(banks)
        self.data.invoices.extend(invoices)
        self.data.settlements.extend(settlements)
        outcome = status if related else "no_match"
        for record in banks:
            self._truth_entity(record, "bank_transaction", case_id, scenario, group_id, outcome)
        for record in invoices:
            self._truth_entity(record, "invoice", case_id, scenario, group_id, outcome)
        for record in settlements:
            self._truth_entity(record, "settlement", case_id, scenario, group_id, outcome)
        expected_invoice = invoices[0] if related and invoices else None
        expected_settlement = settlements[0] if related and settlements else None
        for bank in banks:
            self._truth_reconciliation(
                case_id,
                scenario,
                bank,
                expected_invoice,
                expected_settlement,
                status if related else "no_match",
                reason,
                group_id,
            )
        self.data.scenario_counts[scenario] += 1

    def normal(self) -> None:
        case_id = self._case_id()
        full_name, _ = self._customer()
        invoice_date = self._base_date()
        payment_date = invoice_date + timedelta(days=self.rng.randint(0, 2))
        amount = self._amount()
        invoice = self._invoice(case_id, full_name, invoice_date, amount, "INR", "paid")
        bank = self._bank(full_name, payment_date, amount, "INR", invoice["invoice_number"])
        settlement = self._settlement(case_id, full_name, payment_date, amount)
        self._commit_case("normal", case_id, [bank], [invoice], [settlement], "matched", "Exact amount, currency, reference, and nearby date.")

    def amount_mismatch(self) -> None:
        case_id = self._case_id()
        full_name, _ = self._customer()
        invoice_date = self._base_date()
        invoice_amount = self._amount()
        difference = max(Decimal("500.00"), (invoice_amount * Decimal("0.05")).quantize(Decimal("0.01")))
        paid_amount = invoice_amount - difference
        invoice = self._invoice(case_id, full_name, invoice_date, invoice_amount, "INR", "partial")
        bank = self._bank(full_name, invoice_date, paid_amount, "INR", invoice["invoice_number"])
        settlement = self._settlement(case_id, full_name, invoice_date, paid_amount)
        self._commit_case("amount_mismatch", case_id, [bank], [invoice], [settlement], "review", "Invoice amount differs from bank and settlement amounts.")

    def missing_settlement(self) -> None:
        case_id = self._case_id()
        full_name, _ = self._customer()
        invoice_date = self._base_date()
        amount = self._amount()
        invoice = self._invoice(case_id, full_name, invoice_date, amount, "INR", "paid")
        bank = self._bank(full_name, invoice_date, amount, "INR", invoice["invoice_number"])
        self._commit_case("missing_settlement", case_id, [bank], [invoice], [], "exception", "Expected settlement is missing.")

    def duplicate_payment(self) -> None:
        case_id = self._case_id()
        full_name, _ = self._customer()
        invoice_date = self._base_date()
        amount = self._amount()
        invoice = self._invoice(case_id, full_name, invoice_date, amount, "INR", "paid")
        bank_one = self._bank(full_name, invoice_date, amount, "INR", invoice["invoice_number"])
        bank_two = self._bank(full_name, invoice_date + timedelta(days=1), amount, "INR", invoice["invoice_number"])
        self._commit_case("duplicate_payment", case_id, [bank_one, bank_two], [invoice], [], "exception", "Two bank credits point to one invoice.")

    def date_mismatch(self) -> None:
        case_id = self._case_id()
        full_name, _ = self._customer()
        invoice_date = self._base_date()
        payment_date = invoice_date + timedelta(days=self.rng.randint(3, 14))
        amount = self._amount()
        invoice = self._invoice(case_id, full_name, invoice_date, amount, "INR", "paid")
        bank = self._bank(full_name, payment_date, amount, "INR", invoice["invoice_number"])
        settlement = self._settlement(case_id, full_name, payment_date, amount)
        self._commit_case("date_mismatch", case_id, [bank], [invoice], [settlement], "review", "Payment date is outside the normal matching window.")

    def name_variation(self) -> None:
        case_id = self._case_id()
        full_name, short_name = self._customer()
        invoice_date = self._base_date()
        amount = self._amount()
        invoice = self._invoice(case_id, full_name, invoice_date, amount, "INR", "paid")
        bank = self._bank(short_name, invoice_date, amount, "INR", invoice["invoice_number"], f"UPI receipt {short_name}")
        settlement = self._settlement(case_id, short_name, invoice_date, amount)
        self._commit_case("name_variation", case_id, [bank], [invoice], [settlement], "matched", "Normalized customer name, amount, and reference agree.")

    def currency_mismatch(self) -> None:
        case_id = self._case_id()
        full_name, _ = self._customer()
        invoice_date = self._base_date()
        amount = self._amount()
        invoice = self._invoice(case_id, full_name, invoice_date, amount, "USD", "open")
        bank = self._bank(full_name, invoice_date, amount, "INR", invoice["invoice_number"])
        settlement = self._settlement(case_id, full_name, invoice_date, amount)
        self._commit_case("currency_mismatch", case_id, [bank], [invoice], [settlement], "exception", "Invoice and bank currencies conflict.")

    def partial_payment(self) -> None:
        case_id = self._case_id()
        full_name, _ = self._customer()
        invoice_date = self._base_date()
        invoice_amount = max(self._amount(), Decimal("20000.00"))
        ratio = Decimal(str(self.rng.choice((0.4, 0.5, 0.6, 0.75))))
        paid_amount = (invoice_amount * ratio).quantize(Decimal("0.01"))
        invoice = self._invoice(case_id, full_name, invoice_date, invoice_amount, "INR", "partial")
        bank = self._bank(full_name, invoice_date, paid_amount, "INR", invoice["invoice_number"])
        settlement = self._settlement(case_id, full_name, invoice_date, paid_amount)
        self._commit_case("partial_payment", case_id, [bank], [invoice], [settlement], "review", "Bank and settlement represent a partial invoice payment.")

    def unrelated(self) -> None:
        case_id = self._case_id()
        customer_choices = self.rng.sample(CUSTOMERS, 3)
        invoice_name = customer_choices[0][0]
        bank_name = customer_choices[1][0]
        settlement_name = customer_choices[2][0]
        base_date = self._base_date()
        invoice = self._invoice(case_id, invoice_name, base_date, self._amount(), "INR", "open")
        bank = self._bank(bank_name, base_date + timedelta(days=45), self._amount() + Decimal("137.00"), "INR", f"UNRELATED-{self._id('reference')[:8]}")
        settlement = self._settlement(case_id, settlement_name, base_date + timedelta(days=75), self._amount() + Decimal("283.00"))
        # Each record is deliberately independent. Empty group IDs make any cross-source match false.
        self.data.bank_transactions.append(bank)
        self.data.invoices.append(invoice)
        self.data.settlements.append(settlement)
        for record, source in ((bank, "bank_transaction"), (invoice, "invoice"), (settlement, "settlement")):
            self._truth_entity(record, source, case_id, "unrelated", "", "no_match")
        self._truth_reconciliation(case_id, "unrelated", bank, None, None, "no_match", "No source record is related to another.", "")
        self.data.scenario_counts["unrelated"] += 1

    def unrelated_single_bank(self) -> None:
        case_id = self._case_id()
        full_name, _ = self._customer()
        bank = self._bank(full_name, self._base_date(), self._amount() + Decimal("91.00"), "INR", f"ORPHAN-{self._id('reference')[:8]}")
        self.data.bank_transactions.append(bank)
        self._truth_entity(bank, "bank_transaction", case_id, "unrelated", "", "no_match")
        self._truth_reconciliation(case_id, "unrelated", bank, None, None, "no_match", "Standalone bank record has no related invoice or settlement.", "")
        self.data.scenario_counts["unrelated"] += 1

    def generate(self, target_records: int) -> GeneratedData:
        if target_records <= 0:
            raise ValueError("target_records must be positive")
        methods: dict[str, Callable[[], None]] = {
            name: getattr(self, name) for name in SCENARIO_WEIGHTS
        }
        mandatory_total = sum(SCENARIO_ROW_COUNTS.values())
        if target_records >= mandatory_total:
            for scenario in SCENARIO_WEIGHTS:
                methods[scenario]()
        while self.data.source_record_count < target_records:
            remaining = target_records - self.data.source_record_count
            if remaining == 1:
                self.unrelated_single_bank()
                continue
            if remaining == 2:
                self.missing_settlement()
                continue
            eligible = [name for name, rows in SCENARIO_ROW_COUNTS.items() if rows <= remaining]
            weights = [SCENARIO_WEIGHTS[name] for name in eligible]
            methods[self.rng.choices(eligible, weights=weights, k=1)[0]]()
        validate_generated_data(self.data, target_records)
        return self.data


def validate_generated_data(data: GeneratedData, expected_records: int) -> None:
    if data.source_record_count != expected_records:
        raise ValueError(f"Expected {expected_records} source records, got {data.source_record_count}")
    source_rows = data.bank_transactions + data.invoices + data.settlements
    ids = [row["id"] for row in source_rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Generated source IDs are not unique")
    if len(data.entity_ground_truth) != expected_records:
        raise ValueError("Entity ground truth must contain one row per source record")
    source_ids = set(ids)
    for truth in data.reconciliation_ground_truth:
        if truth["bank_transaction_id"] not in source_ids:
            raise ValueError("Ground truth references an unknown bank transaction")
        for key in ("expected_invoice_id", "expected_settlement_id"):
            if truth[key] and truth[key] not in source_ids:
                raise ValueError(f"Ground truth references unknown {key}")
    if expected_records >= 100:
        missing = set(SCENARIO_WEIGHTS) - set(data.scenario_counts)
        if missing:
            raise ValueError(f"Required scenarios are missing: {sorted(missing)}")
    validate_scenario_semantics(data)


def validate_scenario_semantics(data: GeneratedData) -> None:
    """Verify that every generated case obeys its advertised financial scenario."""
    bank_by_id = {row["id"]: row for row in data.bank_transactions}
    invoice_by_id = {row["id"]: row for row in data.invoices}
    settlement_by_id = {row["id"]: row for row in data.settlements}
    entities_by_case: dict[str, list[dict[str, str]]] = {}
    truth_by_case: dict[str, list[dict[str, str]]] = {}
    for row in data.entity_ground_truth:
        entities_by_case.setdefault(row["case_id"], []).append(row)
    for row in data.reconciliation_ground_truth:
        truth_by_case.setdefault(row["case_id"], []).append(row)

    expected_status = {
        "normal": "matched",
        "amount_mismatch": "review",
        "missing_settlement": "exception",
        "duplicate_payment": "exception",
        "date_mismatch": "review",
        "name_variation": "matched",
        "currency_mismatch": "exception",
        "partial_payment": "review",
        "unrelated": "no_match",
    }

    for case_id, entity_truth in entities_by_case.items():
        scenarios = {row["scenario"] for row in entity_truth}
        if len(scenarios) != 1:
            raise ValueError(f"{case_id} has inconsistent scenario labels")
        scenario = scenarios.pop()
        case_truth = truth_by_case.get(case_id, [])
        if not case_truth:
            raise ValueError(f"{case_id} has no reconciliation ground truth")
        if any(row["expected_status"] != expected_status[scenario] for row in case_truth):
            raise ValueError(f"{case_id} has an incorrect expected status")
        expected_true_match = "false" if scenario == "unrelated" else "true"
        if any(row["true_match"] != expected_true_match for row in case_truth):
            raise ValueError(f"{case_id} has an incorrect true_match label")

        banks = [
            bank_by_id[row["record_id"]]
            for row in entity_truth
            if row["source_type"] == "bank_transaction"
        ]
        invoices = [
            invoice_by_id[row["record_id"]]
            for row in entity_truth
            if row["source_type"] == "invoice"
        ]
        settlements = [
            settlement_by_id[row["record_id"]]
            for row in entity_truth
            if row["source_type"] == "settlement"
        ]

        if scenario == "unrelated":
            if any(row["true_match_group_id"] for row in entity_truth):
                raise ValueError(f"{case_id} unrelated records have a match group")
            if any(
                row["expected_invoice_id"] or row["expected_settlement_id"]
                for row in case_truth
            ):
                raise ValueError(f"{case_id} unrelated records have expected links")
            if len({row.get("customer", row.get("description", "")) for row in invoices + settlements}) != len(invoices + settlements):
                raise ValueError(f"{case_id} unrelated customer identities are not distinct")
            continue

        if not banks or not invoices:
            raise ValueError(f"{case_id} related scenario lacks a bank record or invoice")
        bank_amounts = [Decimal(row["amount"]) for row in banks]
        invoice_amount = Decimal(invoices[0]["amount"])
        settlement_amounts = [Decimal(row["amount"]) for row in settlements]

        if scenario == "normal":
            if not (len(banks) == len(invoices) == len(settlements) == 1):
                raise ValueError(f"{case_id} normal scenario has incorrect cardinality")
            if not (invoice_amount == bank_amounts[0] == settlement_amounts[0]):
                raise ValueError(f"{case_id} normal amounts do not match")
            if invoices[0]["currency"] != banks[0]["currency"]:
                raise ValueError(f"{case_id} normal currencies do not match")
            date_gap = abs((date.fromisoformat(banks[0]["transaction_date"]) - date.fromisoformat(invoices[0]["invoice_date"])).days)
            if date_gap > 2:
                raise ValueError(f"{case_id} normal dates exceed tolerance")
        elif scenario == "amount_mismatch":
            if not settlements or invoice_amount == bank_amounts[0] or bank_amounts[0] != settlement_amounts[0]:
                raise ValueError(f"{case_id} amount mismatch is inaccurate")
        elif scenario == "missing_settlement":
            if settlements or invoice_amount != bank_amounts[0]:
                raise ValueError(f"{case_id} missing-settlement case is inaccurate")
        elif scenario == "duplicate_payment":
            if len(banks) != 2 or len(invoices) != 1 or settlements:
                raise ValueError(f"{case_id} duplicate-payment cardinality is inaccurate")
            if any(amount != invoice_amount for amount in bank_amounts):
                raise ValueError(f"{case_id} duplicate payment amounts differ")
        elif scenario == "date_mismatch":
            if not settlements or not (invoice_amount == bank_amounts[0] == settlement_amounts[0]):
                raise ValueError(f"{case_id} date-mismatch amounts are inaccurate")
            date_gap = abs((date.fromisoformat(banks[0]["transaction_date"]) - date.fromisoformat(invoices[0]["invoice_date"])).days)
            if date_gap < 3:
                raise ValueError(f"{case_id} date mismatch is inside normal tolerance")
        elif scenario == "name_variation":
            if not settlements or invoices[0]["customer"] == settlements[0]["customer"]:
                raise ValueError(f"{case_id} name variation is not actually different")
            if not (invoice_amount == bank_amounts[0] == settlement_amounts[0]):
                raise ValueError(f"{case_id} name-variation amounts differ")
        elif scenario == "currency_mismatch":
            if invoices[0]["currency"] == banks[0]["currency"]:
                raise ValueError(f"{case_id} currency mismatch uses equal currencies")
        elif scenario == "partial_payment":
            if not settlements or not (invoice_amount > bank_amounts[0] == settlement_amounts[0]):
                raise ValueError(f"{case_id} partial-payment amounts are inaccurate")


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_hidden_truth(path: Path, rows: list[dict[str, str]]) -> None:
    """Write evaluation-only JSON Lines with native booleans and null IDs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            truth = {
                "transaction_id": row["bank_transaction_id"],
                "invoice_id": row["expected_invoice_id"] or None,
                "settlement_id": row["expected_settlement_id"] or None,
                "true_match": row["true_match"] == "true",
                "expected_status": row["expected_status"],
                "scenario": row["scenario"],
                "reason": row["expected_reason"],
            }
            handle.write(json.dumps(truth, sort_keys=True) + "\n")
    temporary.replace(path)


def generate_dataset(
    records: int,
    seed: int,
    output_root: Path,
    dataset_name: str | None = None,
    clean: bool = False,
    truth_root: Path | None = None,
) -> dict[str, object]:
    name = dataset_name or f"synthetic_{records}_seed_{seed}"
    source_directory = output_root / "raw" / name
    truth_directory = (truth_root or output_root / "ground_truth") / name
    processed_directory = output_root / "processed" / name
    if clean:
        for directory in (source_directory, truth_directory, processed_directory):
            shutil.rmtree(directory, ignore_errors=True)
    start = time.perf_counter()
    data = SyntheticFinanceGenerator(seed).generate(records)
    write_csv(source_directory / "bank_transactions.csv", SOURCE_COLUMNS["bank_transactions"], data.bank_transactions)
    write_csv(source_directory / "invoices.csv", SOURCE_COLUMNS["invoices"], data.invoices)
    write_csv(source_directory / "settlements.csv", SOURCE_COLUMNS["settlements"], data.settlements)
    write_csv(truth_directory / "entity_ground_truth.csv", ENTITY_TRUTH_COLUMNS, data.entity_ground_truth)
    write_csv(truth_directory / "reconciliation_ground_truth.csv", RECONCILIATION_TRUTH_COLUMNS, data.reconciliation_ground_truth)
    hidden_truth_file = truth_directory / "hidden_truth.jsonl"
    write_hidden_truth(hidden_truth_file, data.reconciliation_ground_truth)
    elapsed = time.perf_counter() - start
    source_counts = {
        "bank_transactions": len(data.bank_transactions),
        "invoices": len(data.invoices),
        "settlements": len(data.settlements),
    }
    public_manifest: dict[str, object] = {
        "dataset_name": name,
        "requested_source_records": records,
        "generated_source_records": data.source_record_count,
        "source_counts": source_counts,
        "elapsed_seconds": round(elapsed, 6),
        "records_per_second": round(records / elapsed, 2) if elapsed else None,
        "source_directory": str(source_directory),
    }
    evaluation_manifest: dict[str, object] = {
        **public_manifest,
        "seed": seed,
        "ground_truth_counts": {
            "entity_ground_truth": len(data.entity_ground_truth),
            "reconciliation_ground_truth": len(data.reconciliation_ground_truth),
        },
        "scenario_case_counts": dict(sorted(data.scenario_counts.items())),
        "ground_truth_directory": str(truth_directory),
        "hidden_truth_file": str(hidden_truth_file),
    }
    processed_directory.mkdir(parents=True, exist_ok=True)
    public_manifest_file = processed_directory / "manifest.json"
    public_manifest_file.write_text(
        json.dumps(public_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    evaluation_manifest_file = truth_directory / "evaluation_manifest.json"
    evaluation_manifest_file.write_text(
        json.dumps(evaluation_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        **evaluation_manifest,
        "counts": {**source_counts, **evaluation_manifest["ground_truth_counts"]},
        "public_manifest_file": str(public_manifest_file),
        "evaluation_manifest_file": str(evaluation_manifest_file),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate reproducible reconciliation datasets and hidden ground truth."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--records", type=int, default=500, help="Exact total rows across the three source CSVs.")
    mode.add_argument("--all-presets", action="store_true", help="Generate 100, 500, 1,000, 5,000, and 10,000-row datasets.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--truth-root",
        type=Path,
        help="Optional evaluation-only root outside the application data mount.",
    )
    parser.add_argument("--dataset-name", help="Optional name; valid only with --records.")
    parser.add_argument("--clean", action="store_true", help="Remove a dataset directory before regenerating it.")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.all_presets and args.dataset_name:
        raise SystemExit("--dataset-name cannot be used with --all-presets")
    sizes = SUPPORTED_PRESETS if args.all_presets else (args.records,)
    manifests = []
    for size in sizes:
        manifest = generate_dataset(
            records=size,
            seed=args.seed + size if args.all_presets else args.seed,
            output_root=args.output_root,
            dataset_name=args.dataset_name,
            clean=args.clean,
            truth_root=args.truth_root,
        )
        manifests.append(manifest)
        if not args.quiet:
            counts = manifest["counts"]
            print(
                f"{manifest['dataset_name']}: {manifest['generated_source_records']:,} rows "
                f"({counts['bank_transactions']:,} bank, {counts['invoices']:,} invoices, "
                f"{counts['settlements']:,} settlements) in "
                f"{manifest['elapsed_seconds']:.3f}s"
            )
    if args.all_presets and not args.quiet:
        print(f"Generated {len(manifests)} preset datasets under {args.output_root}")


if __name__ == "__main__":
    main()
