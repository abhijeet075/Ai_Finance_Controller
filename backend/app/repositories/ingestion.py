"""PostgreSQL persistence for validated ingestion batches."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.finance import BankTransaction, Invoice, Settlement
from app.services.ingestion import NormalizedBatch

MODEL_BY_SOURCE = {
    "bank": BankTransaction,
    "invoices": Invoice,
    "settlements": Settlement,
}


class IngestionPersistenceError(RuntimeError):
    pass


class IngestionConflictError(IngestionPersistenceError):
    pass


def _record_matches(existing: object, record: dict[str, object]) -> bool:
    return all(getattr(existing, field) == value for field, value in record.items())


def store_batch(
    session: Session,
    batch: NormalizedBatch,
    *,
    commit: bool = True,
) -> tuple[int, int]:
    """Insert one validated batch atomically; return inserted and exact-duplicate counts."""
    model = MODEL_BY_SOURCE[batch.source]
    records = batch.records
    if not records:
        return 0, 0

    ids = [str(record["id"]) for record in records]
    natural_field: str | None = None
    natural_column = None
    if batch.source == "invoices":
        natural_field = "invoice_number"
        natural_column = Invoice.invoice_number
    elif batch.source == "settlements":
        natural_field = "settlement_reference"
        natural_column = Settlement.settlement_reference

    predicates = [model.id.in_(ids)]
    if natural_field and natural_column is not None:
        values = [str(record[natural_field]) for record in records]
        predicates.append(natural_column.in_(values))
    existing_rows = list(session.scalars(select(model).where(or_(*predicates))))
    by_id = {str(row.id): row for row in existing_rows}
    by_natural = (
        {str(getattr(row, natural_field)): row for row in existing_rows}
        if natural_field
        else {}
    )

    new_records: list[dict[str, object]] = []
    duplicate_count = 0
    for record in records:
        existing = by_id.get(str(record["id"]))
        if existing is None and natural_field:
            existing = by_natural.get(str(record[natural_field]))
        if existing is None:
            new_records.append(record)
        elif _record_matches(existing, record):
            duplicate_count += 1
        else:
            raise IngestionConflictError(
                f"Stored {batch.source} record conflicts with upload key {record['id']}."
            )

    try:
        session.add_all(model(**record) for record in new_records)
        if commit:
            session.commit()
        else:
            session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise IngestionConflictError(
            "A concurrent upload created a conflicting record. Retry after reviewing duplicates."
        ) from exc
    except Exception as exc:
        session.rollback()
        raise IngestionPersistenceError("PostgreSQL rejected the ingestion batch.") from exc
    return len(new_records), duplicate_count
