from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvoiceBase(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=128)
    customer: str = Field(min_length=1, max_length=255)
    invoice_date: date
    due_date: date
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    status: Literal["open", "partial", "paid", "overdue", "cancelled"]

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceRead(InvoiceBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime
