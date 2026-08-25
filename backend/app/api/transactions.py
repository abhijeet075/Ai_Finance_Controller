from fastapi import APIRouter

from app.schemas.transactions import BankTransactionList

router = APIRouter()


@router.get("", response_model=BankTransactionList)
def list_transactions() -> BankTransactionList:
    return BankTransactionList(items=[], total=0)
