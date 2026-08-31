import json
from pathlib import Path

from evaluation.evaluate_run import build_scoreboard


def test_scoreboard_combines_quality_and_operational_metrics(tmp_path: Path) -> None:
    truth = tmp_path / "truth.jsonl"
    predictions = tmp_path / "predictions.csv"
    run_summary = tmp_path / "run-summary.json"
    truth.write_text(
        json.dumps(
            {
                "transaction_id": "B1",
                "invoice_id": "I1",
                "settlement_id": "S1",
                "true_match": True,
                "expected_status": "matched",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    predictions.write_text(
        "transaction_id,invoice_id,settlement_id,predicted_status\n"
        "B1,I1,S1,matched\n",
        encoding="utf-8",
    )
    run_summary.write_text(
        json.dumps(
            {
                "records_processed": 1,
                "matched": 1,
                "review": 0,
                "exceptions": 0,
                "match_rate": 1.0,
                "processing_time_ms": 5,
                "records_per_second": 200,
                "full_cartesian_comparisons": 2,
                "candidate_records_examined": 2,
                "comparison_reduction": 0,
            }
        ),
        encoding="utf-8",
    )
    result = build_scoreboard(truth, predictions, run_summary)
    assert result["precision"] == 1.0
    assert result["f1"] == 1.0
    assert result["records_per_second"] == 200
