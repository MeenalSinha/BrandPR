"""Source-document upload, processing and lifecycle.

Policies (documented in docs/DATA_MODEL.md):
  * Duplicate: identical content (sha256) in the same brand is rejected with 409 while a live copy exists.
    A failed or archived copy does not block re-upload.
  * Unsupported type, empty file or oversize file: rejected, nothing stored, no record created.
  * Corrupt but well-typed file: a record is kept with processing_status=failed and a useful error;
    the stored file is removed so a failed record is never mistaken for a usable source.
  * Delete: refused with 409 while facts cite the document; archive it instead. Archived documents
    stay visible to the facts that cite them (flagged) and cannot be cited by new facts.
"""
import hashlib
import logging
import uuid
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, PayloadTooLarge
from app.models import ApprovedFact, DocumentSection, SourceDocument
from app.schemas.document import DocumentRead, TableRead, TableRow
from app.services import extraction, storage
from app.services.brands import get_brand

logger = logging.getLogger("brandpr.documents")
CHUNK = 64 * 1024


def read_limited(stream: BinaryIO, limit: int) -> bytes:
    """Read an upload without ever holding more than limit + one chunk in memory."""
    parts, total = [], 0
    while True:
        chunk = stream.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise PayloadTooLarge(f"The file exceeds the {limit // (1024 * 1024)} MB upload limit." if limit >= 1024 * 1024
                                  else f"The file exceeds the {limit} byte upload limit.")
        parts.append(chunk)
    return b"".join(parts)


def get_document(db: Session, document_id: uuid.UUID) -> SourceDocument:
    doc = db.get(SourceDocument, document_id)
    if doc is None:
        raise NotFoundError("Document not found.")
    return doc


def to_read(db: Session, doc: SourceDocument) -> DocumentRead:
    return to_read_many(db, [doc])[0]


def to_read_many(db: Session, docs: list[SourceDocument]) -> list[DocumentRead]:
    if not docs:
        return []
    ids = [d.id for d in docs]
    sec = {
        r[0]: (r[1], r[2])
        for r in db.execute(
            select(DocumentSection.document_id, func.count(), func.coalesce(func.sum(func.length(DocumentSection.text)), 0))
            .where(DocumentSection.document_id.in_(ids))
            .group_by(DocumentSection.document_id)
        )
    }
    facts = dict(
        db.execute(
            select(ApprovedFact.source_document_id, func.count())
            .where(ApprovedFact.source_document_id.in_(ids))
            .group_by(ApprovedFact.source_document_id)
        ).all()
    )
    out = []
    for d in docs:
        count, chars = sec.get(d.id, (0, 0))
        out.append(
            DocumentRead(
                id=d.id, brand_id=d.brand_id, title=d.title, filename=d.filename, mime_type=d.mime_type,
                size_bytes=d.size_bytes, source_type=d.source_type, processing_status=d.processing_status,
                content_hash=d.content_hash, page_count=d.page_count, section_count=count, char_count=int(chars),
                fact_count=facts.get(d.id, 0), uploaded_at=d.uploaded_at, processed_at=d.processed_at,
                error_message=d.error_message, archived_at=d.archived_at,
            )
        )
    return out


def list_documents(
    db: Session, brand_id: uuid.UUID, *, limit: int, offset: int, status: str | None, include_archived: bool
) -> tuple[list[SourceDocument], int]:
    get_brand(db, brand_id)
    cond = [SourceDocument.brand_id == brand_id]
    if status:
        cond.append(SourceDocument.processing_status == status)
    if not include_archived:
        cond.append(SourceDocument.archived_at.is_(None))
    total = db.scalar(select(func.count()).select_from(SourceDocument).where(*cond)) or 0
    rows = db.scalars(
        select(SourceDocument).where(*cond).order_by(SourceDocument.uploaded_at.desc(), SourceDocument.id).limit(limit).offset(offset)
    ).all()
    return list(rows), total


