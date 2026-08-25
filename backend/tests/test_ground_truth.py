import csv
import json
import tempfile
import unittest
from pathlib import Path

from evaluation.evaluate_reconciliation import evaluate, load_hidden_truth, load_predictions
from scripts.generate_data import generate_dataset


class GroundTruthTests(unittest.TestCase):
    def test_truth_is_hidden_and_public_manifest_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as public_temp, tempfile.TemporaryDirectory() as hidden_temp:
            public_root = Path(public_temp)
            hidden_root = Path(hidden_temp)
            manifest = generate_dataset(
                100,
                seed=42,
                output_root=public_root,
                truth_root=hidden_root,
                dataset_name="evaluation_case",
            )
            hidden_file = hidden_root / "evaluation_case" / "hidden_truth.jsonl"
            self.assertTrue(hidden_file.is_file())
            self.assertFalse((public_root / "ground_truth").exists())

            public_manifest = json.loads(
                Path(manifest["public_manifest_file"]).read_text(encoding="utf-8")
            )
            self.assertNotIn("seed", public_manifest)
            self.assertNotIn("scenario_case_counts", public_manifest)
            self.assertNotIn("ground_truth_directory", public_manifest)
            self.assertNotIn("hidden_truth_file", public_manifest)

    def test_source_files_contain_no_truth_labels(self) -> None:
        forbidden = {
            "true_match",
            "scenario",
            "case_id",
            "true_match_group_id",
            "expected_status",
        }
        with tempfile.TemporaryDirectory() as temporary:
            manifest = generate_dataset(100, seed=19, output_root=Path(temporary))
            source = Path(manifest["source_directory"])
            for path in source.glob("*.csv"):
                with path.open(encoding="utf-8", newline="") as handle:
                    header = set(next(csv.reader(handle)))
                self.assertTrue(forbidden.isdisjoint(header), path.name)

    def test_perfect_predictions_score_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = generate_dataset(100, seed=88, output_root=root)
            truth_path = Path(manifest["hidden_truth_file"])
            truth = load_hidden_truth(truth_path)
            prediction_path = root / "predictions.csv"
            with prediction_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "transaction_id",
                        "invoice_id",
                        "settlement_id",
                        "predicted_status",
                    ),
                )
                writer.writeheader()
                for row in truth.values():
                    writer.writerow(
                        {
                            "transaction_id": row["transaction_id"],
                            "invoice_id": row["invoice_id"] or "",
                            "settlement_id": row["settlement_id"] or "",
                            "predicted_status": row["expected_status"],
                        }
                    )
            report = evaluate(truth, load_predictions(prediction_path))
            self.assertEqual(1.0, report["summary"]["precision"])
            self.assertEqual(1.0, report["summary"]["recall"])
            self.assertEqual(1.0, report["summary"]["exact_link_accuracy"])
            self.assertEqual(1.0, report["summary"]["status_accuracy"])
            self.assertEqual([], report["exceptions"])

    def test_evaluator_counts_false_results_honestly(self) -> None:
        truth = {
            "T1": {"transaction_id": "T1", "invoice_id": "I1", "settlement_id": "S1", "true_match": True, "expected_status": "matched"},
            "T2": {"transaction_id": "T2", "invoice_id": "I2", "settlement_id": "S2", "true_match": True, "expected_status": "review"},
            "T3": {"transaction_id": "T3", "invoice_id": None, "settlement_id": None, "true_match": False, "expected_status": "no_match"},
            "T4": {"transaction_id": "T4", "invoice_id": None, "settlement_id": None, "true_match": False, "expected_status": "no_match"},
            "T5": {"transaction_id": "T5", "invoice_id": "I5", "settlement_id": None, "true_match": True, "expected_status": "exception"},
        }
        predictions = {
            "T1": {"transaction_id": "T1", "invoice_id": "I1", "settlement_id": "S1", "predicted_status": "matched"},
            "T2": {"transaction_id": "T2", "invoice_id": "WRONG", "settlement_id": "S2", "predicted_status": "review"},
            "T3": {"transaction_id": "T3", "invoice_id": "WRONG", "settlement_id": "", "predicted_status": "matched"},
            "T4": {"transaction_id": "T4", "invoice_id": "", "settlement_id": "", "predicted_status": "no_match"},
            "EXTRA": {"transaction_id": "EXTRA", "invoice_id": "IX", "settlement_id": "", "predicted_status": "matched"},
        }
        summary = evaluate(truth, predictions)["summary"]
        self.assertEqual(1, summary["true_positives"])
        self.assertEqual(3, summary["false_positives"])
        self.assertEqual(2, summary["false_negatives"])
        self.assertEqual(1, summary["true_negatives"])
        self.assertEqual(0.25, summary["precision"])
        self.assertEqual(0.333333, summary["recall"])
        self.assertEqual(0.4, summary["exact_link_accuracy"])
        self.assertEqual(0.6, summary["status_accuracy"])
        self.assertEqual(1, summary["missing_prediction_count"])
        self.assertEqual(1, summary["extra_prediction_count"])

    def test_application_package_does_not_reference_hidden_truth(self) -> None:
        app_root = Path(__file__).parents[1] / "app"
        for path in app_root.rglob("*.py"):
            source = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("hidden_truth", source, path)
            self.assertNotIn("ground_truth", source, path)


if __name__ == "__main__":
    unittest.main()
