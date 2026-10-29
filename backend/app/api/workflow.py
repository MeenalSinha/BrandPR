"""Phase 4 routes: revisions, suggested corrections, human approval and fact-change impact resolution.
"""
import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentActor, DbSession, OptionalActor, ReviewerActor, get_review_provider, verify_brand_access
from app.core.errors import NotFoundError
from app.models.fact_change_impact import FactChangeImpact
from app.schemas.common import ERROR_RESPONSES
from app.schemas.review import ContentRead, FindingRead
from app.schemas.workflow import (
    DecisionCreate, FindingDetail, ImpactDismissIn, ImpactHistory, ImpactResolutionRead, ImpactResolveIn, RevisionCreate, RevisionHistory,
    SuggestionRead, WorkflowRead,
)
from app.services import content as content_svc
from app.services import corrections, impact_resolution, revisions, workflow
from app.services.content import finding_reads

router = APIRouter(tags=["workflow"])


@router.post("/content/{content_id}/revisions", response_model=ContentRead, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES,
             summary="Create the next revision of content")
def create_revision(content_id: uuid.UUID, data: RevisionCreate, db: DbSession, actor: CurrentActor):
    sub = content_svc.get_content(db, content_id)
    verify_brand_access(sub.brand_id, actor)
    return content_svc.content_read(db, revisions.create_revision(db, content_id, data, actor))


@router.get("/content/{content_id}/revisions", response_model=RevisionHistory, responses=ERROR_RESPONSES, summary="All revisions of the content's asset, oldest first, with review status and decisions")
def list_revisions(content_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    sub = content_svc.get_content(db, content_id)
    verify_brand_access(sub.brand_id, actor)
    return revisions.revision_history(db, content_id)


@router.get("/findings/{finding_id}", response_model=FindingDetail, responses=ERROR_RESPONSES, summary="One finding with its evidence and the revision it belongs to")
def get_finding(finding_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    from app.models import ContentSubmission, ReviewFinding, ReviewRun

    finding = db.get(ReviewFinding, finding_id)
    if finding is None:
        raise NotFoundError("Finding not found.")
    run = db.get(ReviewRun, finding.review_run_id)
    verify_brand_access(run.brand_id, actor)
    sub = db.get(ContentSubmission, run.content_submission_id)
    read: FindingRead = finding_reads(db, [finding])[0]
    return FindingDetail(finding=read, revision_number=sub.revision_number, submission_id=sub.id)


@router.post("/findings/{finding_id}/suggest-correction", response_model=SuggestionRead, responses=ERROR_RESPONSES,
             summary="Ask the AI provider for a proposed replacement of one claim")
def suggest_correction(finding_id: uuid.UUID, db: DbSession, actor: CurrentActor, provider=Depends(get_review_provider)):
    from app.models import ReviewFinding, ReviewRun
    finding = db.get(ReviewFinding, finding_id)
    if finding is None:
        raise NotFoundError("Finding not found.")
    run = db.get(ReviewRun, finding.review_run_id)
    verify_brand_access(run.brand_id, actor)
    return corrections.suggest(db, finding_id, provider)


@router.post("/content/{content_id}/submit-review", response_model=WorkflowRead, responses=ERROR_RESPONSES,
             summary="Submit a reviewed draft revision for human approval")
def submit_review(content_id: uuid.UUID, db: DbSession, actor: CurrentActor):
    sub = content_svc.get_content(db, content_id)
    verify_brand_access(sub.brand_id, actor)
    workflow.submit_for_review(db, content_id, actor)
    return workflow.workflow_read(db, content_id, actor)


@router.get("/content/{content_id}/workflow", response_model=WorkflowRead, responses=ERROR_RESPONSES,
            summary="Workflow state, approval readiness, decision history and the actions the caller may take")
def get_workflow(content_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    sub = content_svc.get_content(db, content_id)
    verify_brand_access(sub.brand_id, actor)
    return workflow.workflow_read(db, content_id, actor)


@router.post("/content/{content_id}/decisions", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES,
             summary="Approve, request changes on, or reject a revision (reviewers only)")
def create_decision(content_id: uuid.UUID, data: DecisionCreate, db: DbSession, actor: ReviewerActor):
    sub = content_svc.get_content(db, content_id)
    verify_brand_access(sub.brand_id, actor)
    workflow.decide(db, content_id, data, actor)
    return workflow.workflow_read(db, content_id, actor)


@router.post("/fact-change-impacts/{impact_id}/resolve", response_model=ImpactResolutionRead, responses=ERROR_RESPONSES,
             summary="Resolve an impact with an approved, later revision (reviewers only)")
def resolve_impact(impact_id: uuid.UUID, data: ImpactResolveIn, db: DbSession, actor: ReviewerActor):
    impact = db.get(FactChangeImpact, impact_id)
    if impact is None:
        raise NotFoundError("Impact not found.")
    verify_brand_access(impact.brand_id, actor)
    row = impact_resolution.resolve_by_id(db, impact_id, data.resolving_submission_id, data.rationale, actor)
    return _resolution(db, row)


@router.post("/fact-change-impacts/{impact_id}/dismiss", response_model=ImpactResolutionRead, responses=ERROR_RESPONSES,
             summary="Dismiss an impact: no action needed (reviewers only, reason required)")
def dismiss_impact(impact_id: uuid.UUID, data: ImpactDismissIn, db: DbSession, actor: ReviewerActor):
    impact = db.get(FactChangeImpact, impact_id)
    if impact is None:
        raise NotFoundError("Impact not found.")
    verify_brand_access(impact.brand_id, actor)
    return _resolution(db, impact_resolution.dismiss(db, impact_id, data.rationale, actor))


@router.get("/fact-change-impacts/{impact_id}/history", response_model=ImpactHistory, responses=ERROR_RESPONSES,
            summary="The impact's resolution record, the asset's revisions and every workflow event")
def impact_history(impact_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    impact = db.get(FactChangeImpact, impact_id)
    if impact is None:
        raise NotFoundError("Impact not found.")
    verify_brand_access(impact.brand_id, actor)
    return impact_resolution.history(db, impact_id)


def _resolution(db, row) -> ImpactResolutionRead:
    from app.models import ContentSubmission

    sub = db.get(ContentSubmission, row.resolving_submission_id) if row.resolving_submission_id else None
    return impact_resolution.resolution_read(row, sub.revision_number if sub else None)
