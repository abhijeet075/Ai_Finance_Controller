import unittest
from datetime import date, datetime
from decimal import Decimal

from app.services.normalization import (
    NormalizationError,
    normalize_amount,
    normalize_currency,
    normalize_date,
    normalize_description,
    normalize_name,
)


class NormalizationTests(unittest.TestCase):
    def test_company_name_variants_share_one_key(self) -> None:
        variants = (
            "ABC Technologies Pvt. Ltd.",
            " ABC   Tech ",
            "ABC TECHNOLOGIES",
        )
        self.assertEqual({"ABC TECH"}, {normalize_name(value) for value in variants})

    def test_name_normalizes_unicode_and_legal_suffixes(self) -> None:
        self.assertEqual("CAFE AND SONS", normalize_name("Café & Sons, LLC"))
        self.assertEqual("ABC", normalize_name("ABC & Co."))

    def test_description_expands_abbreviations(self) -> None:
        left = normalize_description(" PMT--to ABC / inv-100 ")
        right = normalize_description("payment to abc invoice 100")
        self.assertEqual("PAYMENT TO ABC INVOICE 100", left)
        self.assertEqual(left, right)

    def test_amount_normalizes_localized_grouping(self) -> None:
        self.assertEqual(Decimal("1234.56"), normalize_amount("$1,234.56"))
        self.assertEqual(Decimal("1234.56"), normalize_amount("EUR 1.234,56"))
        self.assertEqual(Decimal("123456.78"), normalize_amount("\u20b91,23,456.78"))
        self.assertEqual(Decimal("123456.00"), normalize_amount("1,23,456"))

    def test_amount_handles_signs_and_invalid_values(self) -> None:
        self.assertEqual(Decimal("-10.24"), normalize_amount("(10.2350)"))
        for invalid in ("NaN", "10O.00"):
            with self.assertRaises(NormalizationError):
                normalize_amount(invalid)
        with self.assertRaises(NormalizationError):
            normalize_amount("-1", allow_negative=False)
        with self.assertRaises(NormalizationError):
            normalize_amount("(-10)")

    def test_date_normalizes_unambiguous_formats(self) -> None:
        expected = date(2026, 8, 17)
        values = (
            "2026-08-17",
            "2026/08/17",
            "20260817",
            "17/08/2026",
            "17 Aug 2026",
            datetime(2026, 8, 17, 12, 30),
        )
        self.assertEqual({expected}, {normalize_date(value) for value in values})

    def test_date_requires_hint_when_ambiguous(self) -> None:
        with self.assertRaises(NormalizationError):
            normalize_date("08/10/2026")
        self.assertEqual(date(2026, 10, 8), normalize_date("08/10/2026", day_first=True))
        self.assertEqual(date(2026, 8, 10), normalize_date("08/10/2026", day_first=False))

    def test_currency_normalizes_codes_symbols_and_names(self) -> None:
        self.assertEqual("INR", normalize_currency("rupees"))
        self.assertEqual("INR", normalize_currency("\u20b9"))
        self.assertEqual("USD", normalize_currency("us dollars"))
        self.assertEqual("EUR", normalize_currency("\u20ac"))
        self.assertEqual("AUD", normalize_currency("A$"))
        self.assertEqual("CAD", normalize_currency("$", default="CAD"))
        with self.assertRaises(NormalizationError):
            normalize_currency("$")
        with self.assertRaises(NormalizationError):
            normalize_currency("XYZ")

    def test_normalizers_are_idempotent(self) -> None:
        name = normalize_name("ABC Technologies Pvt. Ltd.")
        description = normalize_description("PMT for inv-100")
        currency = normalize_currency("rupees")
        amount = normalize_amount("INR 1,234.50")
        normalized_date = normalize_date("20260817")
        self.assertEqual(name, normalize_name(name))
        self.assertEqual(description, normalize_description(description))
        self.assertEqual(currency, normalize_currency(currency))
        self.assertEqual(amount, normalize_amount(amount))
        self.assertEqual(normalized_date, normalize_date(normalized_date))


if __name__ == "__main__":
    unittest.main()
