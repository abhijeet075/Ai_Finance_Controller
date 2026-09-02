from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_transactions_contract() -> None:
    response = client.get("/api/transactions")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


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


def test_forecast_rejects_invalid_horizon() -> None:
    response = client.get("/api/forecast?days=0")
    assert response.status_code == 422


def test_upload_routes_use_exact_phase_six_paths() -> None:
    paths = set(app.openapi()["paths"])
    assert "/upload/bank" in paths
    assert "/upload/invoices" in paths
    assert "/upload/settlements" in paths
