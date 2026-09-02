from datetime import date, timedelta
from decimal import Decimal

from app.services.baseline_reconciliation import BankRecord, InvoiceRecord
from app.services.candidate_matching import CandidateConfig, CandidateMatcher, SettlementRecord
from app.services.decision_engine import decide_reconciliation

TODAY = date(2026, 8, 31)


def test_global_assignment_sends_competing_transaction_to_review() -> None:
    banks = [
        BankRecord(
            "B1",
            TODAY,
            Decimal("100"),
            "INR",
            "INV-1",
            "PAYMENT ALPHA PRIMARY",
            customer="ALPHA",
        ),
        BankRecord(
            "B2",
            TODAY + timedelta(days=1),
            Decimal("100"),
            "INR",
            "INV-1",
            "PAYMENT ALPHA SECONDARY",
            customer="ALPHA",
        ),
    ]
    invoices = [InvoiceRecord("I1", "INV-1", "ALPHA", TODAY, Decimal("100"), "INR")]
    settlements = [
        SettlementRecord("S1", "SET-1", "ALPHA", TODAY, Decimal("100"), "INR")
    ]
    candidates = CandidateMatcher(invoices, settlements).match_batch(banks)
    result = decide_reconciliation(candidates, banks, invoices, settlements)
    by_id = {item.bank_transaction_id: item for item in result.decisions}
    assert by_id["B1"].status == "matched"
    assert by_id["B2"].status == "review"
    assert by_id["B2"].exception_type == "ambiguous_match"
    assert sum(item.invoice_id == "I1" for item in result.decisions) == 1
    assert sum(item.settlement_id == "S1" for item in result.decisions) == 1


def test_missing_settlement_is_review() -> None:
    bank = BankRecord("B1", TODAY, Decimal("100"), "INR", "INV-1", customer="ALPHA")
    invoice = InvoiceRecord("I1", "INV-1", "ALPHA", TODAY, Decimal("100"), "INR")
    candidates = CandidateMatcher([invoice], []).match_batch([bank])
    decision = decide_reconciliation(candidates, [bank], [invoice], []).decisions[0]
    assert decision.status == "review"
    assert decision.invoice_id == "I1"
    assert decision.exception_type == "missing_settlement"
    assert decision.best_candidate_id == "I1"
    assert decision.best_candidate_type == "invoice"
    assert decision.best_candidate_amount == Decimal("100.00")
    assert decision.amount_difference == Decimal("0.00")


def test_duplicate_payments_are_not_auto_assigned() -> None:
    banks = [
        BankRecord("B1", TODAY, Decimal("100"), "INR", "INV-1", "PAYMENT ALPHA"),
        BankRecord("B2", TODAY, Decimal("100"), "INR", "INV-1", "PAYMENT ALPHA"),
    ]
    invoice = InvoiceRecord("I1", "INV-1", "ALPHA", TODAY, Decimal("100"), "INR")
    candidates = CandidateMatcher(
        [invoice], [], CandidateConfig(confidence_threshold=Decimal("60"))
    ).match_batch(banks)
    result = decide_reconciliation(candidates, banks, [invoice], [])
    assert {item.exception_type for item in result.decisions} == {"duplicate_payment"}
    assert all(item.invoice_id is None for item in result.decisions)


def test_missing_descriptions_alone_do_not_create_duplicates() -> None:
    banks = [
        BankRecord("B1", TODAY, Decimal("100"), "INR", "INV-1"),
        BankRecord("B2", TODAY, Decimal("100"), "INR", "INV-2"),
    ]
    candidates = CandidateMatcher([], []).match_batch(banks)
    decisions = decide_reconciliation(candidates, banks, [], []).decisions
    assert all(item.exception_type == "no_match" for item in decisions)


def test_currency_and_reference_amount_mismatches_are_classified() -> None:
    currency_bank = BankRecord("B1", TODAY, Decimal("100"), "USD", "OTHER")
    amount_bank = BankRecord("B2", TODAY, Decimal("90"), "INR", "INV-2")
    invoices = [
        InvoiceRecord("I1", "INV-1", "ALPHA", TODAY, Decimal("100"), "INR"),
        InvoiceRecord("I2", "INV-2", "BETA", TODAY, Decimal("100"), "INR"),
    ]
    candidates = CandidateMatcher(invoices, []).match_batch([currency_bank, amount_bank])
    decisions = decide_reconciliation(
        candidates, [currency_bank, amount_bank], invoices, []
    ).decisions
    by_id = {item.bank_transaction_id: item for item in decisions}
    assert by_id["B1"].exception_type == "currency_mismatch"
    assert by_id["B1"].severity == "critical"
    assert by_id["B1"].best_candidate_id == "I1"
    assert by_id["B1"].best_candidate_amount == Decimal("100.00")
    assert by_id["B1"].amount_difference == Decimal("0.00")
    assert by_id["B2"].exception_type == "amount_mismatch"
    assert by_id["B2"].best_candidate_id == "I2"
    assert by_id["B2"].best_candidate_amount == Decimal("100.00")
    assert by_id["B2"].amount_difference == Decimal("10.00")


def test_debits_cannot_consume_invoice_or_settlement_assignments() -> None:
    bank = BankRecord(
        "B1",
        TODAY,
        Decimal("100"),
        "INR",
        "INV-1",
        customer="ALPHA",
        transaction_type="debit",
    )
    invoice = InvoiceRecord("I1", "INV-1", "ALPHA", TODAY, Decimal("100"), "INR")
    settlement = SettlementRecord(
        "S1", "SET-1", "ALPHA", TODAY, Decimal("100"), "INR"
    )
    candidates = CandidateMatcher([invoice], [settlement]).match_batch([bank])
    decision = decide_reconciliation(
        candidates, [bank], [invoice], [settlement]
    ).decisions[0]
    assert decision.status == "exception"
    assert decision.exception_type == "no_match"
    assert decision.invoice_id is None
    assert decision.settlement_id is None
    assert decision.reason == "Debit transactions are outside the receivables workflow."


def test_failed_settlement_does_not_create_currency_mismatch() -> None:
    bank = BankRecord("B1", TODAY, Decimal("100"), "USD", "NONE")
    failed = SettlementRecord(
        "S1", "SET-1", "ALPHA", TODAY, Decimal("100"), "INR", status="failed"
    )
    candidates = CandidateMatcher([], [failed]).match_batch([bank])
    decision = decide_reconciliation(candidates, [bank], [], [failed]).decisions[0]
    assert decision.exception_type == "no_match"