def upload_document(
    db: Session, brand_id: uuid.UUID, *, filename: str | None, title: str | None, stream: BinaryIO
) -> SourceDocument:
    settings = get_settings()
    get_brand(db, brand_id)
    data = read_limited(stream, settings.max_upload_bytes)
    display_name = extraction.sanitize_filename(filename)
    kind = extraction.detect_type(display_name, data)  # raises for empty / unsupported / mismatched content
    digest = hashlib.sha256(data).hexdigest()

    existing = db.scalar(
        select(SourceDocument).where(
            SourceDocument.brand_id == brand_id,
            SourceDocument.content_hash == digest,
            SourceDocument.processing_status != "failed",
            SourceDocument.archived_at.is_(None),
        )
    )
    if existing is not None:
        raise ConflictError(
            "This file has already been uploaded for this brand.",
            code="duplicate_document",
            details=[{"field": "file", "message": f"existing_document_id={existing.id}"}],
        )

    doc = SourceDocument(
        id=uuid.uuid4(), brand_id=brand_id, title=(title or "").strip()[:300] or display_name, filename=display_name,
        mime_type=extraction.MIME_BY_TYPE[kind], size_bytes=len(data), source_type=kind,
        processing_status="pending", content_hash=digest,
    )
    db.add(doc)
    db.commit()  # the pending record exists before any processing starts

    key: str | None = None
    try:
        key = storage.save(brand_id, doc.id, data, kind)
        doc.storage_path = key
        doc.processing_status = "processing"
        db.commit()

        result = extraction.extract(kind, data, max_pdf_pages=settings.max_pdf_pages, max_csv_rows=settings.max_csv_rows)
        for index, s in enumerate(result.sections):
            db.add(
                DocumentSection(
                    document_id=doc.id, section_index=index, kind=s.kind, page_number=s.page_number,
                    line_start=s.line_start, line_end=s.line_end, row_start=s.row_start, row_end=s.row_end,
                    text=s.text, meta=s.meta,
                )
            )
        doc.extracted_text = result.text
        doc.page_count = result.page_count
        doc.processing_status = "processed"
        doc.processed_at = clock.now()
        doc.error_message = None
        db.commit()
    except extraction.ExtractionFailed as exc:
        _mark_failed(db, doc, str(exc), key)
    except Exception:
        logger.exception("Unexpected failure while processing document %s", doc.id)
        _mark_failed(db, doc, "Processing failed unexpectedly. The file was not stored.", key)
    db.refresh(doc)
    return doc


def _mark_failed(db: Session, doc: SourceDocument, message: str, key: str | None) -> None:
    db.rollback()
    storage.delete(key)
    doc = db.get(SourceDocument, doc.id)  # reload after rollback
    assert doc is not None
    db.query(DocumentSection).filter(DocumentSection.document_id == doc.id).delete()
    doc.processing_status = "failed"
    doc.error_message = message
    doc.storage_path = None
    doc.extracted_text = None
    doc.page_count = None
    doc.processed_at = None
    db.commit()


def archive_document(db: Session, document_id: uuid.UUID) -> SourceDocument:
    doc = get_document(db, document_id)
    if doc.archived_at is None:
        doc.archived_at = clock.now()
        db.commit()
        db.refresh(doc)
    return doc


def delete_document(db: Session, document_id: uuid.UUID) -> None:
    doc = get_document(db, document_id)
    used_by = db.scalar(select(func.count()).select_from(ApprovedFact).where(ApprovedFact.source_document_id == doc.id)) or 0
    if used_by:
        raise ConflictError(
            f"This document is cited by {used_by} approved fact(s) and cannot be deleted. Archive it instead.",
            code="document_in_use",
        )
    key = doc.storage_path
    db.delete(doc)
    db.commit()
    storage.delete(key)


def list_sections(
    db: Session, document_id: uuid.UUID, *, page_number: int | None, limit: int, offset: int
) -> tuple[list[DocumentSection], int]:
    get_document(db, document_id)
    cond = [DocumentSection.document_id == document_id]
    if page_number is not None:
        cond.append(DocumentSection.page_number == page_number)
    total = db.scalar(select(func.count()).select_from(DocumentSection).where(*cond)) or 0
    rows = db.scalars(select(DocumentSection).where(*cond).order_by(DocumentSection.section_index).limit(limit).offset(offset)).all()
    return list(rows), total


def table_view(db: Session, document_id: uuid.UUID, *, limit: int, offset: int) -> TableRead:
    doc = get_document(db, document_id)
    if doc.source_type != "csv" or doc.processing_status != "processed":
        raise ConflictError("Table view is only available for processed CSV documents.", code="not_a_table")
    sections = db.scalars(
        select(DocumentSection).where(DocumentSection.document_id == doc.id).order_by(DocumentSection.section_index)
    ).all()
    headers: list[str] = sections[0].meta["headers"] if sections and sections[0].meta else []
    total = sections[0].meta["total_rows"] if sections and sections[0].meta else 0
    rows = [
        TableRow(row_number=r["row_number"], cells=r["cells"])
        for s in sections for r in (s.meta or {}).get("rows", [])
    ][offset : offset + limit]
    return TableRead(document_id=doc.id, headers=headers, rows=rows, total_rows=total, limit=limit, offset=offset)
