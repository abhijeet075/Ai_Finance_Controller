# AI Finance Controller

An evidence-first finance operations MVP for multi-source reconciliation and explainable cash forecasting.

## MVP workflows

1. Reconcile bank transactions, invoices, and payment settlements.
2. Produce 7, 14, and 30-day cash forecasts from verified records.

## Quick start

```bash
cp .env.example .env
docker compose up -d
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic -c backend/alembic.ini upgrade head
uvicorn app.main:app --app-dir backend --reload
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the dashboard at `http://localhost:5173` and API docs at `http://localhost:8000/docs`.

## Structure

- `backend/app/api` — HTTP routes
- `backend/app/models` — SQLAlchemy models
- `backend/app/schemas` — Pydantic contracts
- `backend/app/services` — finance business logic
- `backend/app/repositories` — persistence layer
- `data/raw` — synthetic input files
- `data/processed` — generated outputs, excluded from Git
- `data/ground_truth` — evaluation-only labels
- `scripts` — deterministic dataset generation

## Safety rule

LLM recommendations never bypass deterministic checks for amounts, currency, references, dates, or ledger arithmetic. Ambiguous cases belong in review or exception queues.

## Validation commands

```bash
pytest
ruff check backend scripts
cd frontend && npm run lint && npm run build
```

Convenience commands are also available through `make api`, `make frontend`, `make test`, `make lint`, and `make migrate`.

## Database schema

Phase 3 defines six PostgreSQL entities: bank transactions, invoices, settlements, reconciliation results, exceptions, and cash forecasts. See `docs/database-design.md` for relationships, constraints, indexes, and migration commands.

## Synthetic reconciliation data

Generate an exact combined source-row count across bank transactions, invoices, and settlements:

```bash
python scripts/generate_data.py --records 500 --seed 42 --clean
```

Generate every required scale—50, 100, 500, 1,000, 5,000, and 10,000 rows:

```bash
python scripts/generate_data.py --all-presets --seed 42 --clean
# or: make generate-data
```

The generator includes normal matches, amount mismatches, missing settlements, duplicate payments, date mismatches, name variations, currency mismatches, partial payments, and unrelated records for false-match evaluation. Source CSVs are written under `data/raw`; hidden labels are written separately under `data/ground_truth`. See `docs/synthetic-data-generator.md`.

## Hidden ground truth and offline evaluation

Keep truth outside the application data mount:

```bash
python scripts/generate_data.py \
  --records 1000 \
  --seed 42 \
  --output-root data \
  --truth-root /secure/evaluation-ground-truth \
  --clean
```

The application consumes only the source CSVs. The hidden directory contains `hidden_truth.jsonl`, detailed CSV labels, and a private evaluation manifest. The public manifest is redacted.

Evaluate exported application predictions offline:

```bash
python -m evaluation.evaluate_reconciliation \
  --truth /secure/evaluation-ground-truth/<dataset>/hidden_truth.jsonl \
  --predictions data/exports/predictions.csv \
  --output data/exports/evaluation-report.json
```

See `docs/ground-truth.md` for the prediction contract, metrics, and anti-leakage checks.

## CSV and JSON ingestion

Phase 6 exposes the requested upload routes:

- `POST /upload/bank`
- `POST /upload/invoices`
- `POST /upload/settlements`

Each route accepts multipart CSV/JSON files or raw CSV/JSON bodies, then validates, cleans, normalizes, deduplicates, and atomically stores the batch in PostgreSQL. Apply the latest migration before uploading:

```bash
alembic -c backend/alembic.ini upgrade head
```

See `docs/data-ingestion.md` for field requirements, limits, examples, duplicate behavior, and error responses.

## Reusable data normalization

Phase 7 adds deterministic normalization for names, amounts, dates, currencies,
and transaction descriptions. The ingestion pipeline applies the shared
functions before PostgreSQL storage. See `docs/data-normalization.md` and run:

```bash
make test-normalization
```

## Phase 10 reconciliation orchestration

Upload bank, invoice, and settlement files with the same `source_batch` query value, then call
`POST /api/reconciliation/runs`. The service loads that batch, runs Phase 9 candidate matching,
applies deterministic global one-to-one assignment, persists canonical results and classified
exceptions, and returns operational metrics. Download evaluator-ready CSV from
`GET /api/reconciliation/runs/{run_id}/predictions`.

Apply migration `20260831_0003` before using the workflow. See
`docs/phase-10-reconciliation-orchestration.md` and run `make test-reconciliation`.

## Phase 11 end-to-end evaluation

Phase 11 runs the real persisted Phase 10 controller before loading hidden truth. It produces a
run summary, evaluator-ready predictions, an honest unresolved-transaction report, JSON and text
scoreboards, and a comparison matrix for 50, 100, 500, 1,000, and 5,000 source rows.

Apply migration `20260831_0004`, generate datasets with truth outside the application data path,
then run:

```bash
PYTHONPATH=.:backend python -m evaluation.evaluate_batch \
  --source-dir data/raw/synthetic_500_seed_542 \
  --truth ../evaluation-ground-truth/synthetic_500_seed_542/hidden_truth.jsonl \
  --source-batch eval-500-seed-542 \
  --output-dir data/exports/evaluation/500
```

For the full matrix, copy `evaluation/batches.example.json`, update its paths, and run
`python -m evaluation.evaluate_matrix`. See `docs/phase-11-end-to-end-evaluation.md`.

## Phase 12 reconciliation API

Phase 12 exposes the deterministic reconciliation core as a run-oriented API. It adds traceable
`pending`, `running`, `completed`, and `failed` lifecycle states, paginated run history and results,
filtered exceptions, operational metrics, source-batch discovery, and CSV exports. Production
metrics deliberately return null precision/recall/F1 values because hidden truth remains isolated
in the Phase 11 evaluator.

Apply migration `20260902_0005`, then use:

```text
GET  /api/reconciliation/source-batches
POST /api/reconciliation/runs
GET  /api/reconciliation/runs
GET  /api/reconciliation/runs/{run_id}
GET  /api/reconciliation/runs/{run_id}/results
GET  /api/reconciliation/runs/{run_id}/exceptions
GET  /api/reconciliation/runs/{run_id}/metrics
GET  /api/reconciliation/runs/{run_id}/predictions.csv
GET  /api/reconciliation/runs/{run_id}/exceptions.csv
```

See `docs/phase-12-api-run-management.md` and run `make test-run-management`.
