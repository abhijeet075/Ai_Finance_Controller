"""Backward-compatible singular forecast route."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.schemas.intelligence import ForecastSummary
from app.services.forecasting import build_cash_forecast

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_database_session)]


@router.get("", response_model=ForecastSummary)
def get_forecast(
    session: SessionDep,
    days: int = Query(default=30, ge=1, le=90),
    source_batch: str | None = None,
    currency: str | None = Query(None, min_length=3, max_length=3),
) -> ForecastSummary:
    try:
        data = build_cash_forecast(
            session,
            days,
            source_batch,
            currency.upper() if currency else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ForecastSummary.model_validate(data)
