import json
from pathlib import Path

import pytest

from evaluation.evaluate_run import build_scoreboard, render_text_report


def _files(root: Path) -> tuple[Path, Path, Path, Path]:
    truth = root / "truth.jsonl"
    predictions = root / "predictions.csv"
    summary = root / "summary.json"
    exceptions = root / "exceptions.csv"
    truth.write_text(
        json.dumps(
            {
                "transaction_id": "T1",
                "invoice_id": None,
                "settlement_id": None,
                "true_match": False,
                "expected_status": "no_match",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    predictions.write_text(
        "transaction_id,invoice_id,settlement_id,predicted_status\n"
        "T1,,,exception\n",
        encoding="utf-8",
    )
    summary.write_text(
        json.dumps(
            {
                "batch_size": 3,
                "records_processed": 1,
                "matched": 0,
                "review": 0,
                "exceptions": 1,
                "match_rate": 0,
                "processing_time_ms": 10,
                "records_per_second": 100,
                "full_cartesian_comparisons": 2,
                "candidate_records_examined": 0,
                "comparison_reduction": 100,
            }
        ),
        encoding="utf-8",
    )
    exceptions.write_text(
        "transaction_id,predicted_status,exception_type,best_candidate_id,"
        "best_candidate_type,confidence,reason,bank_amount,candidate_amount,"
        "amount_difference,currency\n"
        "T1,exception,no_match,,,0.0,No candidate,100,,,INR\n",
        encoding="utf-8",
    )
    return truth, predictions, summary, exceptions


def test_report_contains_required_metrics_and_exception_rows(tmp_path: Path) -> None:
    report = build_scoreboard(*_files(tmp_path))
    assert report["batch_size"] == 3
    assert report["total_records"] == 1
    assert report["false_matches"] == 0
    assert report["missed_matches"] == 0
    assert report["exception_rate"] == 1
    assert report["prediction_coverage"] == 1
    assert report["exception_report_complete"] is True
    assert report["exception_report"][0]["exception_type"] == "no_match"
    text = render_text_report(report)
    assert "F1 Score:" in text
    assert "Exception rate:" in text


def test_report_rejects_inconsistent_decision_counts(tmp_path: Path) -> None:
    truth, predictions, summary, exceptions = _files(tmp_path)
    value = json.loads(summary.read_text(encoding="utf-8"))
    value["matched"] = 1
    summary.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="decision counts"):
        build_scoreboard(truth, predictions, summary, exceptions)
