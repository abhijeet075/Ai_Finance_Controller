"""Evaluate the required batch-size matrix through real Phase 10 runs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from app.database import SessionLocal

from evaluation.evaluate_batch import evaluate_batch

REQUIRED_SIZES = {50, 100, 500, 1_000, 5_000}
COLUMNS = (
    "batch_size",
    "match_rate",
    "precision",
    "recall",
    "f1_score",
    "processing_time_seconds",
    "records_per_second",
)


def evaluate_matrix(
    manifest_path: Path,
    output_dir: Path,
    require_all_sizes: bool = True,
) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    batches = manifest.get("batches", [])
    if not isinstance(batches, list) or not batches:
        raise ValueError("Evaluation manifest must contain a non-empty batches list")
    required = {"batch_size", "source_batch", "source_dir", "truth"}
    for index, item in enumerate(batches):
        if not isinstance(item, dict):
            raise ValueError(f"Batch entry {index} must be an object")
        missing_keys = required - set(item)
        if missing_keys:
            raise ValueError(
                f"Batch entry {index} is missing keys: {sorted(missing_keys)}"
            )
    declared_sizes = [int(item["batch_size"]) for item in batches]
    if len(declared_sizes) != len(set(declared_sizes)):
        raise ValueError("Evaluation manifest contains duplicate batch sizes")
    source_batches = [str(item["source_batch"]).strip() for item in batches]
    if any(not value for value in source_batches):
        raise ValueError("Evaluation manifest contains a blank source_batch")
    if len(source_batches) != len(set(source_batches)):
        raise ValueError("Evaluation manifest contains duplicate source_batch values")
    sizes = set(declared_sizes)
    missing = REQUIRED_SIZES - sizes
    if require_all_sizes and missing:
        raise ValueError(f"Evaluation manifest is missing batch sizes: {sorted(missing)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in sorted(batches, key=lambda value: int(value["batch_size"])):
        size = int(item["batch_size"])
        with SessionLocal() as session:
            report = evaluate_batch(
                session,
                Path(item["source_dir"]),
                Path(item["truth"]),
                str(item["source_batch"]),
                output_dir / str(size),
            )
        if int(report["batch_size"]) != size:
            raise ValueError(
                f"Manifest size {size} does not match actual batch size "
                f"{report['batch_size']}"
            )
        rows.append({name: report[name] for name in COLUMNS})

    (output_dir / "comparison.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "comparison.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    table = [
        "| Batch Size | Match Rate | Precision | Recall | F1 | Time | Throughput |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        table.append(
            f"| {row['batch_size']:,} | {row['match_rate']:.2%} | "
            f"{row['precision']:.2%} | {row['recall']:.2%} | "
            f"{row['f1_score']:.2%} | "
            f"{row['processing_time_seconds']:.3f}s | "
            f"{row['records_per_second']:.2f}/s |"
        )
    (output_dir / "comparison.md").write_text(
        "\n".join(table) + "\n",
        encoding="utf-8",
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run and compare the required evaluation batch sizes."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    rows = evaluate_matrix(
        args.manifest,
        args.output_dir,
        require_all_sizes=not args.allow_partial,
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
