import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentActor, DbSession, Limit, Offset, OptionalActor, verify_brand_access
from app.schemas.common import ERROR_RESPONSES
from app.schemas.guideline import (
    GuidelineExtractRequest, GuidelineExtractResponse, GuidelineLintIssueOut, GuidelineLintResponse,
    GuidelineRuleCreate, GuidelineRuleListOut, GuidelineRuleOut, GuidelineRuleUpdate, GuidelineRuleVersionCreate,
    GuidelineRuleVersionOut, PolicySimulationCreate, PolicySimulationListOut, PolicySimulationOut,
)
from app.services import guidelines as svc_g
from app.services import sandbox as svc_s

router = APIRouter(tags=["guidelines"])


# --------------------------------------------------------------------- Rules
@router.get(
    "/brands/{brand_id}/guidelines",
    response_model=GuidelineRuleListOut,
    responses=ERROR_RESPONSES,
    summary="List guideline rules for a brand",
)
def list_guideline_rules(
    brand_id: uuid.UUID,
    db: DbSession,
    status: Annotated[str | None, Query(description="Filter by rule status (proposed, active, retired)")] = None,
    category: Annotated[str | None, Query(description="Filter by category")] = None,
    limit: Limit = 100,
    offset: Offset = 0,
    actor: OptionalActor = None,
):
    verify_brand_access(brand_id, actor)
    return svc_g.list_rules(db, brand_id, status=status, category=category, limit=limit, offset=offset)


@router.post(
    "/brands/{brand_id}/guidelines",
    response_model=GuidelineRuleOut,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Create a new guideline rule",
)
def create_guideline_rule(
    brand_id: uuid.UUID,
    data: GuidelineRuleCreate,
    actor: CurrentActor,
    db: DbSession,
):
    verify_brand_access(brand_id, actor)
    return svc_g.create_rule(db, brand_id, data, actor_name=actor.name, actor_role=actor.role)


@router.post(
    "/brands/{brand_id}/guidelines/extract",
    response_model=GuidelineExtractResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Extract candidate guideline rules from an approved brand document",
)
def extract_guideline_rules(
    brand_id: uuid.UUID,
    data: GuidelineExtractRequest,
    actor: CurrentActor,
    db: DbSession,
):
    verify_brand_access(brand_id, actor)
    extracted = svc_g.extract_rules_from_document(db, brand_id, data.target_document_id, actor_name=actor.name)
    return GuidelineExtractResponse(
        extracted_rules=extracted,
        total_extracted=len(extracted),
        source_document_id=data.target_document_id,
    )


@router.get(
    "/guidelines/{rule_id}",
    response_model=GuidelineRuleOut,
    responses=ERROR_RESPONSES,
    summary="Get a guideline rule by ID",
)
def get_guideline_rule(rule_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    rule = svc_g.get_rule(db, rule_id)
    verify_brand_access(rule.brand_id, actor)
    return rule


@router.patch(
    "/guidelines/{rule_id}",
    response_model=GuidelineRuleOut,
    responses=ERROR_RESPONSES,
    summary="Update a guideline rule or change its status",
)
def update_guideline_rule(
    rule_id: uuid.UUID,
    data: GuidelineRuleUpdate,
    actor: CurrentActor,
    db: DbSession,
):
    rule = svc_g.get_rule(db, rule_id)
    verify_brand_access(rule.brand_id, actor)
    return svc_g.update_rule(db, rule_id, data, actor_name=actor.name, actor_role=actor.role)


@router.get(
    "/guidelines/{rule_id}/versions",
    response_model=list[GuidelineRuleVersionOut],
    responses=ERROR_RESPONSES,
    summary="Get version history of a guideline rule",
)
def get_rule_versions(rule_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    rule = svc_g.get_rule(db, rule_id)
    verify_brand_access(rule.brand_id, actor)
    return svc_g.list_versions(db, rule_id)


@router.post(
    "/guidelines/{rule_id}/versions",
    response_model=GuidelineRuleVersionOut,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Propose a new version for a guideline rule",
)
def propose_rule_version(
    rule_id: uuid.UUID,
    data: GuidelineRuleVersionCreate,
    actor: CurrentActor,
    db: DbSession,
):
    rule = svc_g.get_rule(db, rule_id)
    verify_brand_access(rule.brand_id, actor)
    return svc_g.create_rule_version(db, rule_id, data, actor_name=actor.name, actor_role=actor.role)


# --------------------------------------------------------------------- Linting
@router.post(
    "/brands/{brand_id}/guideline-lint",
    response_model=GuidelineLintResponse,
    responses=ERROR_RESPONSES,
    summary="Run Guideline Lint on brand rules to detect ambiguities, missing conditions, or conflicts",
)
def run_guideline_lint(
    brand_id: uuid.UUID,
    db: DbSession,
    rule_id: Annotated[uuid.UUID | None, Query(description="Optional specific rule ID to lint")] = None,
    actor: OptionalActor = None,
):
    verify_brand_access(brand_id, actor)
    return svc_g.lint_brand_rules(db, brand_id, rule_id=rule_id)


@router.get(
    "/brands/{brand_id}/guideline-lint-results",
    response_model=list[GuidelineLintIssueOut],
    responses=ERROR_RESPONSES,
    summary="Get latest guideline lint results for a brand",
)
def get_guideline_lint_results(brand_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    verify_brand_access(brand_id, actor)
    lint_resp = svc_g.lint_brand_rules(db, brand_id)
    return lint_resp.issues


# --------------------------------------------------------------------- Policy Sandbox Simulations
@router.post(
    "/brands/{brand_id}/policy-simulations",
    response_model=PolicySimulationOut,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Run a policy sandbox simulation against historical content submissions",
)
def create_policy_simulation(
    brand_id: uuid.UUID,
    data: PolicySimulationCreate,
    actor: CurrentActor,
    db: DbSession,
):
    verify_brand_access(brand_id, actor)
    return svc_s.run_policy_simulation(db, brand_id, data, actor_name=actor.name)


@router.get(
    "/brands/{brand_id}/policy-simulations",
    response_model=PolicySimulationListOut,
    responses=ERROR_RESPONSES,
    summary="List policy simulations run for a brand",
)
def list_policy_simulations(
    brand_id: uuid.UUID,
    db: DbSession,
    limit: Limit = 50,
    offset: Offset = 0,
    actor: OptionalActor = None,
):
    verify_brand_access(brand_id, actor)
    return svc_s.list_simulations(db, brand_id, limit=limit, offset=offset)


@router.get(
    "/policy-simulations/{simulation_id}",
    response_model=PolicySimulationOut,
    responses=ERROR_RESPONSES,
    summary="Get details and evaluated submission outcomes for a policy simulation",
)
def get_policy_simulation(simulation_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    sim = svc_s.get_simulation(db, simulation_id)
    verify_brand_access(sim.brand_id, actor)
    return sim
