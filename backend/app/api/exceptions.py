from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.models.finance import ExceptionRecord
from app.schemas.exceptions import ExceptionList, ExceptionRead

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_database_session)]


@router.get("", response_model=ExceptionList)
def list_exceptions(
    session: SessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    run_id: str | None = None,
    severity: Literal["info", "warning", "critical"] | None = None,
    status: Literal[
        "open", "in_review", "resolved", "dismissed"
    ]
    | None = None,
) -> ExceptionList:
    filters = []
    if run_id:
        filters.append(ExceptionRecord.run_id == run_id)
    if severity:
        filters.append(ExceptionRecord.severity == severity)
    if status:
        filters.append(ExceptionRecord.status == status)
    total = int(
        session.scalar(select(func.count(ExceptionRecord.id)).where(*filters))
        or 0
    )
    statement = (
        select(ExceptionRecord)
        .where(*filters)
        .order_by(ExceptionRecord.created_at.desc(), ExceptionRecord.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        ExceptionRead.model_validate(row)
        for row in session.scalars(statement)
    ]
    return ExceptionList(items=items, total=total)
