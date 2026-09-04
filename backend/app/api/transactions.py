from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.models.finance import BankTransaction
from app.schemas.transactions import BankTransactionList, BankTransactionRead

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_database_session)]


@router.get("", response_model=BankTransactionList)
def list_transactions(
    session: SessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    source_batch: str | None = None,
    transaction_type: Literal["credit", "debit"] | None = None,
    currency: str | None = Query(None, min_length=3, max_length=3),
) -> BankTransactionList:
    filters = []
    if source_batch:
        filters.append(BankTransaction.source_batch == source_batch)
    if transaction_type:
        filters.append(BankTransaction.transaction_type == transaction_type)
    if currency:
        filters.append(BankTransaction.currency == currency.upper())
    total = int(
        session.scalar(
            select(func.count(BankTransaction.id)).where(*filters)
        )
        or 0
    )
    statement = (
        select(BankTransaction)
        .where(*filters)
        .order_by(
            BankTransaction.transaction_date.desc(),
            BankTransaction.id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        BankTransactionRead.model_validate(row)
        for row in session.scalars(statement)
    ]
    return BankTransactionList(items=items, total=total)
