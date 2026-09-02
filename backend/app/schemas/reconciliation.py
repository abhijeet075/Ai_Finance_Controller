from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


class ReconciliationRunRequest(BaseModel):
    source_batch: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
    ] = "default"


class ReconciliationRunSummary(BaseModel):
    run_id: str
    source_batch: str
    status: Literal["completed"] = "completed"
    records_processed: int = Field(ge=0)
    matched: int = Field(ge=0)
    review: int = Field(ge=0)
    exceptions: int = Field(ge=0)
    match_rate: float = Field(ge=0, le=1)
    processing_time_ms: int = Field(ge=0)
    records_per_second: float = Field(ge=0)
    full_cartesian_comparisons: int = Field(ge=0)
    candidate_records_examined: int = Field(ge=0)
    comparison_reduction: float = Field(ge=0, le=100)


class OfflineEvaluationMetrics(BaseModel):
    """Quality metrics populated only by the truth-isolated offline evaluator."""

    precision: Decimal = Field(ge=0, le=1)
    recall: Decimal = Field(ge=0, le=1)
    f1: Decimal = Field(ge=0, le=1)
    exact_link_accuracy: Decimal = Field(ge=0, le=1)
    status_accuracy: Decimal = Field(ge=0, le=1)


class ReconciliationExceptionRead(BaseModel):
    transaction_id: str
    predicted_status: Literal["review", "exception"]
    exception_type: str
    best_candidate_id: str | None
    best_candidate_type: Literal["invoice", "settlement"] | None
    confidence: float = Field(ge=0, le=1)
    reason: str
    bank_amount: Decimal
    candidate_amount: Decimal | None
    amount_difference: Decimal | None
    currency: str
