from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExceptionBase(BaseModel):
    transaction_id: str
    exception_type: str = Field(min_length=1, max_length=64)
    severity: Literal["info", "warning", "critical"]
    description: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    confidence: Decimal = Field(ge=0, le=100)
    status: Literal["open", "in_review", "resolved", "dismissed"]


class ExceptionCreate(ExceptionBase):
    pass


class ExceptionRead(ExceptionBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime


class ExceptionList(BaseModel):
    items: list[ExceptionRead]
    total: int = Field(ge=0)
