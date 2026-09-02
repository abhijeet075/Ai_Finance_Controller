# Phase 12 manual test sequence

1. Apply migration `20260902_0005` and start FastAPI.
2. `GET /api/reconciliation/source-batches` and choose a batch with bank rows.
3. `POST /api/reconciliation/runs` with `{"source_batch":"<batch>"}`.
4. Save the returned `run_id`; status must be `completed`.
5. `GET /api/reconciliation/runs/{run_id}`.
6. `GET /api/reconciliation/runs/{run_id}/results?page=1&page_size=50`.
7. Verify `matched + review + exceptions == records_processed`.
8. Verify the results endpoint total equals `records_processed`.
9. `GET /api/reconciliation/runs/{run_id}/exceptions?page=1&page_size=50`.
10. Test `severity`, `exception_type`, and `status` filters.
11. `GET /api/reconciliation/runs/{run_id}/metrics`; quality fields must be null.
12. Download `predictions.csv` and `exceptions.csv`.
13. Run the same batch again and verify a different run ID.
14. `GET /api/reconciliation/runs?page=1&page_size=50` and find both runs.
15. Query PostgreSQL and verify every result and exception has the correct non-null run ID.

Suggested PostgreSQL checks:

```sql
SELECT id, source_batch, status, records_processed, matched_count,
       review_count, exception_count, processing_time_ms,
       matching_time_ms, decision_time_ms, persistence_time_ms
FROM reconciliation_runs
ORDER BY created_at DESC;

SELECT run_id, COUNT(*)
FROM reconciliation_results
GROUP BY run_id;

SELECT run_id, COUNT(*)
FROM exceptions
GROUP BY run_id;

SELECT run_id, invoice_id, COUNT(*)
FROM reconciliation_results
WHERE invoice_id IS NOT NULL
GROUP BY run_id, invoice_id
HAVING COUNT(*) > 1;
```

The final query must return no rows.
