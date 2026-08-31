"""Combine truth-isolated quality metrics with operational run metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.evaluate_reconciliation import evaluate, load_hidden_truth, load_predictions


def build_scoreboard(
    truth_path: Path,
    predictions_path: Path,
    run_summary_path: Path,
) -> dict[str, object]:
    quality = evaluate(load_hidden_truth(truth_path), load_predictions(predictions_path))["summary"]
    operational = json.loads(run_summary_path.read_text(encoding="utf-8"))
    return {
        "records_processed": operational["records_processed"],
        "matched": operational["matched"],
        "review": operational["review"],
        "exceptions": operational["exceptions"],
        "match_rate": operational["match_rate"],
        "precision": quality["precision"],
        "recall": quality["recall"],
        "f1": quality["f1_score"],
        "exact_link_accuracy": quality["exact_link_accuracy"],
        "status_accuracy": quality["status_accuracy"],
        "processing_time_ms": operational["processing_time_ms"],
        "records_per_second": operational["records_per_second"],
        "candidate_pruning": {
            "full_cartesian_comparisons": operational["full_cartesian_comparisons"],
            "candidate_records_examined": operational["candidate_records_examined"],
            "comparison_reduction": operational["comparison_reduction"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--run-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scoreboard = build_scoreboard(args.truth, args.predictions, args.run_summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(scoreboard, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(scoreboard, indent=2))


if __name__ == "__main__":
    main()
