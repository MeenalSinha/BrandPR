"""Phase 5 models: Guideline Rules, Rule Versions, Lint Results, Policy Simulations, and Simulation Results.

All simulation and lint records are persisted separately from historical review records.
Simulations evaluate proposed changes without altering historical review findings or approvals.
"""
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

RULE_STATUSES = ("proposed", "active", "retired")
RULE_SEVERITIES = ("low", "medium", "high")
SIMULATION_STATUSES = ("completed", "failed")
EVALUATION_STATUSES = ("evaluated", "not_evaluable")
OUTCOME_STATUSES = ("pass", "flagged", "not_evaluable")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({','.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())


class GuidelineRule(Base):
    """A brand guideline rule. Extracted rules remain 'proposed' until explicitly approved."""

    __tablename__ = "guideline_rules"
    __table_args__ = (
        UniqueConstraint("id", "brand_id", name="uq_guideline_rules_id_brand_id"),
        ForeignKeyConstraint(["brand_id"], ["brands.id"], name="fk_guideline_rules_brand", ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["source_document_id", "brand_id"],
            ["source_documents.id", "source_documents.brand_id"],
            name="fk_guideline_rules_source_doc_same_brand",
            ondelete="SET NULL",
        ),
        CheckConstraint(_in("status", RULE_STATUSES), name="ck_guideline_rules_status"),
        CheckConstraint(_in("severity", RULE_SEVERITIES), name="ck_guideline_rules_severity"),
        CheckConstraint("length(btrim(title)) > 0", name="ck_guideline_rules_title_not_blank"),
        CheckConstraint("length(btrim(rule_text)) > 0", name="ck_guideline_rules_text_not_blank"),
        Index("ix_guideline_rules_brand_id", "brand_id"),
        Index("ix_guideline_rules_brand_status", "brand_id", "status"),
        Index("ix_guideline_rules_category", "brand_id", "category"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, server_default="general")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, server_default="medium")
    scope: Mapped[str] = mapped_column(String(50), nullable=False, server_default="all")
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    examples: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="proposed")
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GuidelineRuleVersion(Base):
    """Preserves historical versions of a rule and reasons for changes."""

    __tablename__ = "guideline_rule_versions"
    __table_args__ = (
        UniqueConstraint("rule_id", "version_number", name="uq_guideline_rule_versions_rule_ver"),
        ForeignKeyConstraint(["rule_id"], ["guideline_rules.id"], name="fk_guideline_rule_versions_rule", ondelete="CASCADE"),
        Index("ix_guideline_rule_versions_rule_id", "rule_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    examples: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    source_reference: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    change_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GuidelineLintResult(Base):
    """Persisted findings from rule linting (potential ambiguities, missing scope/conditions/examples, or conflicts)."""

    __tablename__ = "guideline_lint_results"
    __table_args__ = (
        ForeignKeyConstraint(["brand_id"], ["brands.id"], name="fk_guideline_lint_results_brand", ondelete="CASCADE"),
        ForeignKeyConstraint(["rule_id"], ["guideline_rules.id"], name="fk_guideline_lint_results_rule", ondelete="CASCADE"),
        ForeignKeyConstraint(["related_rule_id"], ["guideline_rules.id"], name="fk_guideline_lint_results_rel_rule", ondelete="SET NULL"),
        CheckConstraint(_in("severity", RULE_SEVERITIES), name="ck_guideline_lint_results_severity"),
        Index("ix_guideline_lint_results_brand_id", "brand_id"),
        Index("ix_guideline_lint_results_rule_id", "rule_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_category: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, server_default="medium")
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    related_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PolicySimulation(Base):
    """A policy simulation run comparing baseline vs proposed rule against historical content."""

    __tablename__ = "policy_simulations"
    __table_args__ = (
        ForeignKeyConstraint(["brand_id"], ["brands.id"], name="fk_policy_simulations_brand", ondelete="CASCADE"),
        ForeignKeyConstraint(["rule_id"], ["guideline_rules.id"], name="fk_policy_simulations_rule", ondelete="CASCADE"),
        CheckConstraint(_in("status", SIMULATION_STATUSES), name="ck_policy_simulations_status"),
        Index("ix_policy_simulations_brand_id", "brand_id"),
        Index("ix_policy_simulations_rule_id", "rule_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    base_rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    proposed_rule_version: Mapped[int | None] = mapped_column(Integer)
    proposed_rule_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="completed")
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")


class PolicySimulationResult(Base):
    """The simulation outcome for one historical content submission."""

    __tablename__ = "policy_simulation_results"
    __table_args__ = (
        ForeignKeyConstraint(["simulation_id"], ["policy_simulations.id"], name="fk_sim_res_simulation", ondelete="CASCADE"),
        ForeignKeyConstraint(["content_submission_id"], ["content_submissions.id"], name="fk_sim_res_submission", ondelete="CASCADE"),
        ForeignKeyConstraint(["historical_review_run_id"], ["review_runs.id"], name="fk_sim_res_run", ondelete="SET NULL"),
        CheckConstraint(_in("baseline_outcome", OUTCOME_STATUSES), name="ck_sim_res_baseline_outcome"),
        CheckConstraint(_in("simulated_outcome", OUTCOME_STATUSES), name="ck_sim_res_simulated_outcome"),
        CheckConstraint(_in("evaluation_status", EVALUATION_STATUSES), name="ck_sim_res_eval_status"),
        Index("ix_policy_sim_results_sim_id", "simulation_id"),
        Index("ix_policy_sim_results_submission_id", "content_submission_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content_submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    historical_review_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    baseline_outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    simulated_outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="evaluated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
