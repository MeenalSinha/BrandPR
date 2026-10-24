"""Phase 4 tables: the approval workflow, reviewer decisions and fact-change impact resolutions.

All five tables below are APPEND-ONLY (database triggers reject UPDATE and DELETE), so every decision stays inspectable.

  workflow_events                  one row per workflow step of one revision: created, submitted, approved, changes_requested, rejected.
                                   At most one final decision per revision (partial unique index).
  risk_overrides                   a reviewer's reasoned acceptance of one high-risk finding, recorded together with the approval.
  revision_corrections             what the creator did with a finding when writing a revision: accepted / rejected / modified a
                                   suggestion, or corrected by hand. The suggestion text is recorded; the original revision is untouched.
  fact_change_impact_resolutions   how a Phase 3 impact was closed (resolved by an approved revision, or dismissed). The impact row keeps
                                   all of its triggering information; only its status changes, and only together with a row here.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

WORKFLOW_ACTIONS = ("created", "submitted", "approved", "changes_requested", "rejected")
FINAL_ACTIONS = ("approved", "changes_requested", "rejected")
ACTOR_ROLES = ("creator", "reviewer")
CORRECTION_DECISIONS = ("accepted", "rejected", "modified", "manual")
CORRECTION_SOURCES = ("ai", "manual")
RESOLUTION_ACTIONS = ("resolved", "dismissed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({','.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (
        ForeignKeyConstraint(["submission_id", "brand_id"], ["content_submissions.id", "content_submissions.brand_id"], name="fk_workflow_events_submission_same_brand", ondelete="RESTRICT"),
        ForeignKeyConstraint(["submission_id", "asset_id"], ["content_submissions.id", "content_submissions.asset_id"], name="fk_workflow_events_submission_same_asset", ondelete="RESTRICT"),
        ForeignKeyConstraint(["review_run_id", "brand_id"], ["review_runs.id", "review_runs.brand_id"], name="fk_workflow_events_run_same_brand", ondelete="RESTRICT"),
        UniqueConstraint("id", "brand_id", name="uq_workflow_events_id_brand_id"),
        UniqueConstraint("id", "submission_id", name="uq_workflow_events_id_submission_id"),
        UniqueConstraint("submission_id", "action", name="uq_workflow_events_submission_action"),
        CheckConstraint(_in("action", WORKFLOW_ACTIONS), name="action"),
        CheckConstraint(_in("actor_role", ACTOR_ROLES), name="actor_role"),
        CheckConstraint("length(btrim(actor)) > 0", name="actor_not_blank"),
        CheckConstraint("action NOT IN ('changes_requested','rejected') OR length(btrim(coalesce(rationale, ''))) > 0", name="reason_required"),
        CheckConstraint("action NOT IN ('approved','changes_requested','rejected') OR actor_role = 'reviewer'", name="decisions_by_reviewers"),
        Index("uq_workflow_events_one_final_decision", "submission_id", unique=True, postgresql_where=text("action IN ('approved','changes_requested','rejected')")),
        Index("ix_workflow_events_asset_created", "asset_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    review_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")  # e.g. {"finding_ids": [...]} for request_changes
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RiskOverride(Base):
    __tablename__ = "risk_overrides"
    __table_args__ = (
        ForeignKeyConstraint(["event_id", "brand_id"], ["workflow_events.id", "workflow_events.brand_id"], name="fk_risk_overrides_event_same_brand", ondelete="RESTRICT"),
        ForeignKeyConstraint(["finding_id", "review_run_id"], ["review_findings.id", "review_findings.review_run_id"], name="fk_risk_overrides_finding_in_run", ondelete="RESTRICT"),
        ForeignKeyConstraint(["review_run_id", "brand_id"], ["review_runs.id", "review_runs.brand_id"], name="fk_risk_overrides_run_same_brand", ondelete="RESTRICT"),
        UniqueConstraint("event_id", "finding_id", name="uq_risk_overrides_event_finding"),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_not_blank"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    review_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RevisionCorrection(Base):
    __tablename__ = "revision_corrections"
    __table_args__ = (
        ForeignKeyConstraint(["submission_id", "brand_id"], ["content_submissions.id", "content_submissions.brand_id"], name="fk_revision_corrections_submission_same_brand", ondelete="RESTRICT"),
        ForeignKeyConstraint(["finding_id", "brand_id"], ["review_findings.id", "review_findings.brand_id"], name="fk_revision_corrections_finding_same_brand", ondelete="RESTRICT"),
        UniqueConstraint("submission_id", "finding_id", name="uq_revision_corrections_submission_finding"),
        CheckConstraint(_in("decision", CORRECTION_DECISIONS), name="decision"),
        CheckConstraint(_in("source", CORRECTION_SOURCES), name="source"),
        CheckConstraint("source <> 'ai' OR decision <> 'manual'", name="ai_not_manual"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    replacement_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FactChangeImpactResolution(Base):
    __tablename__ = "fact_change_impact_resolutions"
    __table_args__ = (
        ForeignKeyConstraint(["impact_id", "brand_id"], ["fact_change_impacts.id", "fact_change_impacts.brand_id"], name="fk_impact_resolutions_impact_same_brand", ondelete="RESTRICT"),
        ForeignKeyConstraint(["resolving_submission_id", "brand_id"], ["content_submissions.id", "content_submissions.brand_id"], name="fk_impact_resolutions_submission_same_brand", ondelete="RESTRICT"),
        ForeignKeyConstraint(["resolving_review_run_id", "brand_id"], ["review_runs.id", "review_runs.brand_id"], name="fk_impact_resolutions_run_same_brand", ondelete="RESTRICT"),
        ForeignKeyConstraint(["decision_event_id", "resolving_submission_id"], ["workflow_events.id", "workflow_events.submission_id"], name="fk_impact_resolutions_event_for_submission", ondelete="RESTRICT"),
        UniqueConstraint("impact_id", name="uq_impact_resolutions_impact"),  # an impact is closed once; Phase 4 has no re-open
        CheckConstraint(_in("action", RESOLUTION_ACTIONS), name="action"),
        CheckConstraint("action = to_status AND from_status = 'needs_review'", name="transition_consistent"),
        CheckConstraint("length(btrim(rationale)) > 0", name="rationale_not_blank"),
        CheckConstraint(
            "(action = 'resolved') = (resolving_submission_id IS NOT NULL AND resolving_review_run_id IS NOT NULL AND decision_event_id IS NOT NULL)",
            name="resolved_has_evidence",
        ),
        CheckConstraint("actor_role = 'reviewer'", name="reviewer_only"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    impact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    resolving_submission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolving_review_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
