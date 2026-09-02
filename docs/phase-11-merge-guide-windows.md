# Add Phase 11 to an existing Phase 10 repository (Windows)

This procedure preserves Phase 10, applies the cumulative Phase 11 package without replacing Git
history, migrates PostgreSQL, verifies the real workflow, and commits only source files.

## 1. Protect the current Phase 10 state

Open PowerShell in the existing repository:

```powershell
cd "C:\Users\Abhijeet\OneDrive\Desktop\Buildathon\ai-finance-controller"
git status --short
git branch --show-current
```

Commit or stash every intentional Phase 10 change before continuing. Do not proceed with an
unexplained dirty working tree.

If Phase 10 is not committed, review `git status`, stage only its intentional source files through
VS Code Source Control, and commit them. Do not use a blind `git add .` when secrets or generated
data might be present. Then create the safety tag and branch:

```powershell
git tag phase-10-complete
git switch -c phase-11
```

If Phase 10 is already committed, this is all you need. If the tag already exists, omit the tag
command.

## 2. Extract the rechecked package outside the repository

Download `ai-finance-controller-phase11-rechecked.zip`, then run:

```powershell
$zip = "$env:USERPROFILE\Downloads\ai-finance-controller-phase11-rechecked.zip"
$temp = "$env:TEMP\ai-finance-controller-phase11"
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip -DestinationPath $temp
$source = Join-Path $temp "ai-finance-controller"
Test-Path $source
```

`Test-Path` must return `True`.

## 3. Copy Phase 11 over Phase 10 safely

Run this while the PowerShell working directory is the existing repository:

```powershell
$destination = (Get-Location).Path
robocopy $source $destination /E `
  /XD .git .venv node_modules __pycache__ .pytest_cache `
      data\raw data\processed data\ground_truth data\exports `
  /XF .env *.pyc

if ($LASTEXITCODE -ge 8) {
    throw "Robocopy failed with exit code $LASTEXITCODE"
}
```

Do not use `/MIR`; it can delete local files. Never copy `.git`, `.env`, `.venv`, generated data,
hidden truth, evaluation exports, or `node_modules`.

## 4. Review exactly what changed

```powershell
git status --short
git diff --stat
git diff -- backend/app/services/decision_engine.py
git diff -- backend/app/services/reconciliation.py
git diff -- evaluation/evaluate_batch.py
git diff -- evaluation/evaluate_matrix.py
```

Important new files include:

```text
backend/migrations/versions/20260831_0004_phase11_exception_evidence.py
evaluation/evaluate_batch.py
evaluation/evaluate_matrix.py
evaluation/batches.example.json
backend/tests/test_phase11_evaluation.py
docs/phase-11-end-to-end-evaluation.md
```

## 5. Activate Python and verify configuration

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = ".;backend"
python --version
python -c "from app.main import app; print(sorted(app.openapi()['paths']))"
```

Confirm `.env` still contains the working PostgreSQL `DATABASE_URL`. Do not commit `.env`.

## 6. Back up and migrate PostgreSQL

Create a pgAdmin backup before schema changes. Then run:

```powershell
alembic -c backend/alembic.ini current
alembic -c backend/alembic.ini upgrade head
alembic -c backend/alembic.ini current
```

Expected migration head:

```text
20260831_0004 (head)
```

The chain is:

```text
20260820_0001 -> 20260820_0002 -> 20260831_0003 -> 20260831_0004
```

## 7. Run verification before evaluating data

```powershell
python -m compileall backend evaluation scripts
python -m pytest -v
ruff check backend scripts evaluation
```

Do not continue until failures are understood. A line-ending warning about LF/CRLF is not a test
failure.

## 8. Generate isolated evaluation datasets

Keep hidden truth outside the repository:

```powershell
python scripts/generate_data.py `
  --all-presets `
  --seed 42 `
  --output-root data `
  --truth-root ..\evaluation-ground-truth `
  --clean
```

This creates 50, 100, 500, 1,000, 5,000, and 10,000 source-row datasets. Hidden truth stays under
`..\evaluation-ground-truth`, not under `backend` or application uploads.

## 9. Run a 50-row smoke evaluation

```powershell
python -m evaluation.evaluate_batch `
  --source-dir data\raw\synthetic_50_seed_92 `
  --truth ..\evaluation-ground-truth\synthetic_50_seed_92\hidden_truth.jsonl `
  --source-batch eval-50-seed-92 `
  --output-dir data\exports\evaluation\50
```

Check these files:

```powershell
Get-Content data\exports\evaluation\50\evaluation-report.txt
Import-Csv data\exports\evaluation\50\exceptions.csv | Select-Object -First 10
```

The command now fails if predictions do not cover every bank transaction or if any review/exception
is missing from the exception report.

## 10. Run the complete required matrix

```powershell
Copy-Item evaluation\batches.example.json evaluation\batches.json
code evaluation\batches.json
```

If you are not running from the repository root, use absolute paths. In JSON, use forward slashes or
escape each backslash. Then run:

```powershell
python -m evaluation.evaluate_matrix `
  --manifest evaluation\batches.json `
  --output-dir data\exports\evaluation-matrix

Get-Content data\exports\evaluation-matrix\comparison.md
```

The default command requires 50, 100, 500, 1,000, and 5,000. Use `--allow-partial` only for a
development smoke test, never for the final challenge report.

## 11. Verify the API exception exports

Start FastAPI in one PowerShell window:

```powershell
uvicorn app.main:app --app-dir backend --reload
```

For a completed run ID, verify:

```text
GET http://127.0.0.1:8000/api/reconciliation/runs/{run_id}
GET http://127.0.0.1:8000/api/reconciliation/runs/{run_id}/predictions
GET http://127.0.0.1:8000/api/reconciliation/runs/{run_id}/exceptions
GET http://127.0.0.1:8000/api/reconciliation/runs/{run_id}/exceptions.csv
```

## 12. Commit Phase 11 without generated data

```powershell
git status --short
git add .gitignore README.md Makefile backend evaluation scripts docs
git diff --cached --stat
git diff --cached --check
git commit -m "Add Phase 11 end-to-end evaluation"
git push -u origin phase-11
```

Before committing, confirm that `.env`, `data/raw`, hidden truth, evaluation exports, `.venv`, and
`node_modules` are not staged.

## Recovery

If a source copy is wrong, discard the Phase 11 branch and recreate it from the Phase 10 tag. Do not
downgrade a production database casually. For an empty development database only, the schema can be
returned to Phase 10 with:

```powershell
alembic -c backend/alembic.ini downgrade 20260831_0003
```
