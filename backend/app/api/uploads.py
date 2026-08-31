from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.config import get_settings
from app.database import get_database_session
from app.repositories.ingestion import (
    IngestionConflictError,
    IngestionPersistenceError,
    store_batch,
)
from app.schemas.ingestion import IngestionResponse
from app.services.ingestion import (
    IngestionValidationError,
    SourceType,
    parse_and_normalize,
)

router = APIRouter()


def _detect_format(content_type: str, filename: str | None = None) -> str:
    media_type = content_type.split(";", 1)[0].strip().lower()
    suffix = (filename or "").lower()
    if media_type in {"text/csv", "application/csv", "text/plain"} or suffix.endswith(".csv"):
        return "csv"
    if media_type in {"application/json", "text/json"} or suffix.endswith(".json"):
        return "json"
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail={"message": "Only CSV and JSON uploads are supported."},
    )


async def _read_upload(request: Request) -> tuple[bytes, str]:
    settings = get_settings()
    request_type = request.headers.get("content-type", "")
    media_type = request_type.split(";", 1)[0].strip().lower()
    filename: str | None = None
    file_type = request_type
    if media_type == "multipart/form-data":
        form = await request.form()
        candidate = form.get("file")
        if not isinstance(candidate, UploadFile):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "Multipart uploads require a 'file' field."},
            )
        filename = candidate.filename
        file_type = candidate.content_type or ""
        payload = await candidate.read(settings.max_upload_bytes + 1)
    else:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = 0
            if declared_size > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail={"message": f"Upload exceeds {settings.max_upload_bytes} bytes."},
                )
        chunks = bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks) > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail={"message": f"Upload exceeds {settings.max_upload_bytes} bytes."},
                )
        payload = bytes(chunks)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Upload body is empty."},
        )
    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"message": f"Upload exceeds {settings.max_upload_bytes} bytes."},
        )
    return payload, _detect_format(file_type, filename)


async def _ingest(
    source: SourceType,
    request: Request,
    session: Session,
    source_batch: str,
) -> IngestionResponse:
    source_batch = source_batch.strip()
    if not source_batch:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "source_batch cannot be blank."},
        )
    payload, format_name = await _read_upload(request)
    try:
        batch = parse_and_normalize(
            source,
            payload,
            format_name,
            max_records=get_settings().max_upload_records,
        )
        for record in batch.records:
            record["source_batch"] = source_batch
    except IngestionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": str(exc),
                "errors": [issue.to_dict() for issue in exc.issues],
            },
        ) from exc
    try:
        inserted, database_duplicates = store_batch(session, batch)
    except IngestionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc)},
        ) from exc
    except IngestionPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "The validated batch could not be stored."},
        ) from exc
    return IngestionResponse(
        source=source,
        format=format_name,
        received_records=batch.received_records,
        normalized_records=len(batch.records),
        inserted_records=inserted,
        duplicate_records=batch.duplicate_records + database_duplicates,
    )


@router.post("/bank", response_model=IngestionResponse)
async def upload_bank(
    request: Request,
    session: Session = Depends(get_database_session),
    source_batch: str = Query(default="default", min_length=1, max_length=128),
) -> IngestionResponse:
    return await _ingest("bank", request, session, source_batch)


@router.post("/invoices", response_model=IngestionResponse)
async def upload_invoices(
    request: Request,
    session: Session = Depends(get_database_session),
    source_batch: str = Query(default="default", min_length=1, max_length=128),
) -> IngestionResponse:
    return await _ingest("invoices", request, session, source_batch)


@router.post("/settlements", response_model=IngestionResponse)
async def upload_settlements(
    request: Request,
    session: Session = Depends(get_database_session),
    source_batch: str = Query(default="default", min_length=1, max_length=128),
) -> IngestionResponse:
    return await _ingest("settlements", request, session, source_batch)
