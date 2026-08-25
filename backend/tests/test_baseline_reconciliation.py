import unittest
from datetime import date, timedelta
from decimal import Decimal

from app.services.baseline_reconciliation import (
    BankRecord,
    InvoiceRecord,
    ReconciliationConfig,
    reconcile,
)

TODAY = date(2026, 8, 20)

def bank(
    record_id="B1", amount="100", reference=None,
    description="NEFT receipt from ABC Technologies", days=0,
    currency="INR", transaction_type="credit",
):
    return BankRecord(record_id, TODAY + timedelta(days=days), Decimal(amount), currency,
                      reference, description, None, transaction_type)

def invoice(
    record_id="I1", number="INV-1", amount="100",
    customer="ABC Technologies Pvt. Ltd.", days=0, currency="INR",
):
    return InvoiceRecord(record_id, number, customer, TODAY + timedelta(days=days),
                         Decimal(amount), currency)

class BaselineTests(unittest.TestCase):
    def test_exact_reference(self):
        decision = reconcile([bank(reference=" inv-1 ", amount="90")], [invoice()]).decisions[0]
        self.assertEqual(("matched", "exact_reference"), (decision.status, decision.rule))

    def test_amount_customer(self):
        decision = reconcile([bank()], [invoice(number="OTHER", days=-20)]).decisions[0]
        self.assertEqual(
            ("matched", "exact_amount_customer"),
            (decision.status, decision.rule),
        )

    def test_amount_date_three_day_boundary(self):
        decision = reconcile(
            [bank(description=None, days=3)],
            [invoice(number="OTHER")],
        ).decisions[0]
        self.assertEqual(("review", "amount_date"), (decision.status, decision.rule))

    def test_amount_tolerance_inclusive(self):
        config = ReconciliationConfig(amount_tolerance=Decimal("1"))
        decision = reconcile([bank(amount="101", description=None, days=10)],
                             [invoice(number="OTHER")], config).decisions[0]
        self.assertEqual("amount_tolerance", decision.rule)

    def test_duplicate_detection(self):
        result = reconcile([bank("B1"), bank("B2")], [invoice()])
        self.assertEqual(1, len(result.duplicate_groups))
        self.assertEqual({"duplicate"}, {item.rule for item in result.decisions})

    def test_currency_mismatch(self):
        decision = reconcile([bank(reference="INV-1", currency="USD")], [invoice()]).decisions[0]
        self.assertEqual(("exception", "currency_mismatch"), (decision.status, decision.rule))

    def test_equal_candidates_are_ambiguous(self):
        result = reconcile([bank(description=None)], [invoice("I1", "A"), invoice("I2", "B")])
        self.assertEqual("ambiguous", result.decisions[0].rule)
        self.assertIsNone(result.decisions[0].invoice_id)

    def test_missing_description_does_not_create_duplicates(self):
        result = reconcile([bank("B1", description=None), bank("B2", description=None)], [])
        self.assertEqual(0, len(result.duplicate_groups))

    def test_deterministic_order(self):
        banks = [bank("B2", reference="INV-2"), bank("B1", reference="INV-1")]
        invoices = [invoice("I2", "INV-2"), invoice("I1", "INV-1")]
        one = reconcile(banks, invoices)
        two = reconcile(list(reversed(banks)), list(reversed(invoices)))
        self.assertEqual(one, two)

if __name__ == "__main__":
    unittest.main()
