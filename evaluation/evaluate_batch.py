"""Run ingestion, Phase 10 reconciliation, and truth-isolated evaluation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.database import SessionLocal
from app.repositories.ingestion import store_batch
from app.services.ingestion import parse_and_normalize
from app.services.reconciliation import (
    export_exception_report_csv,
    export_predictions_csv,
    run_reconciliation,
)
from sqlalchemy.orm import Session

from evaluation.evaluate_run import build_scoreboard, render_text_report

SOURCE_FILES = {
    "bank": "bank_transactions.csv",
    "invoices": "invoices.csv",
    "settlements": "settlements.csv",
}


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def evaluate_batch(
    session: Session,
    source_dir: Path,
    truth_path: Path,
    source_batch: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Execute the real persisted controller run before loading hidden truth."""
    source_batch = source_batch.strip()
    if not source_batch:
        raise ValueError("source_batch cannot be blank")
    source_dir = source_dir.resolve()
    truth_path = truth_path.resolve()
    if source_dir in truth_path.parents:
        raise ValueError("Hidden truth must not be stored inside the source directory")
    if not truth_path.is_file():
        raise FileNotFoundError(f"Missing hidden truth file: {truth_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    batch_size = 0
    batches = []
    for source, filename in SOURCE_FILES.items():
        path = source_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing source file: {path}")
        batch = parse_and_normalize(
            source,
            path.read_bytes(),
            "csv",
            max_records=settings.max_upload_records,
        )
        for record in batch.records:
            record["source_batch"] = source_batch
        batches.append(batch)
        batch_size += batch.received_records

    try:
        for batch in batches:
            store_batch(session, batch, commit=False)
        session.commit()
    except Exception:
        session.rollback()
        raise

    summary = run_reconciliation(session, source_batch)
    run_summary = {**asdict(summary), "batch_size": batch_size}
    run_summary_path = output_dir / "run-summary.json"
    predictions_path = output_dir / "predictions.csv"
    exceptions_path = output_dir / "exceptions.csv"
    _write_json(run_summary_path, run_summary)
    predictions_path.write_text(
        export_predictions_csv(session, summary.run_id),
        encoding="utf-8",
    )
    exceptions_path.write_text(
        export_exception_report_csv(session, summary.run_id),
        encoding="utf-8",
    )
    scoreboard = build_scoreboard(
        truth_path,
        predictions_path,
        run_summary_path,
        exceptions_path,
    )
    scoreboard["run_id"] = summary.run_id
    scoreboard["source_batch"] = source_batch
    if scoreboard["truth_records"] != scoreboard["total_records"]:
        raise RuntimeError("Hidden truth does not cover every bank transaction")
    if scoreboard["prediction_records"] != scoreboard["total_records"]:
        raise RuntimeError("Prediction export does not cover every bank transaction")
    if not scoreboard["exception_report_complete"]:
        raise RuntimeError("Exception report does not cover every unresolved transaction")
    _write_json(output_dir / "evaluation-report.json", scoreboard)
    (output_dir / "evaluation-report.txt").write_text(
        render_text_report(scoreboard),
        encoding="utf-8",
    )
    return scoreboard


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one persisted reconciliation batch and evaluate it."
    )
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--source-batch", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    with SessionLocal() as session:
        report = evaluate_batch(
            session,
            args.source_dir,
            args.truth,
            args.source_batch,
            args.output_dir,
        )
    print(render_text_report(report), end="")


if __name__ == "__main__":
    main()
