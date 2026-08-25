from pydantic import BaseModel, Field


class IngestionIssueResponse(BaseModel):
    row: int | None = None
    field: str | None = None
    code: str
    message: str


class IngestionResponse(BaseModel):
    source: str
    format: str
    received_records: int = Field(ge=0)
    normalized_records: int = Field(ge=0)
    inserted_records: int = Field(ge=0)
    duplicate_records: int = Field(ge=0)
    status: str = "stored"
