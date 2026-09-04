# Phases 14–18: end-to-end finance intelligence

## Phase 14 — Cash forecasting

`GET /api/forecasts?horizon_days=7|14|30&source_batch=...&currency=USD` queries persisted bank transactions, invoices, and settlements. Currency is optional and is inferred from the source batch when omitted. The response reports current cash + expected receipts − expected expenses − pending settlements = projected cash, a daily series, and explicit assumptions. No demo values are substituted.

## Phase 15 — AI matching

`POST /api/ai/match` accepts a run and transaction. It is available only when the deterministic result is unresolved. The LLM sees a bounded list of same-batch, same-currency candidates and may recommend one based on names, descriptions, and unusual relationships. Amount and currency gates are reapplied after the response. Suggestions are advisory and never mutate canonical results.

## Phase 16 — AI exception analyst

`POST /api/ai/exceptions/{exception_id}/analyze` returns structured exception type, severity, explanation, action, confidence, and the database evidence used. If no LLM is configured, a deterministic evidence-backed explanation is returned.

## Phase 17 — Finance Q&A

`POST /api/ai/finance-qa` queries actual bank transactions, settlements, exceptions, and the latest reconciliation run before generating an answer. Evidence is returned separately so the UI can show its provenance. Without an LLM, the same database query produces a deterministic summary.

## Phase 18 — hardening and delivery

- Audit records are stored for every AI match, exception analysis, and finance question.
- Set `APP_API_KEY` to require `X-API-Key` or Bearer authentication on AI and audit endpoints. Leave blank only for local development.
- `LLM_MAX_TOKENS` bounds response cost and latency; candidate lists are prefiltered by batch, currency, amount, and date before any LLM call.
- CI runs backend tests/lint and frontend tests/lint/build.
- `scripts/performance_test.py` measures p50/p95 latency.
- `docker-compose.full.yml` is an optional full stack deployment; native PostgreSQL remains supported.
- `evaluation/final_benchmark.py` consolidates offline evaluation reports while preserving truth isolation.

## Native Windows run

```powershell
python -m alembic -c backend/alembic.ini upgrade head
python -m uvicorn app.main:app --app-dir backend --reload
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

## Final verification

```powershell
$env:PYTHONPATH = ".;backend"
python -m pytest -q
python -m ruff check backend scripts evaluation
cd frontend
npm test
npm run lint
npm run build
```

## Final demo

1. Upload bank, invoice, and settlement files under one source batch.
2. Run reconciliation and inspect deterministic metrics.
3. Open an unresolved exception and request the structured analysis.
4. Request an AI match for an ambiguous result; confirm it remains advisory.
5. Compare 7, 14, and 30-day projected cash.
6. Ask “Why did cash decrease this week?” and inspect every evidence card.
7. Review `/api/audit-logs` and the final benchmark output.
