# Phase 6 — Data ingestion

The ingestion API implements an atomic pipeline:

```text
Upload → Validate → Clean → Normalize → Store in PostgreSQL
```

## Endpoints

- `POST /upload/bank`
- `POST /upload/invoices`
- `POST /upload/settlements`

These paths are exposed exactly as specified; other application APIs remain under `/api`.

## Accepted formats

- Multipart file upload using field name `file`
- Raw `text/csv` request body
- Raw `application/json` request body
- JSON object, array of objects, or `{ "records": [...] }`

Excel is intentionally deferred.

### CSV upload

```bash
curl -X POST http://localhost:8000/upload/bank \
  -F "file=@data/raw/example/bank_transactions.csv"
```

### JSON upload

```bash
curl -X POST http://localhost:8000/upload/invoices \
  -H "Content-Type: application/json" \
  --data-binary @invoices.json
```

## Validation and normalization

- Header names are trimmed, lowercased, and stripped of UTF-8 BOM markers.
- CSV must use UTF-8, have unique headers, and have consistent row width.
- Unknown columns are rejected to avoid silently dropping financial data.
- Dates must use unambiguous ISO `YYYY-MM-DD` format.
- Amounts accept commas and leading `₹`, `$`, `€`, or `£`, then become `Decimal(18,2)` values.
- Zero, negative, non-finite, and oversized amounts are rejected.
- Currencies are uppercased and checked against: AED, AUD, CAD, EUR, GBP, INR, JPY, SGD, USD.
- Account numbers are reduced to masked values such as `XXXX5678` before persistence.
- Whitespace is collapsed in references, customer names, and descriptions.
- Invoice due dates cannot precede invoice dates.
- Status and transaction-type values are normalized to lowercase and validated.

## Duplicate behavior

- Exact duplicates inside one upload are skipped and counted.
- Conflicting duplicate IDs, invoice numbers, or settlement references reject the entire upload.
- Exact rows already present in PostgreSQL are skipped and counted, making retries idempotent.
- A stored key with different values returns `409 Conflict`; it is never silently treated as a duplicate.
- Bank records with different IDs are retained even if amount/reference fields agree; this preserves duplicate-payment scenarios for reconciliation.

## Atomicity and errors

Validation is all-or-nothing. If any row is invalid, no row from that upload is stored. The `422` response includes row, field, machine-readable code, and explanation.

Other responses:

- `413` — file exceeds `MAX_UPLOAD_BYTES`
- `415` — format is neither CSV nor JSON
- `422` — missing columns, invalid values, duplicates, or malformed data
- `500` — PostgreSQL rejected the otherwise valid batch; the transaction is rolled back

Default limits:

```env
MAX_UPLOAD_BYTES=10485760
MAX_UPLOAD_RECORDS=10000
```

## Successful response

```json
{
  "source": "bank",
  "format": "csv",
  "received_records": 100,
  "normalized_records": 99,
  "inserted_records": 97,
  "duplicate_records": 3,
  "status": "stored"
}
```

## Database migration

Settlement currency is required for safe reconciliation and was added in the Phase 6 migration:

```bash
alembic -c backend/alembic.ini upgrade head
```
