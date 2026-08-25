# Phase 4 — Synthetic data generator

The generator creates deterministic source CSVs and keeps evaluation labels in a separate ground-truth directory. The `--records` value is the **exact combined number of rows** across bank transactions, invoices, and settlements.

## Supported scale presets

```bash
python scripts/generate_data.py --records 100
python scripts/generate_data.py --records 500
python scripts/generate_data.py --records 1000
python scripts/generate_data.py --records 5000
python scripts/generate_data.py --records 10000
```

Generate every required size in one command:

```bash
python scripts/generate_data.py --all-presets --seed 42 --clean
```

The generator also accepts any positive custom row count.

## Generated source files

For a 500-row run with seed 42:

```text
data/
├── raw/synthetic_500_seed_42/
│   ├── bank_transactions.csv
│   ├── invoices.csv
│   └── settlements.csv
├── ground_truth/synthetic_500_seed_42/
│   ├── entity_ground_truth.csv
│   └── reconciliation_ground_truth.csv
└── processed/synthetic_500_seed_42/
    └── manifest.json
```

Ground-truth fields never appear in source files, preventing evaluation leakage.

## Scenario coverage

Every preset contains all required scenarios:

- Normal exact matches
- Amount mismatches
- Missing settlements
- Duplicate payments
- Date mismatches
- Customer-name variations
- Currency mismatches
- Partial payments
- Completely unrelated records

A weighted distribution produces a realistic mix while guaranteeing at least one example of every scenario for datasets of 100 rows or more.

## Reproducibility

IDs and generated values are deterministic for the same seed:

```bash
python scripts/generate_data.py --records 1000 --seed 2026
```

Running that command again produces byte-identical source CSVs.

## Ground truth

`entity_ground_truth.csv` contains one row per source record and identifies the scenario, expected outcome, and true match group. Unrelated records intentionally have an empty match group.

`reconciliation_ground_truth.csv` is bank-transaction-centered and contains expected invoice and settlement links, expected status, and the reason. It can be used to calculate precision, recall, false-match rate, automation rate, and exception accuracy.

## Validation

The generator automatically verifies:

- Exact requested source-row count
- Unique source IDs
- One entity ground-truth row per source record
- Valid ground-truth references
- Coverage of every required scenario for preset-sized datasets
- Scenario-specific financial invariants: amount equality or variance, payment cardinality, missing settlements, date gaps, name differences, currency conflicts, partial-payment arithmetic, and unrelated-record isolation

Run the standalone tests without third-party dependencies:

```bash
python -m unittest backend.tests.test_synthetic_generator -v
```

## Important conventions

- Monetary values are written as two-decimal strings, never binary floats.
- Account numbers are masked synthetic values.
- Dates use ISO `YYYY-MM-DD` format.
- Currency mismatch cases use `USD` invoices and `INR` bank records.
- Unrelated records are deliberately labeled `no_match` to measure false positives.
