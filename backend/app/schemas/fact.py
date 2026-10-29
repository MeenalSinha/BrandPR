import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FactStatus = Literal["proposed", "active", "rejected", "expired", "retired"]
FactCategory = Literal["product_spec", "approved_claim", "terminology", "legal_disclaimer", "pricing", "general"]
EffectiveState = Literal["current", "pending", "expired", "unapproved", "retired"]
ReviewState = Literal["overdue", "due_soon", "scheduled", "unscheduled", "not_applicable"]
Provenance = Literal["document", "manual"]


def _blank_to_none(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class FactFields(BaseModel):
    """Fields shared by create and update. Cross-field and source rules are enforced in the service."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200, description="What the fact is, e.g. 'Battery life'.")
    value: str = Field(min_length=1, max_length=2000, description="The approved value or wording.")
    category: FactCategory = "general"
    qualifications: str | None = Field(None, max_length=2000, description="Conditions the value depends on.")
    unit: str | None = Field(None, max_length=50)
    owner: str | None = Field(None, max_length=200)
    valid_from: date | None = None
    review_date: date | None = None
    expires_at: date | None = Field(None, description="Last day the fact is valid, inclusive.")
    source_document_id: uuid.UUID | None = None
    source_page: int | None = Field(None, ge=1)
    source_excerpt: str | None = Field(None, max_length=4000)
    source_note: str | None = Field(None, max_length=1000, description="Required when no source document is cited.")

    @field_validator("name", "value")
    @classmethod
    def _required_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Must not be blank.")
        return v

    @field_validator("qualifications", "unit", "owner", "source_excerpt", "source_note")
    @classmethod
    def _optional_text(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class FactCreate(FactFields):
    status: Literal["proposed", "active"] = Field(
        "proposed", description="Facts start as proposed. Creating directly as active is an explicit approval."
    )
    actor: str | None = Field(None, max_length=200, description="Who is making the change (placeholder until auth).")


class FactUpdate(BaseModel):
    """Partial edit. Status cannot be changed here; use the status endpoint."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=200)
    value: str | None = Field(None, min_length=1, max_length=2000)
    category: FactCategory | None = None
    qualifications: str | None = Field(None, max_length=2000)
    unit: str | None = Field(None, max_length=50)
    owner: str | None = Field(None, max_length=200)
    valid_from: date | None = None
    review_date: date | None = None
    expires_at: date | None = None
    source_document_id: uuid.UUID | None = None
    source_page: int | None = Field(None, ge=1)
    source_excerpt: str | None = Field(None, max_length=4000)
    source_note: str | None = Field(None, max_length=1000)
    actor: str | None = Field(None, max_length=200)
    change_reason: str | None = Field(None, max_length=1000)
    expected_version: int | None = Field(None, ge=1, description="Reject the edit if the fact changed since this version.")

    @field_validator("name", "value")
    @classmethod
    def _required_text(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Must not be blank.")
        return v

    @field_validator("qualifications", "unit", "owner", "source_excerpt", "source_note")
    @classmethod
    def _optional_text(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class FactStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: FactStatus
    actor: str | None = Field(None, max_length=200)
    reason: str | None = Field(None, max_length=1000, description="Required for rejected, expired and retired.")
    expected_version: int | None = Field(None, ge=1)


class FactSourceRead(BaseModel):
    document_id: uuid.UUID
    title: str
    filename: str
    source_type: str
    processing_status: str
    page_count: int | None
    archived: bool


class FactRead(BaseModel):
    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    value: str
    category: FactCategory
    qualifications: str | None
    unit: str | None
    status: FactStatus
    effective_state: EffectiveState = Field(description="Status combined with validity dates, evaluated today.")
    review_state: ReviewState
    warnings: list[str]
    source_document_id: uuid.UUID | None
    source_page: int | None
    source_excerpt: str | None
    source_excerpt_verified: bool | None
    source_note: str | None
    provenance: Provenance
    source: FactSourceRead | None
    owner: str | None
    valid_from: date | None
    review_date: date | None
    expires_at: date | None
    approved_by: str | None
    approved_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class FactRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    fact_id: uuid.UUID
    revision_number: int
    action: Literal["created", "updated", "status_changed"]
    changes: dict
    snapshot: dict
    changed_by: str | None
    change_reason: str | None
    created_at: datetime


class FactSummary(BaseModel):
    total: int
    by_effective_state: dict[str, int]
    by_review_state: dict[str, int]
    review_warning_days: int


class FactApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_notes: str | None = Field(None, max_length=1000, description="Reviewer notes justifying approval.")
    actor: str | None = Field(None, max_length=200)
    expected_version: int | None = Field(None, ge=1)


class FactRejectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rejection_reason: str = Field(..., min_length=1, max_length=1000, description="Mandatory reason for rejecting proposal.")
    actor: str | None = Field(None, max_length=200)
    expected_version: int | None = Field(None, ge=1)


class FactApprovalDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    fact_id: uuid.UUID
    revision_number: int
    decision: Literal["approved", "rejected"]
    reviewer_name: str
    reviewer_email: str | None
    notes: str | None
    created_at: datetime


class FactComparisonRead(BaseModel):
    fact_id: uuid.UUID
    current_version: int
    status: FactStatus
    is_material_change: bool
    proposed_by: str | None
    change_reason: str | None
    diff: dict
    current_snapshot: dict
    previous_approved_snapshot: dict | None
    affected_content_count: int
    recent_decisions: list[FactApprovalDecisionRead] = []

