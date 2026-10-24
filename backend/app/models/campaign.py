"""Phase 6 models: Campaigns, CampaignAssets, CampaignAudits, Findings, and ReleaseDecisions."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CAMPAIGN_STATUSES = ("draft", "in_review", "blocked", "needs_review", "ready_for_release", "released", "archived")
CHANNEL_ROLES = ("landing_page", "advertisement", "email", "social_post", "product_description", "press_release", "other")
AUDIT_STATUSES = ("completed", "failed")
READINESS_OUTCOMES = ("blocked", "needs_review", "ready_for_release")
FINDING_TYPES = (
    "fact_contradiction", "outdated_fact", "open_impact", "unreviewed_content",
    "failed_review", "incomplete_approval", "guideline_violation",
    "cross_asset_inconsistency", "human_review_required", "stale_review",
)
SEVERITIES = ("hard_blocker", "warning", "info")
CONFIDENCE_LEVELS = ("confirmed", "potential", "uncertain", "not_evaluable")
DECISION_TYPES = ("released", "revoked")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({','.join(repr(v) for v in values)})"


class Campaign(Base):
    """A collection of marketing assets governed and audited together."""

    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("id", "brand_id", name="uq_campaigns_id_brand_id"),
        CheckConstraint("length(btrim(title)) > 0", name="ck_campaigns_title_not_blank"),
        CheckConstraint(_in("status", CAMPAIGN_STATUSES), name="ck_campaigns_status"),
        Index("ix_campaigns_brand_created", "brand_id", "created_at"),
        Index("ix_campaigns_brand_status", "brand_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    external_reference: Mapped[str | None] = mapped_column(String(100))
    owner: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="draft")
    release_notes: Mapped[str | None] = mapped_column(Text)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CampaignAsset(Base):
    """Membership of a ContentAsset in a Campaign, pinning a selected revision."""

    __tablename__ = "campaign_assets"
    __table_args__ = (
        UniqueConstraint("campaign_id", "asset_id", name="uq_campaign_assets_campaign_asset"),
        ForeignKeyConstraint(
            ["campaign_id", "brand_id"], ["campaigns.id", "campaigns.brand_id"],
            name="fk_campaign_assets_campaign_same_brand", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["asset_id", "brand_id"], ["content_assets.id", "content_assets.brand_id"],
            name="fk_campaign_assets_asset_same_brand", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["selected_submission_id", "asset_id"], ["content_submissions.id", "content_submissions.asset_id"],
            name="fk_campaign_assets_submission_same_asset", ondelete="RESTRICT",
        ),
        CheckConstraint(_in("channel_role", CHANNEL_ROLES), name="ck_campaign_assets_channel_role"),
        Index("ix_campaign_assets_campaign_order", "campaign_id", "display_order"),
        Index("ix_campaign_assets_asset", "asset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    selected_submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel_role: Mapped[str] = mapped_column(String(50), nullable=False, server_default="landing_page")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)
    added_by: Mapped[str | None] = mapped_column(String(200))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CampaignAudit(Base):
    """A point-in-time audit of all selected assets in a campaign."""

    __tablename__ = "campaign_audits"
    __table_args__ = (
        UniqueConstraint("campaign_id", "audit_number", name="uq_campaign_audits_campaign_number"),
        CheckConstraint(_in("status", AUDIT_STATUSES), name="ck_campaign_audits_status"),
        CheckConstraint(_in("readiness_outcome", READINESS_OUTCOMES), name="ck_campaign_audits_readiness_outcome"),
        Index("ix_campaign_audits_campaign_created", "campaign_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    audit_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="completed")
    readiness_outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    stale_reason: Mapped[str | None] = mapped_column(Text)
    asset_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    blocker_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    review_required_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    passed_checks_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CampaignAuditFinding(Base):
    """A finding identified during a campaign-wide audit."""

    __tablename__ = "campaign_audit_findings"
    __table_args__ = (
        CheckConstraint(_in("finding_type", FINDING_TYPES), name="ck_campaign_audit_findings_type"),
        CheckConstraint(_in("severity", SEVERITIES), name="ck_campaign_audit_findings_severity"),
        CheckConstraint(_in("confidence", CONFIDENCE_LEVELS), name="ck_campaign_audit_findings_confidence"),
        Index("ix_campaign_audit_findings_audit_sev", "audit_id", "severity"),
        Index("ix_campaign_audit_findings_audit_type", "audit_id", "finding_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    audit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaign_audits.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("content_assets.id", ondelete="SET NULL"))
    submission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("content_submissions.id", ondelete="SET NULL"))
    revision_number: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    claim_text: Mapped[str | None] = mapped_column(String(500))
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    related_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    related_submission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    related_fact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    related_fact_version: Mapped[int | None] = mapped_column(Integer)
    related_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    related_rule_version: Mapped[int | None] = mapped_column(Integer)
    related_impact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    related_review_finding_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CampaignReleaseDecision(Base):
    """An audited human decision to release a campaign."""

    __tablename__ = "campaign_release_decisions"
    __table_args__ = (
        CheckConstraint(_in("decision", DECISION_TYPES), name="ck_campaign_release_decisions_decision"),
        Index("ix_campaign_release_decisions_campaign", "campaign_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    audit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaign_audits.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False, server_default="released")
    actor_name: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    release_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
