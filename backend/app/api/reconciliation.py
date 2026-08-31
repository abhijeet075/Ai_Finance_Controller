from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.schemas.reconciliation import ReconciliationRunRequest, ReconciliationRunSummary
from app.services.reconciliation import (
    EmptySourceBatchError,
    ReconciliationRunNotFoundError,
    export_predictions_csv,
    get_run_summary,
    run_reconciliation,
)

router = APIRouter()


@router.post(
    "/runs",
    response_model=ReconciliationRunSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_reconciliation_run(
    request: ReconciliationRunRequest,
    session: Session = Depends(get_database_session),
) -> ReconciliationRunSummary:
    try:
        return ReconciliationRunSummary.model_validate(
            run_reconciliation(session, request.source_batch).__dict__
        )
    except EmptySourceBatchError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=ReconciliationRunSummary)
def read_reconciliation_run(
    run_id: str,
    session: Session = Depends(get_database_session),
) -> ReconciliationRunSummary:
    try:
        return ReconciliationRunSummary.model_validate(get_run_summary(session, run_id).__dict__)
    except ReconciliationRunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/runs/{run_id}/predictions")
def download_predictions(
    run_id: str,
    session: Session = Depends(get_database_session),
) -> Response:
    try:
        content = export_predictions_csv(session, run_id)
    except ReconciliationRunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="predictions-{run_id}.csv"'
        },
    )
