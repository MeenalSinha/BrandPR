import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field


class GuidelineRuleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    rule_text: str = Field(min_length=1, max_length=10000)
    category: str = Field(default="general", max_length=50)
    severity: str = Field(default="medium", max_length=20)
    scope: str = Field(default="all", max_length=50)
    conditions: dict[str, Any] | None = None
    examples: list[dict[str, Any]] | None = None
    source_document_id: uuid.UUID | None = None
    source_page: int | None = None
    source_excerpt: str | None = None
    owner: str | None = None
    status: str = Field(default="proposed", max_length=20)


class GuidelineRuleUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    rule_text: str | None = None
    category: str | None = None
    severity: str | None = None
    scope: str | None = None
    conditions: dict[str, Any] | None = None
    examples: list[dict[str, Any]] | None = None
    source_document_id: uuid.UUID | None = None
    source_page: int | None = None
    source_excerpt: str | None = None
    owner: str | None = None
    status: str | None = None
    change_reason: str | None = None


class GuidelineRuleVersionCreate(BaseModel):
    rule_text: str = Field(min_length=1, max_length=10000)
    conditions: dict[str, Any] | None = None
    examples: list[dict[str, Any]] | None = None
    source_reference: dict[str, Any] | None = None
    change_reason: str | None = None


class GuidelineRuleVersionOut(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    version_number: int
    rule_text: str
    conditions: dict[str, Any] | None = None
    examples: list[dict[str, Any]] | None = None
    source_reference: dict[str, Any] | None = None
    change_reason: str | None = None
    created_by: str
    created_at: datetime


class GuidelineRuleOut(BaseModel):
    id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    description: str | None = None
    rule_text: str
    category: str
    severity: str
    scope: str
    conditions: dict[str, Any] | None = None
    examples: list[dict[str, Any]] | None = None
    status: str
    source_document_id: uuid.UUID | None = None
    source_page: int | None = None
    source_excerpt: str | None = None
    owner: str | None = None
    created_by: str
    current_version: int
    created_at: datetime
    updated_at: datetime
    versions: list[GuidelineRuleVersionOut] = []


class GuidelineRuleListOut(BaseModel):
    items: list[GuidelineRuleOut]
    total: int
    active_count: int
    proposed_count: int
    retired_count: int


class GuidelineExtractRequest(BaseModel):
    document_id: uuid.UUID | None = None
    source_document_id: uuid.UUID | None = None

    @property
    def target_document_id(self) -> uuid.UUID:
        doc = self.document_id or self.source_document_id
        if not doc:
            raise ValueError("document_id or source_document_id is required.")
        return doc


class GuidelineExtractResponse(BaseModel):
    extracted_rules: list[GuidelineRuleOut]
    total_extracted: int
    source_document_id: uuid.UUID
    notice: str = "Extracted rules are created in 'proposed' status and require explicit reviewer approval to become active."

    @computed_field
    @property
    def extracted_count(self) -> int:
        return self.total_extracted

    @computed_field
    @property
    def proposed_rules(self) -> list[GuidelineRuleOut]:
        return self.extracted_rules


class GuidelineLintIssueOut(BaseModel):
    id: uuid.UUID | None = None
    rule_id: uuid.UUID
    rule_title: str
    rule_version: int
    issue_category: str
    severity: str
    explanation: str
    related_rule_id: uuid.UUID | None = None
    related_rule_title: str | None = None
    suggested_action: str
    requires_human_review: bool = True
    created_at: datetime | None = None


class GuidelineLintResponse(BaseModel):
    brand_id: uuid.UUID
    total_issues: int
    issues: list[GuidelineLintIssueOut]
    summary: dict[str, int]
    notice: str = "Lint results highlight potential ambiguities or conflicts and require human assessment before modifying rules."


class PolicySimulationCreate(BaseModel):
    rule_id: uuid.UUID
    proposed_rule: dict[str, Any] | None = None
    proposed_rule_text: str | None = None
    proposed_conditions: dict[str, Any] | None = None
    content_submission_ids: list[uuid.UUID] | None = None


class PolicySimulationResultOut(BaseModel):
    id: uuid.UUID
    simulation_id: uuid.UUID
    content_submission_id: uuid.UUID
    content_title: str | None = None
    content_snippet: str | None = None
    historical_review_run_id: uuid.UUID | None = None
    baseline_outcome: str
    simulated_outcome: str
    changed_findings: list[dict[str, Any]] = []
    explanation: str
    evaluation_status: str
    created_at: datetime


class PolicySimulationOut(BaseModel):
    id: uuid.UUID
    brand_id: uuid.UUID
    rule_id: uuid.UUID
    rule_title: str | None = None
    base_rule_version: int
    proposed_rule_version: int | None = None
    proposed_rule_snapshot: dict[str, Any]
    status: str
    created_by: str
    created_at: datetime
    completed_at: datetime | None = None
    summary: dict[str, Any]
    results: list[PolicySimulationResultOut] = []
    notice: str = "Simulations evaluate proposed changes against historical content without modifying past review records or activating the rule."


class PolicySimulationListOut(BaseModel):
    items: list[PolicySimulationOut]
    total: int


class GovernanceInsightsOut(BaseModel):
    brand_id: uuid.UUID
    period: str
    overview: dict[str, Any]
    finding_patterns: dict[str, Any]
    repeated_issues: list[dict[str, Any]]
    governance_recommendations: list[dict[str, Any]]
    simulations_summary: dict[str, Any]
