# Phase 5 — Hidden ground truth

Ground truth is generated alongside synthetic source data but stored behind a separate evaluation boundary. The FastAPI application receives only bank, invoice, and settlement inputs. It never imports or reads the hidden truth file.

## Hidden truth record

Each bank transaction receives one JSON Lines record:

```json
{
  "transaction_id": "TX1024",
  "invoice_id": "INV982",
  "settlement_id": "SET441",
  "true_match": true,
  "expected_status": "matched",
  "scenario": "normal",
  "reason": "Exact amount, currency, reference, and nearby date."
}
```

`true_match` means that the supplied IDs belong to the same underlying synthetic business event. A true relationship may still have an expected status of `review` or `exception` when there is a partial payment, duplicate, currency conflict, or another control issue.

## Isolation model

Generate public inputs and hidden truth into different roots:

```bash
python scripts/generate_data.py \
  --records 1000 \
  --seed 42 \
  --output-root data \
  --truth-root /secure/evaluation-ground-truth \
  --clean
```

Public application files:

```text
data/raw/<dataset>/
├── bank_transactions.csv
├── invoices.csv
└── settlements.csv
```

Evaluation-only files:

```text
/secure/evaluation-ground-truth/<dataset>/
├── hidden_truth.jsonl
├── entity_ground_truth.csv
├── reconciliation_ground_truth.csv
└── evaluation_manifest.json
```

The public `data/processed/<dataset>/manifest.json` is redacted: it contains source counts and runtime metadata but no seed, scenario distribution, truth path, or expected labels. `data/ground_truth` is excluded from application container build contexts through `.dockerignore`.

## Evaluation input

The application exports a prediction CSV without seeing the truth:

```csv
transaction_id,invoice_id,settlement_id,predicted_status
TX1024,INV982,SET441,matched
```

Run the offline evaluator:

```bash
python -m evaluation.evaluate_reconciliation \
  --truth /secure/evaluation-ground-truth/<dataset>/hidden_truth.jsonl \
  --predictions data/exports/predictions.csv \
  --output data/exports/evaluation-report.json
```

The report contains precision, recall, F1, exact-link accuracy, status accuracy, false positives, false negatives, missing predictions, unknown predictions, and a detailed exception list. A ready-to-copy prediction file is available at `docs/examples/predictions.example.csv`, and the hidden record contract is defined in `docs/hidden-truth.schema.json`.

## Anti-leakage checks

Automated tests verify that:

- Source CSV headers contain no scenario or truth fields.
- Hidden truth can be placed outside the public output root.
- Public manifests do not reveal truth paths, seeds, or scenario distributions.
- `backend/app` contains no hidden-truth or ground-truth references.
- A perfect prediction file scores 100% on all evaluation metrics.
