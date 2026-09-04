"""Thin HTTP layer for Phase 12 reconciliation run management."""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.schemas.reconciliation import (
    ReconciliationExceptionPage,
    ReconciliationExceptionRead,
    ReconciliationMetrics,
    ReconciliationResultPage,
    ReconciliationResultRead,
    ReconciliationRunPage,
    ReconciliationRunRequest,
    ReconciliationRunSummary,
    SourceBatchList,
    SourceBatchSummary,
)
from app.services.reconciliation import (
    EmptySourceBatchError,
    ReconciliationExecutionError,
    ReconciliationRunNotFoundError,
    export_exception_report_csv,
    export_predictions_csv,
    get_exceptions_page,
    get_metrics,
    get_results_page,
    get_run_summary,
    get_source_batches,
    list_run_summaries,
    run_reconciliation,
)

logger = logging.getLogger(__name__)
router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_database_session)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def _not_found(exc: ReconciliationRunNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/source-batches",
    response_model=SourceBatchList,
    summary="List source batches available for reconciliation",
)
def read_source_batches(session: SessionDependency) -> SourceBatchList:
    items = [
        SourceBatchSummary.model_validate(item)
        for item in get_source_batches(session)
    ]
    return SourceBatchList(items=items, total=len(items))


@router.get(
    "/runs",
    response_model=ReconciliationRunPage,
    summary="List previous reconciliation runs",
)
def read_runs(
    session: SessionDependency,
    page: Page = 1,
    page_size: PageSize = 50,
    source_batch: str | None = None,
    run_status: Annotated[
        Literal["pending", "running", "completed", "failed"] | None,
        Query(alias="status"),
    ] = None,
) -> ReconciliationRunPage:
    items, total = list_run_summaries(
        session, page, page_size, source_batch, run_status
    )
    return ReconciliationRunPage(
        items=[
            ReconciliationRunSummary.model_validate(item.__dict__)
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/runs",
    response_model=ReconciliationRunSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Run reconciliation for a source batch",
)
def create_reconciliation_run(
    request: ReconciliationRunRequest,
    session: SessionDependency,
) -> ReconciliationRunSummary:
    try:
        result = run_reconciliation(session, request.source_batch)
        return ReconciliationRunSummary.model_validate(result.__dict__)
    except EmptySourceBatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ReconciliationExecutionError as exc:
        logger.exception("Reconciliation run %s failed", exc.run_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Reconciliation failed.",
                "run_id": exc.run_id,
            },
        ) from exc


@router.get(
    "/runs/{run_id}",
    response_model=ReconciliationRunSummary,
    summary="Get a reconciliation run",
)
def read_reconciliation_run(
    run_id: str,
    session: SessionDependency,
) -> ReconciliationRunSummary:
    try:
        return ReconciliationRunSummary.model_validate(
            get_run_summary(session, run_id).__dict__
        )
    except ReconciliationRunNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/runs/{run_id}/results",
    response_model=ReconciliationResultPage,
    summary="Get paginated reconciliation results",
)
def read_results(
    run_id: str,
    session: SessionDependency,
    page: Page = 1,
    page_size: PageSize = 50,
    result_status: Annotated[
        Literal["matched", "review", "exception"] | None,
        Query(alias="status"),
    ] = None,
) -> ReconciliationResultPage:
    try:
        items, total = get_results_page(
            session, run_id, page, page_size, result_status
        )
    except ReconciliationRunNotFoundError as exc:
        raise _not_found(exc) from exc
    return ReconciliationResultPage(
        run_id=run_id,
        items=[
            ReconciliationResultRead.model_validate(item.__dict__)
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/runs/{run_id}/exceptions",
    response_model=ReconciliationExceptionPage,
    summary="Get filtered, paginated reconciliation exceptions",
)
def read_exceptions(
    run_id: str,
    session: SessionDependency,
    page: Page = 1,
    page_size: PageSize = 50,
    severity: Literal["info", "warning", "critical"] | None = None,
    exception_type: str | None = None,
    exception_status: Annotated[
        Literal["open", "in_review", "resolved", "dismissed"] | None,
        Query(alias="status"),
    ] = None,
) -> ReconciliationExceptionPage:
    try:
        items, total = get_exceptions_page(
            session,
            run_id,
            page,
            page_size,
            severity,
            exception_type,
            exception_status,
        )
    except ReconciliationRunNotFoundError as exc:
        raise _not_found(exc) from exc
    return ReconciliationExceptionPage(
        run_id=run_id,
        items=[
            ReconciliationExceptionRead.model_validate(item.__dict__)
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/runs/{run_id}/metrics",
    response_model=ReconciliationMetrics,
    summary="Get operational metrics for a reconciliation run",
)
def read_metrics(
    run_id: str,
    session: SessionDependency,
) -> ReconciliationMetrics:
    try:
        return ReconciliationMetrics.model_validate(get_metrics(session, run_id))
    except ReconciliationRunNotFoundError as exc:
        raise _not_found(exc) from exc


def _csv_response(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/runs/{run_id}/predictions.csv",
    summary="Download run predictions as CSV",
)
def download_predictions_csv(
    run_id: str,
    session: SessionDependency,
) -> Response:
    try:
        content = export_predictions_csv(session, run_id)
    except ReconciliationRunNotFoundError as exc:
        raise _not_found(exc) from exc
    return _csv_response(content, f"run-{run_id}-predictions.csv")


@router.get(
    "/runs/{run_id}/predictions",
    include_in_schema=False,
)
def download_predictions_legacy(
    run_id: str,
    session: SessionDependency,
) -> Response:
    return download_predictions_csv(run_id, session)


@router.get(
    "/runs/{run_id}/exceptions.csv",
    summary="Download the run exception report as CSV",
)
def download_exception_report(
    run_id: str,
    session: SessionDependency,
) -> Response:
    try:
        content = export_exception_report_csv(session, run_id)
    except ReconciliationRunNotFoundError as exc:
        raise _not_found(exc) from exc
    return _csv_response(content, f"run-{run_id}-exceptions.csv")
