"""Phase 3 API contracts: fact-change impacts (content that needs another review because a fact changed or expired)."""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.fact import EffectiveState, FactRead, FactStatus
from app.schemas.review import FindingRead, ReviewRunBrief

ImpactTrigger = Literal["fact_revision", "fact_expiry"]
ImpactChangeType = Literal["material_edit", "no_longer_approved", "validity_changed", "expired"]
ImpactStatus = Literal["needs_review", "resolved", "dismissed"]
MatchBasis = Literal["evidence", "matched_fact"]


class ImpactFactBrief(BaseModel):
    """The changed fact as it is NOW. The state at review time is in previous_snapshot / the finding evidence."""

    id: uuid.UUID
    name: str
    status: FactStatus
    effective_state: EffectiveState
    version: int
    value: str
    unit: str | None


class ImpactContentBrief(BaseModel):
    """The exact revision the impact was recorded against (never retargeted), plus where the asset stands now."""

    id: uuid.UUID
    title: str
    created_at: datetime
    asset_id: uuid.UUID
    revision_number: int
    latest_revision_id: uuid.UUID
    latest_revision_number: int
    latest_revision_status: Literal["draft", "in_review", "changes_requested", "approved", "rejected"]


class ImpactResolutionBrief(BaseModel):
    action: Literal["resolved", "dismissed"]
    actor: str
    rationale: str
    created_at: datetime
    resolving_submission_id: uuid.UUID | None
    resolving_revision_number: int | None
    resolving_review_run_id: uuid.UUID | None


class ImpactRead(BaseModel):
    id: uuid.UUID
    brand_id: uuid.UUID
    status: ImpactStatus
    trigger_type: ImpactTrigger
    change_type: ImpactChangeType
    headline: str = Field(description="One-line description of the change, written when the impact was recorded.")
    reason: str = Field(description="Why this content is flagged for another review.")
    detected_at: datetime
    fact: ImpactFactBrief
    previous_fact_version: int = Field(description="Version of the fact the affected review relied on.")
    current_fact_version: int = Field(description="Version of the fact after the change (or at expiry detection).")
    previous_value: str = Field(description="Value (with unit) of the fact version the review relied on, from the revision history.")
    current_value: str = Field(description="Value (with unit) of the fact now.")
    content: ImpactContentBrief
    source_review_run_id: uuid.UUID
    source_review_started_at: datetime
    affected_claim: str | None = Field(description="Text of the first claim in the content that relied on the fact.")
    affected_finding_count: int
    latest_review_started_at: datetime | None = Field(description="Start of the content's most recent completed review.")
    reviewed_since_detection: bool = Field(
        description="True when the content has a completed review that started after this impact was recorded. "
                    "Informational only; an impact is never closed automatically."
    )
    resolution: ImpactResolutionBrief | None = Field(None, description="How the impact was closed; null while it needs review.")


class ImpactRevisionRead(BaseModel):
    id: uuid.UUID
    revision_number: int
    action: Literal["created", "updated", "status_changed"]
    changes: dict[str, Any]
    changed_by: str | None
    change_reason: str | None
    created_at: datetime


class ImpactFindingRead(BaseModel):
    """A historical finding exactly as saved at review time, plus why it is linked to the changed fact."""

    finding: FindingRead
    match_basis: MatchBasis = Field(description="'evidence' = a stored evidence row cites the fact; 'matched_fact' = the finding names the fact without a versioned evidence row.")
    relied_fact_version: int
    review_run: ReviewRunBrief


class ImpactDetail(ImpactRead):
    change_summary: dict[str, Any] = Field(description="Stored at detection time: changed fields, effective states before and after.")
    previous_snapshot: dict[str, Any] = Field(description="The fact as recorded in the revision history at the version the review relied on.")
    new_snapshot: dict[str, Any] = Field(description="The fact as recorded when the triggering change happened.")
    current_fact: FactRead
    trigger_revision: ImpactRevisionRead | None
    findings: list[ImpactFindingRead]


class ImpactSummary(BaseModel):
    open_impacts: int
    resolved_impacts: int = 0
    dismissed_impacts: int = 0
    total_impacts: int = 0
    facts_with_changes: int = Field(description="Distinct facts with at least one open impact.")
    content_needing_review: int = Field(description="Distinct content items with at least one open impact.")
    expiry_affected_content: int = Field(description="Distinct content items flagged because a fact's expiry date passed.")
    revision_affected_content: int = Field(description="Distinct content items flagged because a fact was edited or its status changed.")
