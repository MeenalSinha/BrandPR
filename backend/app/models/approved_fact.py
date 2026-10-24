import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Approval lifecycle. Validity is separate and derived from valid_from / expires_at.
FACT_STATUSES = ("proposed", "active", "rejected", "expired", "retired")
FACT_CATEGORIES = ("product_spec", "approved_claim", "terminology", "legal_disclaimer", "pricing", "general")


class ApprovedFact(Base):
    __tablename__ = "approved_facts"
    __table_args__ = (
        # A fact may only cite a document belonging to the same brand (enforced by the database).
        ForeignKeyConstraint(
            ["source_document_id", "brand_id"],
            ["source_documents.id", "source_documents.brand_id"],
            name="fk_approved_facts_source_same_brand",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('proposed','active','rejected','expired','retired')", name="status"),
        CheckConstraint(
            "category IN ('product_spec','approved_claim','terminology','legal_disclaimer','pricing','general')",
            name="category",
        ),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(btrim(value)) > 0", name="value_not_blank"),
        CheckConstraint("expires_at IS NULL OR valid_from IS NULL OR expires_at >= valid_from", name="dates_ordered"),
        CheckConstraint("source_page IS NULL OR source_page >= 1", name="source_page_positive"),
        CheckConstraint("source_page IS NULL OR source_document_id IS NOT NULL", name="page_requires_document"),
        # Explicit provenance policy: every fact cites a document or states a manual source.
        CheckConstraint(
            "source_document_id IS NOT NULL OR (source_note IS NOT NULL AND length(btrim(source_note)) > 0)",
            name="has_provenance",
        ),
        CheckConstraint("status <> 'active' OR approved_at IS NOT NULL", name="active_has_approval"),
        CheckConstraint("version >= 1", name="version_positive"),
        # Target of composite foreign keys that keep review evidence inside one brand (Phase 2).
        UniqueConstraint("id", "brand_id", name="uq_approved_facts_id_brand_id"),
        Index("ix_approved_facts_brand_status", "brand_id", "status"),
        Index("ix_approved_facts_brand_category", "brand_id", "category"),
        Index("ix_approved_facts_brand_review_date", "brand_id", "review_date"),
        Index("ix_approved_facts_brand_expires_at", "brand_id", "expires_at"),
        Index("ix_approved_facts_source_document_id", "source_document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, server_default="general")
    qualifications: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="proposed")
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    source_excerpt_verified: Mapped[bool | None] = mapped_column(Boolean)
    source_note: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(200))
    valid_from: Mapped[date | None] = mapped_column(Date)
    review_date: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    approved_by: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FactRevision(Base):
    """Append-only history. Every create, edit and status change writes one row in the same transaction."""

    __tablename__ = "fact_revisions"
    __table_args__ = (
        UniqueConstraint("fact_id", "revision_number", name="uq_fact_revisions_fact_id_revision_number"),
        # Target of the composite foreign key that keeps a Phase 3 impact pointing at a revision of its own fact.
        UniqueConstraint("id", "fact_id", name="uq_fact_revisions_id_fact_id"),
        CheckConstraint("action IN ('created','updated','status_changed')", name="action"),
        Index("ix_fact_revisions_fact_id", "fact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approved_facts.id", ondelete="RESTRICT"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(200))
    change_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
