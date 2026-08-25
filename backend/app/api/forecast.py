from fastapi import APIRouter, Query

from app.schemas.forecast import CashForecastResponse

router = APIRouter()


@router.get("", response_model=CashForecastResponse)
def get_forecast(days: int = Query(default=30, ge=1, le=90)) -> CashForecastResponse:
    return CashForecastResponse(horizon_days=days, series=[], alerts=[])
