# Phase 12 — API and run management

Phase 12 exposes the deterministic Phase 9–11 core without changing its matching algorithm and
without adding AI. FastAPI routes delegate to the reconciliation service; database access lives in
`backend/app/repositories/reconciliation.py`.

## Run lifecycle

Every execution receives a UUID and transitions through:

```text
pending -> running -> completed
                   -> failed
```

A pending run is committed before execution begins. Results, exceptions, and completed metrics are
then committed atomically. If matching or persistence fails, partial outputs are rolled back and the
existing run is marked `failed` with a controlled error message. Repeated completed runs for the same
source batch are allowed and receive different IDs.

Migration `20260902_0005_phase12_run_management.py` adds lifecycle timestamps, controlled failure
text, stage timings, a run-status constraint, and non-null run links for results and exceptions.
Legacy rows are assigned to a traceable legacy run during upgrade.

The cumulative package also includes the Phase 11 generator correction that prefixes invoice and
settlement natural keys with the dataset seed, allowing all matrix sizes to coexist in one database.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/reconciliation/source-batches` | List available batches and source counts |
| POST | `/api/reconciliation/runs` | Execute a source batch synchronously |
| GET | `/api/reconciliation/runs` | Paginated run history |
| GET | `/api/reconciliation/runs/{run_id}` | Run status and summary |
| GET | `/api/reconciliation/runs/{run_id}/results` | Paginated decisions |
| GET | `/api/reconciliation/runs/{run_id}/exceptions` | Filtered, paginated exceptions |
| GET | `/api/reconciliation/runs/{run_id}/metrics` | Operational metrics |
| GET | `/api/reconciliation/runs/{run_id}/predictions.csv` | Prediction export |
| GET | `/api/reconciliation/runs/{run_id}/exceptions.csv` | Exception export |

The old `/predictions` URL remains as a hidden compatibility alias.

## Pagination and filters

Run history, results, and exceptions use `page` and `page_size`; page size is capped at 100.

```text
GET /api/reconciliation/runs?page=1&page_size=50&status=completed
GET /api/reconciliation/runs?source_batch=eval-500-seed-542
GET /api/reconciliation/runs/{id}/results?status=review
GET /api/reconciliation/runs/{id}/exceptions?severity=critical
GET /api/reconciliation/runs/{id}/exceptions?exception_type=amount_mismatch
GET /api/reconciliation/runs/{id}/exceptions?status=open
```

## Metrics and truth isolation

Production metrics include counts, match rate, throughput, pruning, and matching/decision/persistence
stage times. Precision, recall, F1, false matches, and missed matches are returned as `null` because a
normal API run has no hidden truth. Phase 11 remains the only truth-aware evaluator, outside
`backend/app`.

## Apply and verify

```powershell
$env:PYTHONPATH = ".;backend"
alembic -c backend/alembic.ini upgrade head
python -m pytest backend/tests/test_run_management.py -v
uvicorn app.main:app --app-dir backend --reload
```

Open `http://127.0.0.1:8000/docs`, list source batches, create a run, copy its ID, and exercise every
read/export endpoint. Create the same batch again and verify that the second run ID differs.

## Error behavior

- Empty source batch: controlled `400`.
- Missing run: controlled `404`.
- Invalid pagination or enum filter: `422`.
- Execution failure: controlled `500` containing the traceable run ID but no SQLAlchemy details.
