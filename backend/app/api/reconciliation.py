from fastapi import APIRouter, status

from app.schemas.reconciliation import ReconciliationRunAccepted, ReconciliationRunRequest

router = APIRouter()


@router.post(
    "/runs",
    response_model=ReconciliationRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_reconciliation_run(
    request: ReconciliationRunRequest,
) -> ReconciliationRunAccepted:
    return ReconciliationRunAccepted(
        message=f"Batch '{request.source_batch}' was accepted for reconciliation."
    )
