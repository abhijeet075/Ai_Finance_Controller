from fastapi import APIRouter

from app.schemas.exceptions import ExceptionList

router = APIRouter()


@router.get("", response_model=ExceptionList)
def list_exceptions() -> ExceptionList:
    return ExceptionList(items=[], total=0)
