from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ForecastComponent(BaseModel):
    date: date
    expected_receipts: Decimal
    expected_expenses: Decimal
    pending_settlements: Decimal
    projected_cash: Decimal


class ForecastSummary(BaseModel):
    horizon_days: Literal[7, 14, 30]
    as_of_date: date
    source_batch: str | None
    currency: str
    current_cash: Decimal
    expected_receipts: Decimal
    expected_expenses: Decimal
    pending_settlements: Decimal
    projected_cash: Decimal
    series: list[ForecastComponent]
    assumptions: list[str]


class AIMatchRequest(BaseModel):
    run_id: str
    transaction_id: str


class AIMatchSuggestion(BaseModel):
    status: Literal["suggested", "unavailable", "not_eligible"]
    candidate_id: str | None = None
    candidate_type: Literal["invoice", "settlement"] | None = None
    explanation: str
    confidence: float = Field(ge=0, le=1)
    deterministic_checks_passed: bool
    applied: bool = False


class ExceptionAnalysis(BaseModel):
    exception_type: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    explanation: str
    recommended_action: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str]
    generated_by: Literal["llm", "deterministic_fallback"]


class FinanceQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    source_batch: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class EvidenceItem(BaseModel):
    label: str
    value: str
    source: str


class FinanceAnswer(BaseModel):
    answer: str
    evidence: list[EvidenceItem]
    generated_by: Literal["llm", "deterministic_fallback"]
    as_of: datetime


class AuditLogRead(BaseModel):
    id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    created_at: datetime
