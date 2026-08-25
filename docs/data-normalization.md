# Phase 7 — Data normalization

The normalization layer creates deterministic comparison values before records
are stored and reconciled.

## Reusable functions

`backend/app/services/normalization.py` exposes:

- `normalize_name(value)` — Unicode, case, punctuation, whitespace,
  abbreviations, and trailing legal suffixes.
- `normalize_amount(value, allow_negative=True)` — US, European, and Indian
  separators, currency markers, finite Decimal conversion, and rounding.
- `normalize_date(value, day_first=None)` — common unambiguous numeric,
  ISO, compact, date-time, and textual formats.
- `normalize_description(value)` — punctuation, spacing, case, and finance
  abbreviation expansion.
- `normalize_currency(value)` — currency symbols and names to ISO codes.

The normalization rules are versioned as `NORMALIZATION_VERSION`. Plain `$`
is deliberately rejected because it could mean USD, CAD, AUD, or SGD. Use a
qualified symbol such as `US$`/`A$`, a currency code, or pass an explicit
`default` to `normalize_currency()`.

All three company examples normalize to `ABC TECH`:

```text
ABC Technologies Pvt. Ltd.
ABC Tech
ABC TECHNOLOGIES
```

Ambiguous numeric dates such as `08/10/2026` are rejected unless the caller
explicitly supplies `day_first=True` or `day_first=False`. Guessing financial
dates silently is unsafe.

Phase 6 ingestion uses these reusable functions for customer and processor
names, amounts, dates, currencies, and bank transaction descriptions. Upload
validation remains atomic: an unsafe value rejects the entire batch.

Indian integer grouping such as `1,23,456` is supported. Conflicting negative
notation such as `(-10)` is rejected instead of being silently converted.
