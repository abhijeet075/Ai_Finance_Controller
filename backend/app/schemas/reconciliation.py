from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DecisionStatus = Literal["matched", "review", "exception"]


class ReconciliationRunRequest(BaseModel):
    source_batch: str = Field(default="default", min_length=1, max_length=128)


class ReconciliationRunAccepted(BaseModel):
    status: Literal["accepted"] = "accepted"
    message: str


class ReconciliationResultCreate(BaseModel):
    bank_transaction_id: str
    invoice_id: str | None = None
    settlement_id: str | None = None
    confidence: Decimal = Field(ge=0, le=100)
    status: DecisionStatus
    reason: str = Field(min_length=1)


class ReconciliationResultRead(ReconciliationResultCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
