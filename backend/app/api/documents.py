import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse, Response

from app.api.deps import DbSession, Limit, Offset, OptionalActor, verify_brand_access
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.schemas.common import ERROR_RESPONSES, ErrorResponse, Page
from app.schemas.document import DocumentRead, DocumentTextRead, SectionRead, TableRead
from app.services import documents as svc
from app.services import storage

router = APIRouter(tags=["documents"])
UPLOAD_ERRORS = {
    **ERROR_RESPONSES,
    413: {"model": ErrorResponse, "description": "File exceeds the configured size limit"},
    415: {"model": ErrorResponse, "description": "Unsupported or mismatched file type"},
}


@router.get("/brands/{brand_id}/documents", response_model=Page[DocumentRead], responses=ERROR_RESPONSES, summary="List source documents")
def list_documents(
    brand_id: uuid.UUID, db: DbSession, limit: Limit = 50, offset: Offset = 0,
    processing_status: Literal["pending", "processing", "processed", "failed"] | None = None,
    include_archived: bool = False,
    actor: OptionalActor = None,
):
    verify_brand_access(brand_id, actor)
    rows, total = svc.list_documents(db, brand_id, limit=limit, offset=offset, status=processing_status, include_archived=include_archived)
    return Page(items=svc.to_read_many(db, rows), total=total, limit=limit, offset=offset)


@router.post(
    "/brands/{brand_id}/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED,
    responses=UPLOAD_ERRORS, summary="Upload a source document (PDF, TXT or CSV)",
    description="Returns 201 with the stored record. If the file is well-typed but cannot be processed, "
    "the record is returned with processing_status=failed and an error_message.",
)
def upload_document(
    brand_id: uuid.UUID, db: DbSession, file: Annotated[UploadFile, File(description="PDF, plain text or CSV")],
    title: Annotated[str | None, Form(max_length=300)] = None,
    actor: OptionalActor = None,
):
    verify_brand_access(brand_id, actor)
    doc = svc.upload_document(db, brand_id, filename=file.filename, title=title, stream=file.file)
    return svc.to_read(db, doc)


@router.get("/documents/{document_id}", response_model=DocumentRead, responses=ERROR_RESPONSES, summary="Get document metadata")
def get_document(document_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    doc = svc.get_document(db, document_id)
    verify_brand_access(doc.brand_id, actor)
    return svc.to_read(db, doc)


@router.get("/documents/{document_id}/sections", response_model=Page[SectionRead], responses=ERROR_RESPONSES, summary="List extracted sections with page references")
def list_sections(document_id: uuid.UUID, db: DbSession, page_number: Annotated[int | None, Query(ge=1)] = None, limit: Limit = 200, offset: Offset = 0, actor: OptionalActor = None):
    doc = svc.get_document(db, document_id)
    verify_brand_access(doc.brand_id, actor)
    rows, total = svc.list_sections(db, document_id, page_number=page_number, limit=limit, offset=offset)
    return Page(items=[SectionRead.model_validate(r, from_attributes=True) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/documents/{document_id}/text", response_model=DocumentTextRead, responses=ERROR_RESPONSES, summary="Full extracted text")
def get_text(document_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    doc = svc.get_document(db, document_id)
    verify_brand_access(doc.brand_id, actor)
    if doc.processing_status != "processed":
        raise ConflictError("The document has no extracted text because processing did not succeed.", code="not_processed")
    return DocumentTextRead(document_id=doc.id, title=doc.title, text=doc.extracted_text or "")


@router.get("/documents/{document_id}/table", response_model=TableRead, responses=ERROR_RESPONSES, summary="CSV headers and rows")
def get_table(document_id: uuid.UUID, db: DbSession, limit: Limit = 100, offset: Offset = 0, actor: OptionalActor = None):
    doc = svc.get_document(db, document_id)
    verify_brand_access(doc.brand_id, actor)
    return svc.table_view(db, document_id, limit=limit, offset=offset)


@router.get("/documents/{document_id}/file", responses=ERROR_RESPONSES, summary="Download the original file")
def download_file(document_id: uuid.UUID, db: DbSession, inline: bool = False, actor: OptionalActor = None):
    doc = svc.get_document(db, document_id)
    verify_brand_access(doc.brand_id, actor)
    if not doc.storage_path:
        raise NotFoundError("The original file is not available.")
    disposition = "inline" if inline and doc.source_type == "pdf" else "attachment"
    settings = get_settings()
    if settings.gcs_bucket:
        data = storage.read_bytes(doc.storage_path)
        if data is None:
            raise NotFoundError("The original file is not available.")
        return Response(
            content=data,
            media_type=doc.mime_type,
            headers={
                "Content-Disposition": f'{disposition}; filename="{doc.filename}"',
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; sandbox",
            },
        )
    try:
        path = storage.resolve(doc.storage_path)
    except storage.StorageError:
        raise NotFoundError("The original file is not available.") from None
    if not path.is_file():
        raise NotFoundError("The original file is not available.")
    return FileResponse(
        path, media_type=doc.mime_type, filename=doc.filename, content_disposition_type=disposition,
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"},
    )


@router.post("/documents/{document_id}/archive", response_model=DocumentRead, responses=ERROR_RESPONSES, summary="Archive a document")
def archive_document(document_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    doc = svc.get_document(db, document_id)
    verify_brand_access(doc.brand_id, actor)
    return svc.to_read(db, svc.archive_document(db, document_id))


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, responses=ERROR_RESPONSES, summary="Delete an unreferenced document")
def delete_document(document_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    doc = svc.get_document(db, document_id)
    verify_brand_access(doc.brand_id, actor)
    svc.delete_document(db, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
