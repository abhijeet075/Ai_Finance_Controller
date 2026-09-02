import unittest
from datetime import date, timedelta
from decimal import Decimal

from app.services.baseline_reconciliation import BankRecord, InvoiceRecord
from app.services.candidate_matching import (
    CandidateBatch,
    CandidateConfig,
    CandidateMatcher,
    SettlementRecord,
)

TODAY = date(2026, 8, 20)

def bank(amount="100", currency="INR"):
    return BankRecord(
        "TX1", TODAY, Decimal(amount), currency, "INV-1",
        "NEFT receipt from ABC Technologies",
    )


def invoice(record_id="I1", amount="100", number="INV-1", currency="INR"):
    return InvoiceRecord(
        record_id, number, "ABC Technologies Pvt Ltd", TODAY,
        Decimal(amount), currency,
    )


def settlement(record_id="S1", amount="100", currency="INR"):
    return SettlementRecord(
        record_id, f"SET-{record_id}", "ABC Tech", TODAY,
        Decimal(amount), currency,
    )


class CandidateMatchingTests(unittest.TestCase):
    def test_exact_candidates_score_one_hundred(self):
        result = CandidateMatcher([invoice()], [settlement()]).match_transaction(bank())
        self.assertEqual(Decimal("100.00"), result.invoices[0].score)
        self.assertEqual("I1", result.selected_invoice_id)
        self.assertEqual(Decimal("100.00"), result.settlements[0].score)

    def test_currency_is_a_hard_filter(self):
        result = CandidateMatcher(
            [invoice(currency="USD")], [settlement(currency="USD")]
        ).match_transaction(bank())
        self.assertEqual((), result.invoices)
        self.assertEqual((), result.settlements)

    def test_low_confidence_is_not_selected(self):
        weak = InvoiceRecord("I1", "OTHER", "Different Name", TODAY + timedelta(days=40),
                             Decimal("109"), "INR")
        result = CandidateMatcher([weak], []).match_transaction(bank())
        self.assertIsNone(result.selected_invoice_id)

    def test_close_scores_require_review(self):
        result = CandidateMatcher(
            [invoice("I1"), invoice("I2")], [],
            CandidateConfig(minimum_winner_margin=Decimal("10")),
        ).match_transaction(bank())
        self.assertIsNone(result.selected_invoice_id)
        self.assertEqual("insufficient_score_margin", result.invoice_selection_reason)

    def test_failed_settlements_are_excluded(self):
        failed = SettlementRecord(
            "S2", "SET-2", "ABC Tech", TODAY, Decimal("100"), "INR",
            status="failed",
        )
        result = CandidateMatcher([], [settlement(), failed]).match_transaction(bank())
        self.assertEqual(["S1"], [item.record_id for item in result.settlements])

    def test_index_reduces_comparisons(self):
        records = [
            invoice(f"I{number}", str(number * 100), f"INV-{number}")
            for number in range(1, 1001)
        ]
        result = CandidateMatcher(records, []).match_batch([bank("50000")])
        self.assertLess(result.examined_records, 150)
        self.assertGreater(result.comparison_reduction_percent, Decimal("85"))

    def test_results_are_deterministic(self):
        records = [invoice("I2", number="OTHER"), invoice("I1")]
        one = CandidateMatcher(records, []).match_transaction(bank())
        two = CandidateMatcher(list(reversed(records)), []).match_transaction(bank())
        self.assertEqual(one, two)
    def test_comparison_reduction_never_becomes_negative(self) -> None:
        batch = CandidateBatch(
        transactions=(),
        full_cartesian_comparisons=1,
        examined_records=2,
    )

        assert batch.comparison_reduction_percent == Decimal("0.00")

if __name__ == "__main__":
    unittest.main()

def test_comparison_reduction_never_becomes_negative() -> None:
    from decimal import Decimal

    from app.services.candidate_matching import CandidateBatch
    batch = CandidateBatch(transactions=(),full_cartesian_comparisons=1,examined_records=2,)
    assert batch.comparison_reduction_percent == Decimal("0.00")



