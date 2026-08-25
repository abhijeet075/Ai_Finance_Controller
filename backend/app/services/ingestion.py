"""Parse, validate, clean, and normalize CSV/JSON finance uploads."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from app.services.normalization import (
    NormalizationError,
    SUPPORTED_CURRENCIES,
    normalize_amount,
    normalize_currency,
    normalize_date,
    normalize_description,
    normalize_name,
)

SourceType = Literal["bank", "invoices", "settlements"]

REQUIRED_COLUMNS: dict[SourceType, tuple[str, ...]] = {
    "bank": (
        "id", "transaction_date", "amount", "currency", "description",
        "reference", "account_number", "transaction_type",
    ),
    "invoices": (
        "id", "invoice_number", "customer", "invoice_date", "due_date",
        "amount", "currency", "status",
    ),
    "settlements": (
        "id", "settlement_reference", "transaction_date", "amount",
        "currency", "processor", "customer", "status",
    ),
}
OPTIONAL_COLUMNS: dict[SourceType, set[str]] = {
    "bank": {"description", "reference"},
    "invoices": set(),
    "settlements": set(),
}
STATUS_VALUES = {
    "invoices": {"open", "partial", "paid", "overdue", "cancelled"},
    "settlements": {"pending", "completed", "failed", "reversed"},
}
MAX_ID_LENGTH = 36
MAX_RECORDS = 10_000


@dataclass(frozen=True)
class IngestionIssue:
    row: int | None
    field: str | None
    code: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "row": self.row,
            "field": self.field,
            "code": self.code,
            "message": self.message,
        }


class IngestionValidationError(ValueError):
    def __init__(self, message: str, issues: list[IngestionIssue]) -> None:
        super().__init__(message)
        self.issues = issues


@dataclass(frozen=True)
class NormalizedBatch:
    source: SourceType
    format: str
    received_records: int
    records: list[dict[str, object]]
    duplicate_records: int


def _normalize_key(value: object) -> str:
    return str(value).replace("\ufeff", "").strip().lower()


def parse_csv_bytes(payload: bytes) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionValidationError(
            "CSV must use UTF-8 encoding.",
            [IngestionIssue(None, None, "invalid_encoding", str(exc))],
        ) from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        if reader.fieldnames is None:
            raise IngestionValidationError(
                "CSV header is missing.",
                [IngestionIssue(1, None, "missing_header", "CSV requires a header row.")],
            )
        normalized_headers = [_normalize_key(name) for name in reader.fieldnames]
        if any(not name for name in normalized_headers):
            raise IngestionValidationError(
                "CSV contains a blank header.",
                [IngestionIssue(1, None, "blank_header", "Every column needs a name.")],
            )
        if len(normalized_headers) != len(set(normalized_headers)):
            raise IngestionValidationError(
                "CSV contains duplicate headers.",
                [IngestionIssue(1, None, "duplicate_header", "Column names must be unique.")],
            )
        reader.fieldnames = normalized_headers
        rows: list[dict[str, Any]] = []
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise IngestionValidationError(
                    "CSV row contains more values than the header.",
                    [
                        IngestionIssue(
                            row_number,
                            None,
                            "malformed_row",
                            "Row width exceeds header width.",
                        )
                    ],
                )
            if all(value is None or not str(value).strip() for value in row.values()):
                continue
            rows.append(row)
        return rows
    except csv.Error as exc:
        raise IngestionValidationError(
            "Malformed CSV data.",
            [IngestionIssue(None, None, "malformed_csv", str(exc))],
        ) from exc


def parse_json_bytes(payload: bytes) -> list[dict[str, Any]]:
    try:
        decoded = payload.decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IngestionValidationError(
            "Malformed JSON data.",
            [IngestionIssue(None, None, "malformed_json", str(exc))],
        ) from exc
    if isinstance(value, dict) and "records" in value:
        value = value["records"]
    elif isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        raise IngestionValidationError(
            "JSON must be an object, an array of objects, or {\"records\": [...]}",
            [IngestionIssue(None, None, "invalid_json_shape", "Expected JSON records.")],
        )
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value, start=1):
        if not isinstance(row, dict):
            raise IngestionValidationError(
                "Every JSON record must be an object.",
                [IngestionIssue(index, None, "invalid_record", "Record is not an object.")],
            )
        normalized: dict[str, Any] = {}
        for key, item in row.items():
            normalized_key = _normalize_key(key)
            if normalized_key in normalized:
                raise IngestionValidationError(
                    "JSON record contains duplicate normalized keys.",
                    [
                        IngestionIssue(
                            index,
                            normalized_key,
                            "duplicate_key",
                            "Key occurs more than once after normalization.",
                        )
                    ],
                )
            normalized[normalized_key] = item
        rows.append(normalized)
    return rows


def _clean_text(value: object, *, required: bool, max_length: int, field: str) -> str | None:
    if value is None:
        cleaned = ""
    else:
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
    if not cleaned:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if len(cleaned) > max_length:
        raise ValueError(f"{field} exceeds {max_length} characters")
    return cleaned


def _clean_id(value: object) -> str:
    cleaned = _clean_text(value, required=True, max_length=MAX_ID_LENGTH, field="id")
    assert cleaned is not None
    return cleaned


def _clean_date(value: object, field: str) -> date:
    try:
        return normalize_date(value)
    except NormalizationError as exc:
        raise ValueError(f"{field} {exc}") from exc


def _clean_amount(value: object) -> Decimal:
    try:
        amount = normalize_amount(value)
    except NormalizationError as exc:
        raise ValueError(f"amount {exc}") from exc
    if amount <= 0:
        raise ValueError("amount must be greater than zero")
    if amount >= Decimal("10000000000000000"):
        raise ValueError("amount exceeds NUMERIC(18,2) capacity")
    return amount


def _clean_currency(value: object) -> str:
    try:
        return normalize_currency(value)
    except NormalizationError as exc:
        raise ValueError(str(exc)) from exc


def _clean_name(value: object, field: str, max_length: int) -> str:
    try:
        cleaned = normalize_name(value)
    except NormalizationError as exc:
        raise ValueError(f"{field} {exc}") from exc
    if len(cleaned) > max_length:
        raise ValueError(f"{field} exceeds {max_length} characters")
    return cleaned


def _clean_description(value: object) -> str | None:
    if value is None or not str(value).strip():
        return None
    try:
        cleaned = normalize_description(value)
    except NormalizationError as exc:
        raise ValueError(f"description {exc}") from exc
    if len(cleaned) > 10_000:
        raise ValueError("description exceeds 10000 characters")
    return cleaned


def _mask_account_number(value: object) -> str:
    raw = re.sub(r"[^A-Za-z0-9]", "", str(value or ""))
    if len(raw) < 4:
        raise ValueError("account_number must contain at least four characters")
    return f"XXXX{raw[-4:]}"


def _required_columns(source: SourceType, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise IngestionValidationError(
            "Upload contains no records.",
            [IngestionIssue(None, None, "empty_upload", "At least one record is required.")],
        )
    columns = set().union(*(row.keys() for row in rows))
    allowed = set(REQUIRED_COLUMNS[source])
    required = allowed - OPTIONAL_COLUMNS[source]
    missing = sorted(required - columns)
    unexpected = sorted(columns - allowed)
    issues = [
        IngestionIssue(1, column, "missing_column", f"Required column '{column}' is missing.")
        for column in missing
    ]
    issues.extend(
        IngestionIssue(1, column, "unexpected_column", f"Unexpected column '{column}'.")
        for column in unexpected
    )
    if issues:
        raise IngestionValidationError("Upload columns are invalid.", issues)


def _normalize_row(source: SourceType, row: dict[str, Any]) -> dict[str, object]:
    if source == "bank":
        transaction_type = str(row.get("transaction_type") or "").strip().lower()
        if transaction_type not in {"credit", "debit"}:
            raise ValueError("transaction_type must be credit or debit")
        return {
            "id": _clean_id(row.get("id")),
            "transaction_date": _clean_date(row.get("transaction_date"), "transaction_date"),
            "amount": _clean_amount(row.get("amount")),
            "currency": _clean_currency(row.get("currency")),
            "description": _clean_description(row.get("description")),
            "reference": _clean_text(
                row.get("reference"),
                required=False,
                max_length=255,
                field="reference",
            ),
            "account_number": _mask_account_number(row.get("account_number")),
            "transaction_type": transaction_type,
        }
    if source == "invoices":
        status = str(row.get("status") or "").strip().lower()
        if status not in STATUS_VALUES["invoices"]:
            raise ValueError("invoice status is invalid")
        invoice_date = _clean_date(row.get("invoice_date"), "invoice_date")
        due_date = _clean_date(row.get("due_date"), "due_date")
        if due_date < invoice_date:
            raise ValueError("due_date cannot be before invoice_date")
        return {
            "id": _clean_id(row.get("id")),
            "invoice_number": _clean_text(
                row.get("invoice_number"),
                required=True,
                max_length=128,
                field="invoice_number",
            ),
            "customer": _clean_name(row.get("customer"), "customer", 255),
            "invoice_date": invoice_date,
            "due_date": due_date,
            "amount": _clean_amount(row.get("amount")),
            "currency": _clean_currency(row.get("currency")),
            "status": status,
        }
    status = str(row.get("status") or "").strip().lower()
    if status not in STATUS_VALUES["settlements"]:
        raise ValueError("settlement status is invalid")
    return {
        "id": _clean_id(row.get("id")),
        "settlement_reference": _clean_text(
            row.get("settlement_reference"),
            required=True,
            max_length=128,
            field="settlement_reference",
        ),
        "transaction_date": _clean_date(row.get("transaction_date"), "transaction_date"),
        "amount": _clean_amount(row.get("amount")),
        "currency": _clean_currency(row.get("currency")),
        "processor": _clean_name(row.get("processor"), "processor", 128),
        "customer": _clean_name(row.get("customer"), "customer", 255),
        "status": status,
    }


def _duplicate_keys(source: SourceType, record: dict[str, object]) -> tuple[tuple[str, str], ...]:
    keys = [("id", str(record["id"]))]
    if source == "invoices":
        keys.append(("invoice_number", str(record["invoice_number"])))
    elif source == "settlements":
        keys.append(("settlement_reference", str(record["settlement_reference"])))
    return tuple(keys)


def parse_and_normalize(
    source: SourceType,
    payload: bytes,
    format_name: str,
    max_records: int = MAX_RECORDS,
) -> NormalizedBatch:
    if format_name == "csv":
        rows = parse_csv_bytes(payload)
    elif format_name == "json":
        rows = parse_json_bytes(payload)
    else:
        raise IngestionValidationError(
            "Unsupported upload format.",
            [IngestionIssue(None, None, "unsupported_format", "Use CSV or JSON.")],
        )
    if len(rows) > max_records:
        raise IngestionValidationError(
            "Upload contains too many records.",
            [IngestionIssue(None, None, "too_many_records", f"Maximum is {max_records} records.")],
        )
    _required_columns(source, rows)
    issues: list[IngestionIssue] = []
    normalized: list[dict[str, object]] = []
    seen: dict[tuple[str, str], dict[str, object]] = {}
    duplicates = 0
    for row_number, row in enumerate(rows, start=2 if format_name == "csv" else 1):
        try:
            record = _normalize_row(source, row)
        except ValueError as exc:
            message = str(exc)
            field = message.split(" ", 1)[0] if message else None
            issues.append(IngestionIssue(row_number, field, "invalid_value", message))
            continue
        duplicate_record: dict[str, object] | None = None
        conflict = False
        for key in _duplicate_keys(source, record):
            existing = seen.get(key)
            if existing is not None:
                duplicate_record = existing
                if existing != record:
                    conflict = True
                break
        if duplicate_record is not None:
            if conflict:
                issues.append(
                    IngestionIssue(
                        row_number,
                        key[0],
                        "duplicate_conflict",
                        f"Duplicate {key[0]} has conflicting values.",
                    )
                )
            else:
                duplicates += 1
            continue
        normalized.append(record)
        for key in _duplicate_keys(source, record):
            seen[key] = record
    if issues:
        raise IngestionValidationError("Upload validation failed; no records were stored.", issues)
    return NormalizedBatch(source, format_name, len(rows), normalized, duplicates)
