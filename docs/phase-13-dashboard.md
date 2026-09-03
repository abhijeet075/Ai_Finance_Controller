# Phase 13 — Dashboard

## Scope

Phase 13 turns the Phase 12 run-management API into a frontend-ready finance operations workflow. The React application displays only API responses; it contains no demo metrics, synthetic result rows, reconciliation rules, or hidden truth.

## Screens

### Overview

- Discovers source batches from `GET /api/reconciliation/source-batches`.
- Starts a run through `POST /api/reconciliation/runs`.
- Loads run history and allows switching the active run.
- Displays total records, matched, review, exceptions, match rate, precision, recall, F1, processing time, and throughput.
- Displays a proportional matched/review/exception visualization.
- Keeps precision, recall, and F1 as **Not evaluated** when the production API returns `null`.
- Downloads prediction and exception CSV exports.

### Reconciliation results

- Loads `GET /api/reconciliation/runs/{run_id}/results`.
- Supports All, Matched, Review, and Exception filters.
- Uses server-side pagination.
- Displays transaction, invoice, settlement, status, confidence, and reason.

### Exception workbench

- Loads `GET /api/reconciliation/runs/{run_id}/exceptions`.
- Uses server-side severity, type, and workflow-status filters.
- Uses server-side pagination.
- Opens a keyboard-accessible detail drawer containing bank, invoice, settlement, and difference amounts; exception type; severity; confidence; evidence; reason; and recommended action.

## API enrichment

The existing Phase 12 exception endpoint now includes read-only `invoice_id`, `settlement_id`, `invoice_amount`, and `settlement_amount` fields. These are loaded by outer joins to existing records and do not alter matching, assignment, persistence, or exception classification.

## Local run

Start PostgreSQL and the backend first:

```powershell
$env:PYTHONPATH = ".;backend"
$env:DATABASE_URL = "postgresql+psycopg://finance_user:finance_password@localhost:5432/finance_controller_eval_v2"
uvicorn app.main:app --app-dir backend --reload
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to the backend on port 8000.

For a separately deployed frontend, set `VITE_API_BASE_URL` to the backend origin.

## Verification

```powershell
cd frontend
npm run lint
npm test
npm run build
```

From the repository root:

```powershell
$env:PYTHONPATH = ".;backend"
python -m pytest backend/tests/test_run_management.py backend/tests/test_api_contracts.py -v
```

## Data integrity

- The dashboard never computes reconciliation decisions.
- Filters and pagination are executed by Phase 12 endpoints.
- Production quality metrics remain nullable.
- Hidden ground truth is never requested by or bundled into the frontend.
