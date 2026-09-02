"""Combine truth-isolated quality metrics with operational run metrics."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from evaluation.evaluate_reconciliation import (
    evaluate,
    load_hidden_truth,
    load_predictions,
)

EXCEPTION_COLUMNS = {
    "transaction_id",
    "predicted_status",
    "exception_type",
    "best_candidate_id",
    "best_candidate_type",
    "confidence",
    "reason",
}


def _load_exception_report(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = EXCEPTION_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"Exception report is missing columns: {sorted(missing)}"
            )
        return list(reader)


def build_scoreboard(
    truth_path: Path,
    predictions_path: Path,
    run_summary_path: Path,
    exception_report_path: Path | None = None,
) -> dict[str, Any]:
    evaluation = evaluate(
        load_hidden_truth(truth_path),
        load_predictions(predictions_path),
    )
    quality = evaluation["summary"]
    operational = json.loads(run_summary_path.read_text(encoding="utf-8"))
    total = int(operational["records_processed"])
    matched = int(operational["matched"])
    review = int(operational["review"])
    exceptions = int(operational["exceptions"])
    if matched + review + exceptions != total:
        raise ValueError("Run decision counts do not equal records_processed")
    processing_ms = int(operational["processing_time_ms"])
    exception_rows = _load_exception_report(exception_report_path)
    unresolved = review + exceptions
    prediction_count = int(quality["prediction_records"])
    return {
        "batch_size": int(operational.get("batch_size", total)),
        "total_records": total,
        "truth_records": int(quality["truth_records"]),
        "prediction_records": prediction_count,
        "matched": matched,
        "review": review,
        "exceptions": exceptions,
        "unresolved_records": unresolved,
        "match_rate": float(operational["match_rate"]),
        "precision": quality["precision"],
        "recall": quality["recall"],
        "f1_score": quality["f1_score"],
        "exact_link_accuracy": quality["exact_link_accuracy"],
        "status_accuracy": quality["status_accuracy"],
        "false_matches": quality["false_positives"],
        "missed_matches": quality["false_negatives"],
        "prediction_coverage": (
            round(prediction_count / total, 6) if total else 0.0
        ),
        "exception_rate": round(exceptions / total, 6) if total else 0.0,
        "exception_report_records": len(exception_rows),
        "exception_report_complete": len(exception_rows) == unresolved,
        "processing_time_ms": processing_ms,
        "processing_time_seconds": round(processing_ms / 1000, 6),
        "records_per_second": float(operational["records_per_second"]),
        "candidate_pruning": {
            "full_cartesian_comparisons": operational[
                "full_cartesian_comparisons"
            ],
            "candidate_records_examined": operational[
                "candidate_records_examined"
            ],
            "comparison_reduction": operational["comparison_reduction"],
        },
        "exception_report": exception_rows,
        "evaluation_discrepancies": evaluation["exceptions"],
    }


def render_text_report(scoreboard: dict[str, Any]) -> str:
    percent = lambda value: f"{float(value) * 100:.2f}%"
    lines = [
        "=" * 48,
        "AI FINANCE CONTROLLER — EVALUATION",
        "=" * 48,
        "",
        f"Batch size:          {scoreboard['batch_size']}",
        f"Total records:       {scoreboard['total_records']}",
        "",
        f"Matched:             {scoreboard['matched']}",
        f"Review:              {scoreboard['review']}",
        f"Exceptions:          {scoreboard['exceptions']}",
        f"Unresolved:          {scoreboard['unresolved_records']}",
        "",
        f"Match rate:          {percent(scoreboard['match_rate'])}",
        f"Precision:           {percent(scoreboard['precision'])}",
        f"Recall:              {percent(scoreboard['recall'])}",
        f"F1 Score:            {percent(scoreboard['f1_score'])}",
        "",
        f"False matches:       {scoreboard['false_matches']}",
        f"Missed matches:      {scoreboard['missed_matches']}",
        f"Exception rate:      {percent(scoreboard['exception_rate'])}",
        f"Prediction coverage: {percent(scoreboard['prediction_coverage'])}",
        "",
        f"Processing time:     {scoreboard['processing_time_seconds']:.3f} sec",
        f"Throughput:          {scoreboard['records_per_second']:.2f} records/sec",
        "=" * 48,
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build one honest quality and throughput report."
    )
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--run-summary", type=Path, required=True)
    parser.add_argument("--exceptions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--text-output", type=Path)
    args = parser.parse_args()
    scoreboard = build_scoreboard(
        args.truth,
        args.predictions,
        args.run_summary,
        args.exceptions,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(scoreboard, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    text = render_text_report(scoreboard)
    if args.text_output:
        args.text_output.parent.mkdir(parents=True, exist_ok=True)
        args.text_output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
