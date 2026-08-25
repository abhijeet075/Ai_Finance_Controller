"""Evaluate reconciliation predictions against hidden ground truth.

This module is intentionally outside ``backend/app``. The application produces
predictions; only this offline evaluator receives the truth file.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

PREDICTION_COLUMNS = {
    "transaction_id",
    "invoice_id",
    "settlement_id",
    "predicted_status",
}


def _optional_id(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def load_hidden_truth(path: Path) -> dict[str, dict[str, Any]]:
    truth: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            required = {
                "transaction_id",
                "invoice_id",
                "settlement_id",
                "true_match",
                "expected_status",
            }
            missing = required - set(row)
            if missing:
                raise ValueError(f"Truth line {line_number} is missing {sorted(missing)}")
            transaction_id = str(row["transaction_id"])
            if transaction_id in truth:
                raise ValueError(f"Duplicate truth transaction_id: {transaction_id}")
            if not transaction_id.strip():
                raise ValueError(f"Truth line {line_number} has an empty transaction_id")
            if not isinstance(row["true_match"], bool):
                raise ValueError(f"Truth line {line_number} true_match must be boolean")
            if row["expected_status"] not in {"matched", "review", "exception", "no_match"}:
                raise ValueError(f"Truth line {line_number} has an invalid expected_status")
            invoice_id = row.get("invoice_id")
            settlement_id = row.get("settlement_id")
            if invoice_id is not None and not isinstance(invoice_id, str):
                raise ValueError(f"Truth line {line_number} invoice_id must be string or null")
            if settlement_id is not None and not isinstance(settlement_id, str):
                raise ValueError(f"Truth line {line_number} settlement_id must be string or null")
            if row["true_match"] and not (invoice_id or settlement_id):
                raise ValueError(f"Truth line {line_number} true match has no linked record")
            if not row["true_match"] and (invoice_id or settlement_id):
                raise ValueError(f"Truth line {line_number} false match contains linked IDs")
            truth[transaction_id] = row
    if not truth:
        raise ValueError("Hidden truth file is empty")
    return truth


def load_predictions(path: Path) -> dict[str, dict[str, str]]:
    predictions: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = PREDICTION_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Prediction CSV is missing columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            transaction_id = (row.get("transaction_id") or "").strip()
            if not transaction_id:
                raise ValueError(f"Prediction line {line_number} has no transaction_id")
            if transaction_id in predictions:
                raise ValueError(f"Duplicate prediction transaction_id: {transaction_id}")
            predictions[transaction_id] = row
    return predictions


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def evaluate(
    truth: dict[str, dict[str, Any]],
    predictions: dict[str, dict[str, str]],
) -> dict[str, Any]:
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    true_negatives = 0
    exact_link_correct = 0
    status_correct = 0
    missing_predictions: list[str] = []
    exceptions: list[dict[str, Any]] = []

    for transaction_id, expected in truth.items():
        prediction = predictions.get(transaction_id)
        if prediction is None:
            missing_predictions.append(transaction_id)
            if expected["true_match"]:
                false_negatives += 1
            exceptions.append(
                {
                    "transaction_id": transaction_id,
                    "issue": "missing_prediction",
                    "expected_status": expected["expected_status"],
                }
            )
            continue

        expected_invoice = _optional_id(expected.get("invoice_id"))
        expected_settlement = _optional_id(expected.get("settlement_id"))
        predicted_invoice = _optional_id(prediction.get("invoice_id"))
        predicted_settlement = _optional_id(prediction.get("settlement_id"))
        predicted_match = bool(predicted_invoice or predicted_settlement)
        links_exact = (
            predicted_invoice == expected_invoice
            and predicted_settlement == expected_settlement
        )

        if expected["true_match"]:
            if links_exact:
                true_positives += 1
                exact_link_correct += 1
            else:
                false_negatives += 1
                if predicted_match:
                    false_positives += 1
        elif predicted_match:
            false_positives += 1
        else:
            true_negatives += 1
            exact_link_correct += 1

        predicted_status = (prediction.get("predicted_status") or "").strip()
        status_matches = predicted_status == expected["expected_status"]
        if status_matches:
            status_correct += 1

        if not links_exact or not status_matches:
            exceptions.append(
                {
                    "transaction_id": transaction_id,
                    "issue": "incorrect_prediction",
                    "expected_invoice_id": expected_invoice,
                    "predicted_invoice_id": predicted_invoice,
                    "expected_settlement_id": expected_settlement,
                    "predicted_settlement_id": predicted_settlement,
                    "expected_status": expected["expected_status"],
                    "predicted_status": predicted_status,
                    "scenario": expected.get("scenario"),
                }
            )

    extra_prediction_ids = sorted(set(predictions) - set(truth))
    false_positives += len(extra_prediction_ids)
    for transaction_id in extra_prediction_ids:
        exceptions.append(
            {"transaction_id": transaction_id, "issue": "unknown_prediction"}
        )

    precision = _ratio(true_positives, true_positives + false_positives)
    recall = _ratio(true_positives, true_positives + false_negatives)
    f1 = _ratio(2 * true_positives, 2 * true_positives + false_positives + false_negatives)
    total_truth = len(truth)
    return {
        "summary": {
            "truth_records": total_truth,
            "prediction_records": len(predictions),
            "evaluated_records": total_truth - len(missing_predictions),
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "true_negatives": true_negatives,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "exact_link_accuracy": _ratio(exact_link_correct, total_truth),
            "status_accuracy": _ratio(status_correct, total_truth),
            "missing_prediction_count": len(missing_predictions),
            "extra_prediction_count": len(extra_prediction_ids),
            "exception_count": len(exceptions),
        },
        "missing_prediction_ids": missing_predictions,
        "extra_prediction_ids": extra_prediction_ids,
        "exceptions": exceptions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate application predictions against hidden truth."
    )
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = evaluate(
        load_hidden_truth(args.truth),
        load_predictions(args.predictions),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
