# Phase 8 — Deterministic baseline reconciliation

The baseline engine is implemented in `backend/app/services/baseline_reconciliation.py`.
It is a pure Python rules engine and makes no AI, LLM, embedding, or network calls.

## Rule precedence

1. `exact_reference` — normalized bank reference equals invoice number; strong, confidence 100.
2. `exact_amount_customer` — same currency and amount plus normalized customer similarity; strong, confidence 95.
3. `amount_date` — same currency and amount with an inclusive date gap of at most three days; review, confidence 75.
4. `amount_tolerance` — same currency and inclusive configurable amount tolerance; review, confidence 60.
5. `duplicate` — repeated currency + amount + normalized customer + date; exception and auto-match blocked.

Invoice number is the canonical invoice reference in the existing schema. Bank customer is taken
from an explicit customer value when available; otherwise deterministic stop-word removal is applied
to the normalized transaction description.

## Safety and determinism

- Different currencies never match.
- Debits are excluded from receivables matching.
- Equal top candidates are returned as `ambiguous` for review rather than selected arbitrarily.
- Invoice assignment is one-to-one. Competing bank transactions are surfaced for review.
- Missing customer text is not sufficient to create a duplicate group.
- Output ordering is stable by bank transaction ID.
- Every decision includes the rule, confidence, amount difference, date difference, and customer score.

## Defaults

- Amount tolerance: `1.00`
- Date window: `3` calendar days, inclusive
- Customer similarity threshold: `0.70`

Run the tests with:

```bash
PYTHONPATH=backend python -m unittest backend.tests.test_baseline_reconciliation -v
```
