from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BankTransactionBase(BaseModel):
    transaction_date: date
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    description: str | None = None
    reference: str | None = Field(default=None, max_length=255)
    account_number: str = Field(min_length=1, max_length=128)
    transaction_type: Literal["credit", "debit"]

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class BankTransactionCreate(BankTransactionBase):
    pass


class BankTransactionRead(BankTransactionBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime


class BankTransactionList(BaseModel):
    items: list[BankTransactionRead]
    total: int = Field(ge=0)
