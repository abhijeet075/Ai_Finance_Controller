# Phase 11 — End-to-end evaluation

Phase 11 measures the real persisted Phase 10 workflow before any AI is introduced.
The application never receives hidden truth. The evaluator loads truth only after ingestion,
reconciliation, persistence, and prediction export have completed.

## Architecture

```text
Synthetic generator -> source CSVs -> ingestion -> PostgreSQL
-> CandidateMatcher -> global decision -> persisted run
-> predictions.csv -> offline evaluator <- hidden_truth.jsonl
-> accuracy, throughput, and honest exception reports
```

## Apply the migration

```bash
alembic -c backend/alembic.ini upgrade head
```

The Phase 11 migration is `20260831_0004_phase11_exception_evidence.py`. It stores only application
candidate evidence: candidate ID/type, candidate amount, and amount difference. It never stores or
reads hidden truth.

## Generate the required sizes

Keep truth outside the application data directory:

```bash
python scripts/generate_data.py \
  --all-presets \
  --seed 42 \
  --output-root data \
  --truth-root ../evaluation-ground-truth \
  --clean
```

The preset matrix contains 50, 100, 500, 1,000, 5,000, and 10,000 source rows. Phase 11 requires
at least 50, 100, 500, 1,000, and 5,000.

## Evaluate one real batch

```bash
PYTHONPATH=.:backend python -m evaluation.evaluate_batch \
  --source-dir data/raw/synthetic_500_seed_542 \
  --truth ../evaluation-ground-truth/synthetic_500_seed_542/hidden_truth.jsonl \
  --source-batch eval-500-seed-542 \
  --output-dir data/exports/evaluation/500
```

This command uses the configured PostgreSQL database. It validates and stores all three source
files, executes `run_reconciliation()`, persists results and exceptions, exports predictions, and
only then invokes the truth-isolated evaluator.

Artifacts:

- `run-summary.json` — operational metrics from the persisted run.
- `predictions.csv` — evaluator contract with transaction, invoice, settlement, and status.
- `exceptions.csv` — every review/exception with the best candidate and financial evidence.
- `evaluation-report.json` — complete machine-readable scoreboard and discrepancies.
- `evaluation-report.txt` — presentation-ready terminal report.

Use a fresh database or unique generator seed and `source_batch` for each matrix entry. Source IDs
are globally unique, so reusing the same generated IDs under another batch is intentionally rejected.

## Evaluate the required matrix

Copy `evaluation/batches.example.json`, update its paths, then run:

```bash
PYTHONPATH=.:backend python -m evaluation.evaluate_matrix \
  --manifest evaluation/batches.json \
  --output-dir data/exports/evaluation-matrix
```

The matrix command refuses to claim complete coverage unless 50, 100, 500, 1,000, and 5,000 are
present. `--allow-partial` is available only for development checks.

Comparison outputs:

- `comparison.csv`
- `comparison.json`
- `comparison.md`
- A complete artifact folder for every batch size

## Honest exception report

Every unresolved transaction contains:

- transaction ID and canonical status;
- deterministic exception type;
- best invoice or settlement candidate, even when it was not selected;
- confidence as a zero-to-one value;
- bank amount, candidate amount, and absolute difference;
- currency and deterministic reason.

The same report is available from a persisted run:

```text
GET /api/reconciliation/runs/{run_id}/exceptions
GET /api/reconciliation/runs/{run_id}/exceptions.csv
```

## Metric definitions

- `batch_size`: all bank, invoice, and settlement source rows supplied to the controller.
- `total_records`: bank transactions receiving one canonical decision.
- `match_rate`: matched decisions divided by total records.
- `precision`: exact correct links divided by exact correct links plus false matches.
- `recall`: exact correct links divided by exact correct links plus missed matches.
- `f1_score`: harmonic mean of precision and recall.
- `false_matches`: evaluator false positives.
- `missed_matches`: evaluator false negatives.
- `exception_rate`: canonical exception decisions divided by total records.
- `prediction_coverage`: exported predictions divided by total records.
- `exception_report_complete`: whether every review/exception has a report row.
- `processing_time`: Phase 10 matching, decision, and persistence time.
- `records_per_second`: canonical decisions divided by processing time.
- `comparison_reduction`: candidate pruning only; it is not application throughput.

Reviews and exceptions are deliberately not hidden. Evaluation discrepancies show wrong links,
wrong statuses, missing predictions, and unknown predictions.

## Dependency-free baseline validation

`docs/phase11-core-validation.md`, `.csv`, and `.json` contain actual deterministic-core results
for the five required sizes. These validate scaling and metric calculations without PostgreSQL.
They are not substitutes for the final persisted matrix: run `evaluation.evaluate_matrix` locally
to measure database-inclusive processing time and produce the challenge report.
