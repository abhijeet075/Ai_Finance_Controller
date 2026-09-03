# Phase 13 merge guide — Windows

Use these steps from the repository root after extracting the Phase 13 ZIP beside your existing project.

## 1. Create the branch

```powershell
git switch phase-12
git pull
git switch -c phase-13-dashboard
```

## 2. Copy the cumulative source

Copy the ZIP contents into the existing `ai-finance-controller` folder and allow Windows to replace matching files. Do not copy `.venv`, `node_modules`, `.env`, generated exports, or database files.

## 3. Install and verify the frontend

```powershell
cd frontend
npm install
npm test
npm run lint
npm run build
cd ..
```

## 4. Verify the backend API enrichment

```powershell
$env:PYTHONPATH = ".;backend"
python -m pytest backend/tests/test_run_management.py backend/tests/test_api_contracts.py -v
```

No new database migration is required for Phase 13. The exception endpoint adds response fields through read-only joins to existing invoice and settlement tables.

## 5. Run locally

Backend terminal:

```powershell
$env:PYTHONPATH = ".;backend"
$env:DATABASE_URL = "postgresql+psycopg://finance_user:finance_password@localhost:5432/finance_controller_eval_v2"
uvicorn app.main:app --app-dir backend --reload
```

Frontend terminal:

```powershell
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173` and verify Overview, Results, Exceptions, filtering, pagination, detail drawer, run switching, and CSV downloads.

## 6. Commit

```powershell
git status --short
git add README.md Makefile backend frontend docs
git diff --cached --check
git commit -m "Add Phase 13 reconciliation dashboard"
git push -u origin phase-13-dashboard
```
