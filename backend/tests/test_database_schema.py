from app.database import Base
from app.models import finance  # noqa: F401

EXPECTED_COLUMNS = {
    "bank_transactions": {
        "id",
        "transaction_date",
        "amount",
        "currency",
        "description",
        "reference",
        "account_number",
        "transaction_type",
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
    },
    "reconciliation_results": {
        "id",
        "bank_transaction_id",
        "invoice_id",
        "settlement_id",
        "confidence",
        "status",
        "reason",
        "created_at",
    },
    "exceptions": {
        "id",
        "transaction_id",
        "exception_type",
        "severity",
        "description",
        "recommended_action",
        "confidence",
        "status",
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
        "settlements.id",
    }


def test_exception_transaction_foreign_key_is_present() -> None:
    table = Base.metadata.tables["exceptions"]
    targets = {fk.target_fullname for fk in table.foreign_keys}
    assert targets == {"bank_transactions.id"}
