import json
from pathlib import Path

from evaluation.evaluate_run import build_scoreboard, render_text_report


def test_scoreboard_combines_quality_and_operational_metrics(tmp_path: Path) -> None:
    truth = tmp_path / "truth.jsonl"
    predictions = tmp_path / "predictions.csv"
    run_summary = tmp_path / "run-summary.json"
    exceptions = tmp_path / "exceptions.csv"
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
    exceptions.write_text(
        "transaction_id,predicted_status,exception_type,best_candidate_id,"
        "best_candidate_type,confidence,reason,bank_amount,candidate_amount,"
        "amount_difference,currency\n",
        encoding="utf-8",
    )
    result = build_scoreboard(truth, predictions, run_summary, exceptions)
    assert result["precision"] == 1.0
    assert result["f1_score"] == 1.0
    assert result["records_per_second"] == 200
    assert result["false_matches"] == 0
    assert result["missed_matches"] == 0
    assert result["exception_rate"] == 0
    assert result["prediction_coverage"] == 1
    assert result["exception_report_complete"] is True
    text = render_text_report(result)
    assert "AI FINANCE CONTROLLER — EVALUATION" in text
    assert "Throughput:          200.00 records/sec" in text
