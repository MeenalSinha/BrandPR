import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ClaimCategory = Literal[
    "quantitative", "comparative", "performance", "specification", "pricing", "terminology", "time_sensitive", "general"
]
FindingStatus = Literal["supported", "unsupported", "conflicting", "outdated", "uncertain"]
Severity = Literal["low", "medium", "high"]
RunStatus = Literal["pending", "running", "completed", "completed_limited", "failed"]
AnalysisMode = Literal["full", "limited"]
EvidenceRole = Literal["supports", "conflicts", "outdated", "context", "related_source"]
AnalysisMethod = Literal["deterministic", "ai_assisted"]


# ------------------------------------------------------------------ content
class ContentCreate(BaseModel):
    """Length limits that depend on configuration (MAX_CONTENT_CHARS) are enforced in the service."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300, description="Short name for the draft.")
    content: str = Field(min_length=1, description="The marketing text to review.")
    submitted_by: str | None = Field(None, max_length=200, description="Placeholder until sign-in exists.")

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Must not be blank.")
        return v

    @field_validator("content")
    @classmethod
    def _content(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Must not be blank.")
        return v  # stored exactly as submitted so claim offsets stay valid

    @field_validator("submitted_by")
    @classmethod
    def _by(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


class ReviewRunBrief(BaseModel):
    id: uuid.UUID
    status: RunStatus
    analysis_mode: AnalysisMode
    started_at: datetime
    completed_at: datetime | None
    counts: dict[str, int] = Field(description="Findings per status for this run.")


WorkflowStatus = Literal["draft", "in_review", "changes_requested", "approved", "rejected"]


class ContentRead(BaseModel):
    id: uuid.UUID
    brand_id: uuid.UUID
    asset_id: uuid.UUID
    revision_number: int
    parent_submission_id: uuid.UUID | None
    workflow_status: WorkflowStatus
    is_latest: bool = Field(description="False once a newer revision of the same asset exists.")
    change_note: str | None
    title: str
    content: str
    content_hash: str
    submitted_by: str | None
    created_at: datetime
    updated_at: datetime
    review_count: int = 0
    latest_review: ReviewRunBrief | None = None


class ContentSummary(BaseModel):
    """List item: no body text, so lists stay small."""

    id: uuid.UUID
    brand_id: uuid.UUID
    asset_id: uuid.UUID
    revision_number: int
    workflow_status: WorkflowStatus
    is_latest: bool
    title: str
    char_count: int
    submitted_by: str | None
    created_at: datetime
    review_count: int
    latest_review: ReviewRunBrief | None


# ------------------------------------------------------------------ reviews
class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_by: str | None = Field(None, max_length=200)


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: EvidenceRole
    fact_id: uuid.UUID | None
    source_document_id: uuid.UUID | None
    document_section_id: uuid.UUID | None
    source_title: str | None
    source_page: int | None
    excerpt: str | None = Field(description="Passage as saved at review time. Verified against the stored source text when excerpt_verified is true.")
    excerpt_verified: bool | None
    fact_name: str | None
    fact_value: str | None
    fact_qualifications: str | None
    fact_status: str | None
    fact_effective_state: str | None
    fact_version: int | None
    relation_note: str | None


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    review_run_id: uuid.UUID
    claim_index: int
    claim_text: str
    claim_category: ClaimCategory
    start_offset: int
    end_offset: int
    status: FindingStatus
    severity: Severity
    explanation: str
    recommended_action: str | None
    requires_human_review: bool
    method: AnalysisMethod
    extraction_method: Literal["deterministic", "ai"]
    matched_fact_id: uuid.UUID | None
    evidence: list[EvidenceRead]
    created_at: datetime


class ReviewRunRead(BaseModel):
    id: uuid.UUID
    brand_id: uuid.UUID
    content_submission_id: uuid.UUID
    status: RunStatus
    analysis_mode: AnalysisMode
    content_hash: str
    requested_by: str | None
    started_at: datetime
    completed_at: datetime | None
    provider_name: str | None
    model_name: str | None
    error_code: str | None
    error_message: str | None
    counts: dict[str, int]
    limitations: list[str] = Field(description="What this run could not do (for example no AI provider configured).")
    notes: list[str] = Field(description="Non-fatal observations such as discarded model output.")
    total_findings: int
    findings: list[FindingRead] | None = Field(None, description="Included when a run is created; use the findings endpoint to page.")
