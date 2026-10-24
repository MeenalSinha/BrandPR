"""Phase 2 tables: submitted content, review runs, findings and the evidence behind each finding.

Vocabulary
  content submission  the text a creator submitted. Immutable in Phase 2 (later phases add versions).
  review run          one analysis of one submission. A re-review creates a new run; old runs are kept.
  claim               a span of the submission (start/end offsets) that the engine decided needs verification.
  finding             the verdict on one claim in one run. Claim fields live on the finding row so a finding
                      is readable on its own; (review_run_id, claim_index) identifies the claim inside a run.
  finding evidence    a link from a finding to a real approved fact and/or document section, plus a snapshot
                      of what was shown at review time. Phase 3 uses fact_id to find findings affected by a fact change.

Same-brand integrity is enforced by composite foreign keys that include brand_id.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RUN_STATUSES = ("pending", "running", "completed", "completed_limited", "failed")
ANALYSIS_MODES = ("full", "limited")
CLAIM_CATEGORIES = (
    "quantitative", "comparative", "performance", "specification", "pricing", "terminology", "time_sensitive", "general",
)
FINDING_STATUSES = ("supported", "unsupported", "conflicting", "outdated", "uncertain")
SEVERITIES = ("low", "medium", "high")
EVIDENCE_ROLES = ("supports", "conflicts", "outdated", "context", "related_source")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({','.join(repr(v) for v in values)})"


WORKFLOW_STATUSES = ("draft", "in_review", "changes_requested", "approved", "rejected")


class ContentAsset(Base):
    """Phase 4: the logical piece of content (for example "Summer campaign"). Its revisions are immutable ContentSubmissions."""

    __tablename__ = "content_assets"
    __table_args__ = (
        UniqueConstraint("id", "brand_id", name="uq_content_assets_id_brand_id"),
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        Index("ix_content_assets_brand_created", "brand_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ContentSubmission(Base):
    """One immutable revision of a ContentAsset. Only workflow_status (and updated_at) may change; a database trigger enforces this."""

    __tablename__ = "content_submissions"
    __table_args__ = (
        UniqueConstraint("id", "brand_id", name="uq_content_submissions_id_brand_id"),
        UniqueConstraint("id", "asset_id", name="uq_content_submissions_id_asset_id"),
        UniqueConstraint("asset_id", "revision_number", name="uq_content_submissions_asset_revision"),
        UniqueConstraint("parent_submission_id", name="uq_content_submissions_parent"),  # linear history: one child per revision
        ForeignKeyConstraint(
            ["asset_id", "brand_id"], ["content_assets.id", "content_assets.brand_id"],
            name="fk_content_submissions_asset_same_brand", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["parent_submission_id", "asset_id"], ["content_submissions.id", "content_submissions.asset_id"],
            name="fk_content_submissions_parent_same_asset", ondelete="RESTRICT",
        ),
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint("length(btrim(content)) > 0", name="content_not_blank"),
        CheckConstraint("revision_number >= 1", name="revision_positive"),
        CheckConstraint("(parent_submission_id IS NULL) = (revision_number = 1)", name="parent_matches_revision"),
        CheckConstraint(_in("workflow_status", WORKFLOW_STATUSES), name="workflow_status"),
        CheckConstraint("content_hash = encode(sha256(convert_to(content, 'UTF8')), 'hex')", name="content_hash_matches"),
        Index("ix_content_submissions_brand_created", "brand_id", "created_at"),
        Index("ix_content_submissions_asset", "asset_id"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    parent_submission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    workflow_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    change_note: Mapped[str | None] = mapped_column(Text)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ReviewRun(Base):
    __tablename__ = "review_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["content_submission_id", "brand_id"], ["content_submissions.id", "content_submissions.brand_id"],
            name="fk_review_runs_content_same_brand", ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "brand_id", name="uq_review_runs_id_brand_id"),
        CheckConstraint(_in("status", RUN_STATUSES), name="status"),
        CheckConstraint(_in("analysis_mode", ANALYSIS_MODES), name="analysis_mode"),
        CheckConstraint("status NOT IN ('completed','completed_limited','failed') OR completed_at IS NOT NULL", name="finished_has_timestamp"),
        CheckConstraint("status <> 'failed' OR error_code IS NOT NULL", name="failed_has_error_code"),
        CheckConstraint("status <> 'completed' OR analysis_mode = 'full'", name="completed_is_full_mode"),
        CheckConstraint("status <> 'completed_limited' OR analysis_mode = 'limited'", name="limited_is_limited_mode"),
        Index("ix_review_runs_content_started", "content_submission_id", "started_at"),
        Index("ix_review_runs_brand_status", "brand_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content_submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    analysis_mode: Mapped[str] = mapped_column(String(10), nullable=False, server_default="limited")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_name: Mapped[str | None] = mapped_column(String(50))
    model_name: Mapped[str | None] = mapped_column(String(100))
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict | None] = mapped_column(JSONB)


class ReviewFinding(Base):
    __tablename__ = "review_findings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["review_run_id", "brand_id"], ["review_runs.id", "review_runs.brand_id"],
            name="fk_review_findings_run_same_brand", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["matched_fact_id", "brand_id"], ["approved_facts.id", "approved_facts.brand_id"],
            name="fk_review_findings_fact_same_brand", ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "brand_id", name="uq_review_findings_id_brand_id"),
        UniqueConstraint("id", "review_run_id", name="uq_review_findings_id_review_run_id"),
        UniqueConstraint("review_run_id", "claim_index", name="uq_review_findings_review_run_id_claim_index"),
        CheckConstraint(_in("status", FINDING_STATUSES), name="status"),
        CheckConstraint(_in("severity", SEVERITIES), name="severity"),
        CheckConstraint(_in("claim_category", CLAIM_CATEGORIES), name="claim_category"),
        CheckConstraint("method IN ('deterministic','ai_assisted')", name="method"),
        CheckConstraint("extraction_method IN ('deterministic','ai')", name="extraction_method"),
        CheckConstraint("start_offset >= 0 AND end_offset > start_offset", name="offsets_valid"),
        CheckConstraint("length(btrim(claim_text)) > 0", name="claim_not_blank"),
        Index("ix_review_findings_run_status", "review_run_id", "status"),
        Index("ix_review_findings_matched_fact", "matched_fact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    review_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    claim_index: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_category: Mapped[str] = mapped_column(String(30), nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    method: Mapped[str] = mapped_column(String(20), nullable=False, server_default="deterministic")
    extraction_method: Mapped[str] = mapped_column(String(20), nullable=False, server_default="deterministic")
    matched_fact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FindingEvidence(Base):
    """A real record behind a finding. Snapshot columns keep the review readable if the fact later changes."""

    __tablename__ = "finding_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["finding_id", "brand_id"], ["review_findings.id", "review_findings.brand_id"],
            name="fk_finding_evidence_finding_same_brand", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["fact_id", "brand_id"], ["approved_facts.id", "approved_facts.brand_id"],
            name="fk_finding_evidence_fact_same_brand", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_document_id", "brand_id"], ["source_documents.id", "source_documents.brand_id"],
            name="fk_finding_evidence_document_same_brand", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["document_section_id", "source_document_id"], ["document_sections.id", "document_sections.document_id"],
            name="fk_finding_evidence_section_same_document", ondelete="RESTRICT",
        ),
        CheckConstraint(_in("role", EVIDENCE_ROLES), name="role"),
        # Evidence must point at something real: an approved fact or a document section.
        CheckConstraint("fact_id IS NOT NULL OR document_section_id IS NOT NULL", name="points_at_a_record"),
        CheckConstraint("document_section_id IS NULL OR source_document_id IS NOT NULL", name="section_has_document"),
        CheckConstraint("role = 'related_source' OR fact_id IS NOT NULL", name="fact_roles_need_fact"),
        Index("ix_finding_evidence_finding", "finding_id"),
        Index("ix_finding_evidence_fact", "fact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    fact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    document_section_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_title: Mapped[str | None] = mapped_column(String(300))
    source_page: Mapped[int | None] = mapped_column(Integer)
    excerpt: Mapped[str | None] = mapped_column(Text)
    excerpt_verified: Mapped[bool | None] = mapped_column(Boolean)
    fact_name: Mapped[str | None] = mapped_column(String(200))
    fact_value: Mapped[str | None] = mapped_column(Text)
    fact_qualifications: Mapped[str | None] = mapped_column(Text)
    fact_status: Mapped[str | None] = mapped_column(String(20))
    fact_effective_state: Mapped[str | None] = mapped_column(String(20))
    fact_version: Mapped[int | None] = mapped_column(Integer)
    relation_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
