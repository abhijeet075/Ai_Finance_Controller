# Phase 10 — Decision and reconciliation orchestration

Phase 10 converts the Phase 9 candidate matcher into a database-backed application workflow. It
does not introduce a duplicate scoring module.

## Runtime flow

```text
Uploaded batch -> normalization -> CandidateMatcher -> global assignment
-> canonical decision -> results and exceptions -> PostgreSQL -> CSV export -> offline evaluator
```

`POST /api/reconciliation/runs` loads one `source_batch`, converts SQLAlchemy rows into domain
records, runs indexed matching, applies deterministic greedy one-to-one assignment, persists one
canonical result per bank transaction, creates classified exceptions, and returns operational
metrics.

Upload all three source files with the same query parameter, for example:

```text
POST /upload/bank?source_batch=demo-100
POST /upload/invoices?source_batch=demo-100
POST /upload/settlements?source_batch=demo-100
```

Then run:

```json
{"source_batch": "demo-100"}
```

against `POST /api/reconciliation/runs`.

The response can be saved as `run-summary.json`; download the run's predictions and build the
combined scoreboard with:

```bash
python -m evaluation.evaluate_run \
  --truth /secure/evaluation-ground-truth/demo-100/hidden_truth.jsonl \
  --predictions data/exports/predictions.csv \
  --run-summary data/exports/run-summary.json \
  --output data/exports/run-scoreboard.json
```

## Decisions

- `matched`: both an unused invoice and unused settlement were assigned.
- `review`: evidence is incomplete, ambiguous, or lost a global assignment conflict.
- `exception`: deterministic controls identified a duplicate, currency mismatch, amount mismatch,
  or no match.

The first global allocator is deliberately greedy and deterministic: candidate edges are sorted by
score, then bank ID and record ID; the highest-confidence unused record wins. Competing rows go to
review. Database uniqueness constraints provide a second one-to-one safety boundary per run.

## Exception types

`currency_mismatch`, `duplicate_payment`, `missing_settlement`, `amount_mismatch`,
`ambiguous_match`, and `no_match` are classified without an LLM. Each exception includes severity,
description, recommended action, confidence, and workflow status.

## Metrics

The run stores `records_processed`, decision counts, match rate, end-to-end processing time,
records per second, Cartesian comparisons, examined candidate records, and pruning reduction.
Timing includes matching, decision creation, and database persistence. Candidate pruning and full
application throughput remain separate metrics.

Precision, recall, F1, exact-link accuracy, and status accuracy remain truth-isolated. Download
`GET /api/reconciliation/runs/{run_id}/predictions`, then pass the CSV to
`evaluation/evaluate_reconciliation.py` with the hidden truth file.

The evaluator maps the legacy truth label `no_match` to the canonical application status
`exception`. The application continues to persist only `matched`, `review`, or `exception`.

## Migration

Apply `20260831_0003_reconciliation_orchestration.py`. It adds batch labels, a run table, run foreign
keys, metrics, indexes, and per-run one-to-one constraints.
