import json
import unittest
from datetime import date
from decimal import Decimal

from app.services.ingestion import IngestionValidationError, parse_and_normalize


class IngestionTests(unittest.TestCase):
    def test_bank_csv_is_cleaned_and_normalized(self) -> None:
        payload = (
            "id,transaction_date,amount,currency,account_number,transaction_type\n"
            "TX-1,2026-08-10,₹10\"\"000.00,inr,1234-5678,CREDIT\n"
        ).replace('₹10""000.00', '"₹10,000.00"').encode("utf-8")
        batch = parse_and_normalize("bank", payload, "csv")
        self.assertEqual(1, batch.received_records)
        record = batch.records[0]
        self.assertEqual(Decimal("10000.00"), record["amount"])
        self.assertEqual("INR", record["currency"])
        self.assertEqual("XXXX5678", record["account_number"])
        self.assertEqual("credit", record["transaction_type"])
        self.assertEqual(date(2026, 8, 10), record["transaction_date"])
        self.assertIsNone(record["description"])

    def test_invoice_json_is_normalized(self) -> None:
        payload = json.dumps(
            {
                "records": [
                    {
                        "id": "I-1",
                        "invoice_number": " INV-100 ",
                        "customer": "  ABC   Technologies ",
                        "invoice_date": "2026-08-10",
                        "due_date": "2026-09-09",
                        "amount": "20,000",
                        "currency": "inr",
                        "status": "OPEN",
                    }
                ]
            }
        ).encode()
        record = parse_and_normalize("invoices", payload, "json").records[0]
        self.assertEqual("INV-100", record["invoice_number"])
        self.assertEqual("ABC TECH", record["customer"])
        self.assertEqual(Decimal("20000.00"), record["amount"])
        self.assertEqual("INR", record["currency"])
        self.assertEqual("open", record["status"])

    def test_settlement_currency_is_required_and_normalized(self) -> None:
        payload = json.dumps(
            {
                "id": "S-1",
                "settlement_reference": "SET-1",
                "transaction_date": "2026-08-10",
                "amount": 10000,
                "currency": "usd",
                "processor": "Stripe",
                "customer": "ABC Technologies",
                "status": "COMPLETED",
            }
        ).encode()
        record = parse_and_normalize("settlements", payload, "json").records[0]
        self.assertEqual("USD", record["currency"])
        self.assertEqual("completed", record["status"])

    def test_missing_columns_are_reported(self) -> None:
        payload = b"id,transaction_date,currency,account_number,transaction_type\nTX-1,2026-08-10,INR,XXXX1234,credit\n"
        with self.assertRaises(IngestionValidationError) as context:
            parse_and_normalize("bank", payload, "csv")
        self.assertIn("missing_column", {issue.code for issue in context.exception.issues})
        self.assertIn("amount", {issue.field for issue in context.exception.issues})

    def test_invalid_date_negative_amount_and_currency_are_rejected(self) -> None:
        base = {
            "id": "TX-1",
            "transaction_date": "10/08/2026",
            "amount": "-100",
            "currency": "XYZ",
            "account_number": "XXXX1234",
            "transaction_type": "credit",
        }
        with self.assertRaises(IngestionValidationError) as context:
            parse_and_normalize("bank", json.dumps(base).encode(), "json")
        self.assertEqual("invalid_value", context.exception.issues[0].code)

        for field, value in (("transaction_date", "2026-08-10"), ("amount", "100")):
            base[field] = value
        with self.assertRaises(IngestionValidationError):
            parse_and_normalize("bank", json.dumps(base).encode(), "json")
        base["currency"] = "INR"
        record = parse_and_normalize("bank", json.dumps(base).encode(), "json").records[0]
        self.assertEqual(Decimal("100.00"), record["amount"])

    def test_compact_date_format_is_normalized(self) -> None:
        row = {
            "id": "TX-1", "transaction_date": "20260810", "amount": "100",
            "currency": "INR", "account_number": "XXXX1234",
            "transaction_type": "credit",
        }
        record = parse_and_normalize("bank", json.dumps(row).encode(), "json").records[0]
        self.assertEqual(date(2026, 8, 10), record["transaction_date"])

    def test_malformed_json_and_unexpected_columns_are_rejected(self) -> None:
        with self.assertRaises(IngestionValidationError) as malformed:
            parse_and_normalize("bank", b"{broken", "json")
        self.assertEqual("malformed_json", malformed.exception.issues[0].code)

        row = {
            "id": "TX-1", "transaction_date": "2026-08-10", "amount": "100",
            "currency": "INR", "account_number": "XXXX1234",
            "transaction_type": "credit", "unknown_field": "unsafe",
        }
        with self.assertRaises(IngestionValidationError) as unexpected:
            parse_and_normalize("bank", json.dumps(row).encode(), "json")
        self.assertEqual("unexpected_column", unexpected.exception.issues[0].code)

    def test_invoice_due_date_cannot_precede_invoice_date(self) -> None:
        row = {
            "id": "I-1", "invoice_number": "INV-1", "customer": "ABC",
            "invoice_date": "2026-08-10", "due_date": "2026-08-09",
            "amount": "100", "currency": "INR", "status": "open",
        }
        with self.assertRaises(IngestionValidationError) as context:
            parse_and_normalize("invoices", json.dumps(row).encode(), "json")
        self.assertIn("due_date", context.exception.issues[0].message)

    def test_exact_duplicates_are_skipped(self) -> None:
        row = {
            "id": "I-1",
            "invoice_number": "INV-1",
            "customer": "ABC",
            "invoice_date": "2026-08-10",
            "due_date": "2026-09-10",
            "amount": "10000",
            "currency": "INR",
            "status": "open",
        }
        batch = parse_and_normalize("invoices", json.dumps([row, row]).encode(), "json")
        self.assertEqual(2, batch.received_records)
        self.assertEqual(1, len(batch.records))
        self.assertEqual(1, batch.duplicate_records)

    def test_conflicting_duplicate_natural_key_is_rejected(self) -> None:
        first = {
            "id": "I-1", "invoice_number": "INV-1", "customer": "ABC",
            "invoice_date": "2026-08-10", "due_date": "2026-09-10",
            "amount": "10000", "currency": "INR", "status": "open",
        }
        second = {**first, "id": "I-2", "amount": "9500"}
        with self.assertRaises(IngestionValidationError) as context:
            parse_and_normalize("invoices", json.dumps([first, second]).encode(), "json")
        self.assertIn("duplicate_conflict", {issue.code for issue in context.exception.issues})

    def test_malformed_csv_row_is_rejected(self) -> None:
        payload = b"id,transaction_date,amount,currency,account_number,transaction_type\nTX-1,2026-08-10,100,INR,XXXX1234,credit,EXTRA\n"
        with self.assertRaises(IngestionValidationError) as context:
            parse_and_normalize("bank", payload, "csv")
        self.assertEqual("malformed_row", context.exception.issues[0].code)

    def test_upload_record_limit_is_enforced(self) -> None:
        row = {
            "id": "TX-1", "transaction_date": "2026-08-10", "amount": "100",
            "currency": "INR", "account_number": "XXXX1234",
            "transaction_type": "credit",
        }
        with self.assertRaises(IngestionValidationError) as context:
            parse_and_normalize("bank", json.dumps([row, {**row, "id": "TX-2"}]).encode(), "json", max_records=1)
        self.assertEqual("too_many_records", context.exception.issues[0].code)


if __name__ == "__main__":
    unittest.main()
