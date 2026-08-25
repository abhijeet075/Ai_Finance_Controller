from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SettlementBase(BaseModel):
    settlement_reference: str = Field(min_length=1, max_length=128)
    transaction_date: date
    amount: Decimal
    processor: str = Field(min_length=1, max_length=128)
    customer: str = Field(min_length=1, max_length=255)
    status: Literal["pending", "completed", "failed", "reversed"]


class SettlementCreate(SettlementBase):
    pass


class SettlementRead(SettlementBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime
