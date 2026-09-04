from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_transactions_contract() -> None:
    paths = app.openapi()["paths"]
    assert "get" in paths["/api/transactions"]


def test_reconciliation_contract() -> None:
    paths = app.openapi()["paths"]
    assert "post" in paths["/api/reconciliation/runs"]
    assert "get" in paths["/api/reconciliation/runs"]
    assert "get" in paths["/api/reconciliation/source-batches"]
    assert "get" in paths["/api/reconciliation/runs/{run_id}"]
    assert "get" in paths["/api/reconciliation/runs/{run_id}/results"]
    assert "get" in paths["/api/reconciliation/runs/{run_id}/exceptions"]
    assert "get" in paths["/api/reconciliation/runs/{run_id}/metrics"]
    assert "get" in paths["/api/reconciliation/runs/{run_id}/predictions.csv"]
    assert "get" in paths["/api/reconciliation/runs/{run_id}/exceptions.csv"]


def test_phases14_to18_api_contract() -> None:
    paths = app.openapi()["paths"]
    assert "get" in paths["/api/forecast"]
    assert "get" in paths["/api/forecasts"]
    assert "post" in paths["/api/ai/match"]
    assert "post" in paths["/api/ai/exceptions/{exception_id}/analyze"]
    assert "post" in paths["/api/ai/finance-qa"]
    assert "get" in paths["/api/audit-logs"]


def test_forecast_rejects_invalid_horizon() -> None:
    response = client.get("/api/forecast?days=0")
    assert response.status_code == 422


def test_upload_routes_use_exact_phase_six_paths() -> None:
    paths = set(app.openapi()["paths"])
    assert "/upload/bank" in paths
    assert "/upload/invoices" in paths
    assert "/upload/settlements" in paths
