"""Phase 3 tables: persistent records of content whose earlier review relied on a fact that later changed or expired.

Vocabulary
  impact          one content submission that needs another review because of ONE fact-change event.
  event           either a material fact revision (trigger_type 'fact_revision', identified by the fact_revisions row)
                  or the lapse of a fact's expiry date (trigger_type 'fact_expiry', identified by fact id + expiry date).
  affected finding  a historical review finding that relied on the fact. Linked through fact_change_impact_findings.

An impact never edits the content, the review run, the findings or the evidence. It only points at them, so the
original review stays an accurate record of what was approved when it ran.

Duplicate prevention is enforced by the database:
  * UNIQUE (trigger_key, content_submission_id): one impact per content item per event.
  * UNIQUE (finding_id, fact_id) on the link table: a historical finding is attributed to the first event that
    invalidated the fact it relied on, so later events do not re-flag the same finding.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

IMPACT_TRIGGERS = ("fact_revision", "fact_expiry")
IMPACT_CHANGE_TYPES = ("material_edit", "no_longer_approved", "validity_changed", "expired")
# Phase 3 only creates needs_review. Phase 4 closes an impact as resolved or dismissed, only through fact_change_impact_resolutions.
IMPACT_STATUSES = ("needs_review", "resolved", "dismissed")
IMPACT_MATCH_BASES = ("evidence", "matched_fact")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({','.join(repr(v) for v in values)})"


class FactChangeImpact(Base):
    __tablename__ = "fact_change_impacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["fact_id", "brand_id"], ["approved_facts.id", "approved_facts.brand_id"],
            name="fk_fact_change_impacts_fact_same_brand", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["content_submission_id", "brand_id"], ["content_submissions.id", "content_submissions.brand_id"],
            name="fk_fact_change_impacts_content_same_brand", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_review_run_id", "brand_id"], ["review_runs.id", "review_runs.brand_id"],
            name="fk_fact_change_impacts_run_same_brand", ondelete="RESTRICT",
        ),
        # The triggering revision must belong to the same fact.
        ForeignKeyConstraint(
            ["fact_revision_id", "fact_id"], ["fact_revisions.id", "fact_revisions.fact_id"],
            name="fk_fact_change_impacts_revision_same_fact", ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "brand_id", name="uq_fact_change_impacts_id_brand_id"),
        UniqueConstraint("trigger_key", "content_submission_id", name="uq_fact_change_impacts_event_content"),
        CheckConstraint(_in("trigger_type", IMPACT_TRIGGERS), name="trigger_type"),
        CheckConstraint(_in("change_type", IMPACT_CHANGE_TYPES), name="change_type"),
        CheckConstraint(_in("status", IMPACT_STATUSES), name="status"),
        CheckConstraint("(trigger_type = 'fact_revision') = (fact_revision_id IS NOT NULL)", name="revision_matches_trigger"),
        CheckConstraint("previous_fact_version >= 1 AND current_fact_version >= previous_fact_version", name="versions_ordered"),
        CheckConstraint("length(btrim(trigger_key)) > 0", name="trigger_key_not_blank"),
        Index("ix_fact_change_impacts_brand_status", "brand_id", "status"),
        Index("ix_fact_change_impacts_brand_created", "brand_id", "created_at"),
        Index("ix_fact_change_impacts_fact", "fact_id"),
        Index("ix_fact_change_impacts_content", "content_submission_id"),
        Index("ix_fact_change_impacts_revision", "fact_revision_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id", ondelete="RESTRICT"), nullable=False)
    fact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content_submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fact_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_key: Mapped[str] = mapped_column(String(200), nullable=False)
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_fact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_fact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_review_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    change_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="needs_review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FactChangeImpactFinding(Base):
    """Which historical findings (and evidence rows) made a content item depend on the changed fact."""

    __tablename__ = "fact_change_impact_findings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["impact_id", "brand_id"], ["fact_change_impacts.id", "fact_change_impacts.brand_id"],
            name="fk_fact_change_impact_findings_impact_same_brand", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["finding_id", "brand_id"], ["review_findings.id", "review_findings.brand_id"],
            name="fk_fact_change_impact_findings_finding_same_brand", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["fact_id", "brand_id"], ["approved_facts.id", "approved_facts.brand_id"],
            name="fk_fact_change_impact_findings_fact_same_brand", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["review_run_id", "brand_id"], ["review_runs.id", "review_runs.brand_id"],
            name="fk_fact_change_impact_findings_run_same_brand", ondelete="RESTRICT",
        ),
        UniqueConstraint("finding_id", "fact_id", name="uq_fact_change_impact_findings_finding_fact"),
        UniqueConstraint("impact_id", "finding_id", name="uq_fact_change_impact_findings_impact_finding"),
        CheckConstraint(_in("match_basis", IMPACT_MATCH_BASES), name="match_basis"),
        CheckConstraint("relied_fact_version >= 1", name="relied_version_positive"),
        CheckConstraint("(match_basis = 'evidence') = (evidence_id IS NOT NULL)", name="evidence_matches_basis"),
        Index("ix_fact_change_impact_findings_impact", "impact_id"),
        Index("ix_fact_change_impact_findings_fact", "fact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    impact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    review_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("finding_evidence.id", ondelete="RESTRICT"))
    match_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    relied_fact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
