from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_api_identity
from app.database import get_database_session
from app.models.finance import AuditLog
from app.schemas.intelligence import (
    AIMatchRequest,
    AIMatchSuggestion,
    AuditLogRead,
    ExceptionAnalysis,
    FinanceAnswer,
    FinanceQuestion,
    ForecastSummary,
)
from app.services.forecasting import build_cash_forecast
from app.services.intelligence import (
    analyze_exception,
    answer_finance_question,
    suggest_ambiguous_match,
    write_audit,
)

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_database_session)]
Identity = Annotated[str, Depends(require_api_identity)]


@router.get("/forecasts", response_model=ForecastSummary)
def forecast(
    session: SessionDep,
    horizon_days: int = Query(30),
    source_batch: str | None = None,
    currency: str | None = Query(None, min_length=3, max_length=3),
) -> ForecastSummary:
    try:
        data = build_cash_forecast(
            session,
            horizon_days,
            source_batch,
            currency.upper() if currency else None,
        )
        return ForecastSummary.model_validate(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/ai/match", response_model=AIMatchSuggestion)
def ai_match(
    body: AIMatchRequest,
    session: SessionDep,
    actor: Identity,
) -> AIMatchSuggestion:
    try:
        result = suggest_ambiguous_match(
            session, body.run_id, body.transaction_id
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    write_audit(
        session,
        actor,
        "ai_match_suggested",
        "bank_transaction",
        body.transaction_id,
        str(result["status"]),
        result,
    )
    return AIMatchSuggestion.model_validate(result)


@router.post(
    "/ai/exceptions/{exception_id}/analyze",
    response_model=ExceptionAnalysis,
)
def exception_analysis(
    exception_id: str,
    session: SessionDep,
    actor: Identity,
) -> ExceptionAnalysis:
    try:
        result = analyze_exception(session, exception_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    write_audit(
        session,
        actor,
        "exception_analyzed",
        "exception",
        exception_id,
        "success",
        {"generated_by": result["generated_by"]},
    )
    return ExceptionAnalysis.model_validate(result)


@router.post("/ai/finance-qa", response_model=FinanceAnswer)
def finance_qa(
    body: FinanceQuestion,
    session: SessionDep,
    actor: Identity,
) -> FinanceAnswer:
    result = answer_finance_question(
        session,
        body.question,
        body.source_batch,
        body.currency.upper() if body.currency else None,
    )
    write_audit(
        session,
        actor,
        "finance_question_answered",
        "finance_qa",
        None,
        "success",
        {
            "question": body.question,
            "generated_by": result["generated_by"],
        },
    )
    return FinanceAnswer.model_validate(result)


@router.get("/audit-logs", response_model=list[AuditLogRead])
def audit_logs(
    session: SessionDep,
    actor: Identity,
    limit: int = Query(50, ge=1, le=200),
) -> list[AuditLogRead]:
    statement = select(AuditLog).order_by(
        AuditLog.created_at.desc()
    ).limit(limit)
    rows = session.scalars(statement)
    return [
        AuditLogRead.model_validate(
            {
                "id": row.id,
                "actor": row.actor,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "outcome": row.outcome,
                "created_at": row.created_at,
            }
        )
        for row in rows
    ]
