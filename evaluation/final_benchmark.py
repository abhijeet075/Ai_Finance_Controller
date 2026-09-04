"""Summarize final evaluation artifacts without exposing hidden truth."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reports",
        type=Path,
        default=Path("data/exports/evaluation"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/exports/final-benchmark.json"),
    )
    args = parser.parse_args()
    reports = []
    for path in sorted(args.reports.rglob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        metrics = data.get("metrics", data)
        reports.append(
            {
                "report": str(path),
                "precision": metrics.get("precision"),
                "recall": metrics.get("recall"),
                "f1": metrics.get("f1"),
                "match_rate": metrics.get("match_rate"),
                "processing_time_ms": metrics.get("processing_time_ms"),
            }
        )
    output = {
        "report_count": len(reports),
        "reports": reports,
        "truth_isolation": (
            "Hidden truth was consumed only by offline evaluation."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
