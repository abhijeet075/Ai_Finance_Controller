import csv
import tempfile
import unittest
from pathlib import Path

from scripts.generate_data import SCENARIO_WEIGHTS, SUPPORTED_PRESETS, generate_dataset


class SyntheticGeneratorTests(unittest.TestCase):
    def test_every_supported_size_is_exact_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for size in SUPPORTED_PRESETS:
                manifest = generate_dataset(size, seed=42 + size, output_root=root)
                counts = manifest["counts"]
                source_total = (
                    counts["bank_transactions"]
                    + counts["invoices"]
                    + counts["settlements"]
                )
                self.assertEqual(size, source_total)
                self.assertEqual(size, counts["entity_ground_truth"])
                self.assertEqual(set(SCENARIO_WEIGHTS), set(manifest["scenario_case_counts"]))

    def test_same_seed_produces_identical_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_root = Path(first)
            second_root = Path(second)
            first_manifest = generate_dataset(100, seed=2026, output_root=first_root)
            second_manifest = generate_dataset(100, seed=2026, output_root=second_root)
            first_source = Path(first_manifest["source_directory"])
            second_source = Path(second_manifest["source_directory"])
            for filename in ("bank_transactions.csv", "invoices.csv", "settlements.csv"):
                self.assertEqual(
                    (first_source / filename).read_bytes(),
                    (second_source / filename).read_bytes(),
                )

    def test_unrelated_records_have_no_true_match_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = generate_dataset(100, seed=99, output_root=Path(temporary))
            truth_path = Path(manifest["ground_truth_directory"]) / "entity_ground_truth.csv"
            with truth_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            unrelated = [row for row in rows if row["scenario"] == "unrelated"]
            self.assertTrue(unrelated)
            self.assertTrue(all(row["true_match_group_id"] == "" for row in unrelated))
            self.assertTrue(all(row["expected_outcome"] == "no_match" for row in unrelated))

    def test_duplicate_scenario_contains_two_bank_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = generate_dataset(100, seed=77, output_root=Path(temporary))
            truth_path = Path(manifest["ground_truth_directory"]) / "entity_ground_truth.csv"
            with truth_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            duplicate_cases: dict[str, list[dict[str, str]]] = {}
            for row in rows:
                if row["scenario"] == "duplicate_payment":
                    duplicate_cases.setdefault(row["case_id"], []).append(row)
            self.assertTrue(duplicate_cases)
            for case_rows in duplicate_cases.values():
                bank_count = sum(row["source_type"] == "bank_transaction" for row in case_rows)
                invoice_count = sum(row["source_type"] == "invoice" for row in case_rows)
                self.assertEqual(2, bank_count)
                self.assertEqual(1, invoice_count)


if __name__ == "__main__":
    unittest.main()
