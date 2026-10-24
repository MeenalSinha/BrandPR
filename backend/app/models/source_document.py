import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PROCESSING_STATUSES = ("pending", "processing", "processed", "failed")
SOURCE_TYPES = ("pdf", "text", "csv")


class SourceDocument(Base):
    """An uploaded document. Presence of a statement here never makes it an approved fact."""

    __tablename__ = "source_documents"
    __table_args__ = (
        # Target of the composite foreign key that stops facts citing another brand's document.
        UniqueConstraint("id", "brand_id", name="uq_source_documents_id_brand_id"),
        CheckConstraint("processing_status IN ('pending','processing','processed','failed')", name="processing_status"),
        CheckConstraint("source_type IN ('pdf','text','csv')", name="source_type"),
        CheckConstraint("processing_status <> 'processed' OR processed_at IS NOT NULL", name="processed_has_timestamp"),
        CheckConstraint(
            "processing_status <> 'failed' OR (error_message IS NOT NULL AND length(btrim(error_message)) > 0)",
            name="failed_has_error",
        ),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
        # Duplicate policy: one live (non-failed, non-archived) copy of identical content per brand.
        Index(
            "uq_source_documents_live_content",
            "brand_id", "content_hash",
            unique=True,
            postgresql_where=text("processing_status <> 'failed' AND archived_at IS NULL"),
        ),
        Index("ix_source_documents_brand_uploaded", "brand_id", "uploaded_at"),
        Index("ix_source_documents_content_hash", "content_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Relative key inside the configured storage root; never an absolute path, never user-controlled.
    storage_path: Mapped[str | None] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    extracted_text: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DocumentSection(Base):
    """A locatable piece of extracted text: a PDF page, a block of plain text, or a batch of CSV rows."""

    __tablename__ = "document_sections"
    __table_args__ = (
        UniqueConstraint("document_id", "section_index", name="uq_document_sections_document_id_section_index"),
        # Target of the composite foreign key that ties review evidence to the right document (Phase 2).
        UniqueConstraint("id", "document_id", name="uq_document_sections_id_document_id"),
        CheckConstraint("kind IN ('page','text_block','csv_rows')", name="kind"),
        CheckConstraint("page_number IS NULL OR page_number >= 1", name="page_number_positive"),
        Index("ix_document_sections_document_page", "document_id", "page_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False
    )
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    line_start: Mapped[int | None] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer)
    row_start: Mapped[int | None] = mapped_column(Integer)
    row_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    meta: Mapped[dict | None] = mapped_column(JSONB)
