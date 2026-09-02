"""API contracts for reconciliation run management."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

RunStatus = Literal["pending", "running", "completed", "failed"]
ResultStatus = Literal["matched", "review", "exception"]
ExceptionSeverity = Literal["info", "warning", "critical"]
ExceptionStatus = Literal["open", "in_review", "resolved", "dismissed"]
SourceBatch = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]


class ReconciliationRunRequest(BaseModel):
    source_batch: SourceBatch


class ReconciliationRunSummary(BaseModel):
    run_id: str
    source_batch: str
    status: RunStatus
    records_processed: int = Field(ge=0)
    matched: int = Field(ge=0)
    review: int = Field(ge=0)
    exceptions: int = Field(ge=0)
    match_rate: float = Field(ge=0, le=1)
    processing_time_ms: int = Field(ge=0)
    records_per_second: float = Field(ge=0)
    throughput: float = Field(ge=0)
    matching_time_ms: int = Field(ge=0)
    decision_time_ms: int = Field(ge=0)
    persistence_time_ms: int = Field(ge=0)
    full_cartesian_comparisons: int = Field(ge=0)
    candidate_records_examined: int = Field(ge=0)
    comparison_reduction: float = Field(ge=0, le=100)
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class ReconciliationRunPage(BaseModel):
    items: list[ReconciliationRunSummary]
    page: int
    page_size: int
    total: int


class ReconciliationResultRead(BaseModel):
    id: str
    transaction_id: str
    invoice_id: str | None
    settlement_id: str | None
    status: ResultStatus
    confidence: float = Field(ge=0, le=100)
    reason: str
    best_candidate_id: str | None
    best_candidate_type: Literal["invoice", "settlement"] | None
    best_candidate_amount: float | None
    amount_difference: float | None


class ReconciliationResultPage(BaseModel):
    run_id: str
    items: list[ReconciliationResultRead]
    page: int
    page_size: int
    total: int


class ReconciliationExceptionRead(BaseModel):
    id: str
    transaction_id: str
    predicted_status: Literal["review", "exception"]
    exception_type: str
    severity: ExceptionSeverity
    description: str
    recommended_action: str
    confidence: float = Field(ge=0, le=100)
    status: ExceptionStatus
    best_candidate_id: str | None
    best_candidate_type: Literal["invoice", "settlement"] | None
    bank_amount: float
    candidate_amount: float | None
    amount_difference: float | None
    currency: str


class ReconciliationExceptionPage(BaseModel):
    run_id: str
    items: list[ReconciliationExceptionRead]
    page: int
    page_size: int
    total: int


class ReconciliationMetrics(BaseModel):
    run_id: str
    total_records: int
    matched: int
    review: int
    exceptions: int
    match_rate: float
    processing_time_ms: int
    throughput: float
    matching_time_ms: int
    decision_time_ms: int
    persistence_time_ms: int
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    false_matches: int | None = None
    missed_matches: int | None = None


class SourceBatchSummary(BaseModel):
    source_batch: str
    bank_transactions: int
    invoices: int
    settlements: int


class SourceBatchList(BaseModel):
    items: list[SourceBatchSummary]
    total: int
