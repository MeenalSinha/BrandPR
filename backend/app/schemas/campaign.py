"""Pydantic schemas for Phase 6 campaigns, campaign assets, audits, comparisons, and release decisions."""
from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CampaignCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    external_reference: Optional[str] = Field(None, max_length=100)
    owner: Optional[str] = Field(None, max_length=200)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("title cannot be blank")
        return s


class CampaignUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    external_reference: Optional[str] = Field(None, max_length=100)
    owner: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = None

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("title cannot be blank")
            return s
        return v



class CampaignAssetAdd(BaseModel):
    asset_id: uuid.UUID
    submission_id: Optional[uuid.UUID] = None
    channel_role: Optional[str] = "landing_page"
    display_order: Optional[int] = 0
    notes: Optional[str] = None


class CampaignAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    brand_id: uuid.UUID
    asset_id: uuid.UUID
    asset_title: Optional[str] = None
    selected_submission_id: uuid.UUID
    revision_number: int = 1
    content_hash: Optional[str] = None
    workflow_status: str = "draft"
    channel_role: str = "landing_page"
    display_order: int = 0
    notes: Optional[str] = None
    added_by: Optional[str] = None
    added_at: datetime


class CampaignAuditFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    audit_id: uuid.UUID
    asset_id: Optional[uuid.UUID] = None
    asset_title: Optional[str] = None
    submission_id: Optional[uuid.UUID] = None
    revision_number: Optional[int] = None
    content_hash: Optional[str] = None
    finding_type: str
    severity: str
    confidence: str
    claim_text: Optional[str] = None
    explanation: str
    recommended_action: str
    requires_human_review: bool = False

    related_asset_id: Optional[uuid.UUID] = None
    related_asset_title: Optional[str] = None
    related_submission_id: Optional[uuid.UUID] = None
    related_fact_id: Optional[uuid.UUID] = None
    related_fact_version: Optional[int] = None
    related_rule_id: Optional[uuid.UUID] = None
    related_rule_version: Optional[int] = None
    related_impact_id: Optional[uuid.UUID] = None
    related_review_finding_id: Optional[uuid.UUID] = None

    source_document_id: Optional[uuid.UUID] = None
    source_page: Optional[int] = None
    source_excerpt: Optional[str] = None
    created_at: datetime


class CampaignAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    audit_number: int
    status: str
    readiness_outcome: str
    is_stale: bool = False
    stale_reason: Optional[str] = None
    asset_count: int = 0
    blocker_count: int = 0
    warning_count: int = 0
    review_required_count: int = 0
    passed_checks_count: int = 0
    summary: Optional[dict[str, Any]] = None
    created_by: Optional[str] = None
    created_at: datetime
    findings: list[CampaignAuditFindingOut] = []


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    description: Optional[str] = None
    external_reference: Optional[str] = None
    owner: Optional[str] = None
    status: str
    release_notes: Optional[str] = None
    released_at: Optional[datetime] = None
    released_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    asset_count: int = 0
    latest_audit_id: Optional[uuid.UUID] = None
    latest_readiness: Optional[str] = None
    latest_audit_stale: bool = False
    blocker_count: int = 0
    warning_count: int = 0
    assets: list[CampaignAssetOut] = []


class AuditComparisonOut(BaseModel):
    audit_id: uuid.UUID
    previous_audit_id: uuid.UUID
    new_findings: list[CampaignAuditFindingOut] = []
    persistent_findings: list[CampaignAuditFindingOut] = []
    resolved_findings: list[CampaignAuditFindingOut] = []
    unevaluable_findings: list[CampaignAuditFindingOut] = []
    summary: dict[str, Any] = {}


class CampaignReleaseRequest(BaseModel):
    release_notes: Optional[str] = None


class CampaignReleaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision_id: uuid.UUID
    campaign_id: uuid.UUID
    audit_id: uuid.UUID
    decision: str
    actor_name: str
    actor_role: str
    release_notes: Optional[str] = None
    released_at: datetime


class ReleaseEvaluationOut(BaseModel):
    campaign_id: uuid.UUID
    status: str
    is_stale: bool
    can_release: bool
    blocker_count: int
    warning_count: int
    review_required_count: int
    blockers: list[str] = []
    audit_id: Optional[uuid.UUID] = None
    readiness_outcome: Optional[str] = None
