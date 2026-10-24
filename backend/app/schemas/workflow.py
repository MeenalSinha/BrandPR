"""Phase 4 API contracts: revisions, corrections, approval workflow and impact resolution."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.review import AnalysisMode, FindingRead, ReviewRunBrief, RunStatus

WorkflowStatus = Literal["draft", "in_review", "changes_requested", "approved", "rejected"]
WorkflowAction = Literal["created", "submitted", "approved", "changes_requested", "rejected"]
DecisionAction = Literal["approve", "request_changes", "reject"]
ActorRole = Literal["creator", "reviewer"]
CorrectionDecision = Literal["accepted", "rejected", "modified", "manual"]
CorrectionSource = Literal["ai", "manual"]
ReadinessState = Literal["no_review", "review_in_progress", "review_failed", "content_mismatch", "ready"]


def _strip(v: str | None) -> str | None:
    return (v or "").strip() or None


# ------------------------------------------------------------------ revisions
class CorrectionIn(BaseModel):
    """What the creator did with one finding while writing this revision. A suggestion is only a record here; it never edits content."""

    model_config = ConfigDict(extra="forbid")
    finding_id: uuid.UUID
    decision: CorrectionDecision
    source: CorrectionSource = "manual"
    original_text: str = Field(min_length=1, max_length=5000)
    replacement_text: str | None = Field(None, max_length=5000, description="The suggested or written replacement; null when a suggestion was rejected.")

    @field_validator("replacement_text")
    @classmethod
    def _repl(cls, v: str | None) -> str | None:
        return v if v is None or v.strip() else None


class RevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, min_length=1, max_length=300, description="New title; omit to keep the previous one.")
    content: str = Field(min_length=1, description="The full corrected text. Stored exactly as sent so claim offsets stay valid.")
    change_note: str | None = Field(None, max_length=1000, description="Why this revision was made.")
    corrections: list[CorrectionIn] = Field(default_factory=list, max_length=200)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str | None) -> str | None:
        return _strip(v)

    @field_validator("content")
    @classmethod
    def _content(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Must not be blank.")
        return v

    @field_validator("change_note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        return _strip(v)


class DecisionBrief(BaseModel):
    id: uuid.UUID
    action: WorkflowAction
    actor: str
    actor_role: ActorRole
    rationale: str | None
    review_run_id: uuid.UUID | None
    created_at: datetime


class RevisionRead(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    brand_id: uuid.UUID
    revision_number: int
    parent_submission_id: uuid.UUID | None
    title: str
    created_by: str | None
    created_at: datetime
    change_note: str | None
    char_count: int
    content_hash: str
    workflow_status: WorkflowStatus
    is_latest: bool
    review_count: int
    latest_review: ReviewRunBrief | None
    decision: DecisionBrief | None = Field(description="The final reviewer decision on this revision, if any.")
    correction_count: int
    open_impact_count: int = Field(description="Open fact-change impacts recorded against exactly this revision.")


class RevisionHistory(BaseModel):
    asset_id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    latest_revision_id: uuid.UUID
    items: list[RevisionRead] = Field(description="Oldest first.")


class CorrectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    finding_id: uuid.UUID
    decision: CorrectionDecision
    source: CorrectionSource
    original_text: str
    replacement_text: str | None
    created_at: datetime


# ------------------------------------------------------------------ suggestions
class SuggestionRead(BaseModel):
    """A proposal only. It is not stored and never applied; the creator must accept it, edit it or reject it."""

    finding_id: uuid.UUID
    review_run_id: uuid.UUID
    start_offset: int
    end_offset: int
    original_text: str
    replacement_text: str | None = Field(description="Null when the model could not propose a safe replacement.")
    rationale: str | None
    cannot_suggest_reason: str | None
    evidence_fact_ids: list[uuid.UUID]
    warnings: list[str]
    requires_human_review: Literal[True] = True
    source: Literal["ai"] = "ai"
    provider_name: str | None
    model_name: str | None


# ------------------------------------------------------------------ workflow
class OverrideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("A reason is required.")
        return v


class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: DecisionAction
    review_run_id: uuid.UUID | None = Field(None, description="The review run the reviewer looked at. Required to approve; must be the latest run.")
    rationale: str | None = Field(None, max_length=4000, description="Required to request changes or reject.")
    finding_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200, description="Findings that motivate a change request or rejection.")
    overrides: list[OverrideIn] = Field(default_factory=list, max_length=200, description="Reasoned acceptance of high-risk findings (approve only).")
    resolve_impact_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50, description="Open impacts of this asset to resolve in the same transaction (approve only).")
    resolution_rationale: str | None = Field(None, max_length=4000, description="Rationale recorded for each impact in resolve_impact_ids.")

    @field_validator("rationale", "resolution_rationale")
    @classmethod
    def _r(cls, v: str | None) -> str | None:
        return _strip(v)


class OverrideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_id: uuid.UUID
    review_run_id: uuid.UUID
    finding_id: uuid.UUID
    reason: str
    actor: str
    created_at: datetime


class WorkflowEventRead(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    revision_number: int
    action: WorkflowAction
    from_status: WorkflowStatus | None
    to_status: WorkflowStatus
    actor: str
    actor_role: ActorRole
    rationale: str | None
    review_run_id: uuid.UUID | None
    finding_ids: list[uuid.UUID]
    created_at: datetime


class BlockingFinding(BaseModel):
    finding_id: uuid.UUID
    claim_text: str
    status: str
    severity: str
    explanation: str
    overridden: bool = False


class Readiness(BaseModel):
    state: ReadinessState
    ready_for_decision: bool = Field(description="True only when the latest review of this exact text finished (fully or in limited mode).")
    reasons: list[str]
    review: ReviewRunBrief | None
    review_status: RunStatus | None
    analysis_mode: AnalysisMode | None
    limited_mode: bool
    limitations: list[str]
    counts: dict[str, int]
    blocking_findings: list[BlockingFinding] = Field(description="High-risk findings that are not 'supported'. Approval needs a recorded override for each.")


class WorkflowRead(BaseModel):
    submission_id: uuid.UUID
    asset_id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    revision_number: int
    is_latest: bool
    created_by: str | None
    workflow_status: WorkflowStatus
    readiness: Readiness
    events: list[WorkflowEventRead] = Field(description="Every workflow event of every revision of the asset, oldest first.")
    overrides: list[OverrideRead]
    corrections: list[CorrectionRead]
    available_actions: list[str] = Field(description="What the calling actor may do now, computed by the backend.")
    approved_run_id: uuid.UUID | None


# ------------------------------------------------------------------ impact resolution
class ImpactResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolving_submission_id: uuid.UUID = Field(description="The APPROVED later revision that corrected the content.")
    rationale: str = Field(min_length=3, max_length=4000)

    @field_validator("rationale")
    @classmethod
    def _r(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("A rationale is required.")
        return v


class ImpactDismissIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rationale: str = Field(min_length=3, max_length=4000)

    @field_validator("rationale")
    @classmethod
    def _r(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("A rationale is required.")
        return v


class ImpactResolutionRead(BaseModel):
    id: uuid.UUID
    impact_id: uuid.UUID
    action: Literal["resolved", "dismissed"]
    from_status: str
    to_status: str
    actor: str
    actor_role: ActorRole
    rationale: str
    resolving_submission_id: uuid.UUID | None
    resolving_revision_number: int | None
    resolving_review_run_id: uuid.UUID | None
    decision_event_id: uuid.UUID | None
    created_at: datetime


class ImpactHistory(BaseModel):
    impact_id: uuid.UUID
    status: Literal["needs_review", "resolved", "dismissed"]
    detected_at: datetime
    affected_submission_id: uuid.UUID
    affected_revision_number: int
    asset_id: uuid.UUID
    latest_revision_id: uuid.UUID
    latest_revision_number: int
    resolutions: list[ImpactResolutionRead]
    revisions: list[RevisionRead]
    events: list[WorkflowEventRead]


class FindingDetail(BaseModel):
    """One finding with the claim's surrounding sentence, for the correction editor."""

    finding: FindingRead
    revision_number: int
    submission_id: uuid.UUID
