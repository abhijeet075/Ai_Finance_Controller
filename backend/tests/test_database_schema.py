from app.database import Base
from app.models import finance  # noqa: F401

EXPECTED_COLUMNS = {
    "audit_logs": {
        "id",
        "actor",
        "action",
        "resource_type",
        "resource_id",
        "outcome",
        "detail_json",
        "created_at",
    },
    "bank_transactions": {
        "id",
        "transaction_date",
        "amount",
        "currency",
        "description",
        "reference",
        "account_number",
        "transaction_type",
        "source_batch",
    },
    "invoices": {
        "id",
        "invoice_number",
        "customer",
        "invoice_date",
        "due_date",
        "amount",
        "currency",
        "status",
        "source_batch",
    },
    "settlements": {
        "id",
        "settlement_reference",
        "transaction_date",
        "amount",
        "currency",
        "processor",
        "customer",
        "status",
        "source_batch",
    },
    "reconciliation_results": {
        "id",
        "run_id",
        "bank_transaction_id",
        "invoice_id",
        "settlement_id",
        "confidence",
        "status",
        "reason",
        "best_candidate_id",
        "best_candidate_type",
        "best_candidate_amount",
        "amount_difference",
        "created_at",
    },
    "exceptions": {
        "id",
        "run_id",
        "transaction_id",
        "exception_type",
        "severity",
        "description",
        "recommended_action",
        "confidence",
        "status",
    },
    "reconciliation_runs": {
        "id",
        "source_batch",
        "status",
        "records_processed",
        "matched_count",
        "review_count",
        "exception_count",
        "match_rate",
        "processing_time_ms",
        "matching_time_ms",
        "decision_time_ms",
        "persistence_time_ms",
        "records_per_second",
        "full_cartesian_comparisons",
        "candidate_records_examined",
        "comparison_reduction",
        "created_at",
        "started_at",
        "completed_at",
        "error_message",
    },
    "cash_forecasts": {
        "id",
        "forecast_date",
        "opening_balance",
        "expected_receipts",
        "expected_expenses",
        "pending_settlements",
        "projected_balance",
        "risk_level",
    },
}


def test_core_tables_are_registered() -> None:
    assert set(EXPECTED_COLUMNS).issubset(Base.metadata.tables)


def test_every_requested_column_is_registered() -> None:
    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        actual_columns = set(Base.metadata.tables[table_name].columns.keys())
        assert expected_columns.issubset(actual_columns), table_name


def test_reconciliation_foreign_keys_are_present() -> None:
    table = Base.metadata.tables["reconciliation_results"]
    targets = {fk.target_fullname for fk in table.foreign_keys}
    assert targets == {
        "bank_transactions.id",
        "invoices.id",
        "reconciliation_runs.id",
        "settlements.id",
    }


def test_exception_transaction_foreign_key_is_present() -> None:
    table = Base.metadata.tables["exceptions"]
    targets = {fk.target_fullname for fk in table.foreign_keys}
    assert targets == {"bank_transactions.id", "reconciliation_runs.id"}


def test_phase12_run_links_are_required() -> None:
    assert not Base.metadata.tables["reconciliation_results"].c.run_id.nullable
    assert not Base.metadata.tables["exceptions"].c.run_id.nullable
