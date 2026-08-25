from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CashForecastBase(BaseModel):
    forecast_date: date
    opening_balance: Decimal
    expected_receipts: Decimal
    expected_expenses: Decimal
    pending_settlements: Decimal
    projected_balance: Decimal
    risk_level: Literal["low", "medium", "high", "critical"]


class CashForecastCreate(CashForecastBase):
    pass


class CashForecastRead(CashForecastBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime


class CashRiskAlert(BaseModel):
    date: date
    severity: Literal["info", "warning", "critical"]
    message: str
    projected_impact: Decimal


class CashForecastResponse(BaseModel):
    horizon_days: int = Field(ge=1, le=90)
    series: list[CashForecastRead]
    alerts: list[CashRiskAlert]
