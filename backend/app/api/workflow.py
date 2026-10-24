"""Phase 4 routes: revisions, suggested corrections, human approval and fact-change impact resolution.

Identity is the demo actor (X-Actor-Name / X-Actor-Role headers); see app/api/deps.py. All rules live in the services.
"""
import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentActor, DbSession, OptionalActor, ReviewerActor, get_review_provider
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

ROLE_NOTE = (
    "Needs the demo identity headers X-Actor-Name and X-Actor-Role. The role is asserted by the caller and is NOT authenticated "
    "(competition prototype); the backend still enforces what each role may do."
)


@router.post("/content/{content_id}/revisions", response_model=ContentRead, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES,
             summary="Create the next revision of content", description="Never edits the base revision. `content_id` must be the newest revision, otherwise 409 `revision_conflict`. " + ROLE_NOTE)
def create_revision(content_id: uuid.UUID, data: RevisionCreate, db: DbSession, actor: CurrentActor):
    return content_svc.content_read(db, revisions.create_revision(db, content_id, data, actor))


@router.get("/content/{content_id}/revisions", response_model=RevisionHistory, responses=ERROR_RESPONSES, summary="All revisions of the content's asset, oldest first, with review status and decisions")
def list_revisions(content_id: uuid.UUID, db: DbSession):
    return revisions.revision_history(db, content_id)


@router.get("/findings/{finding_id}", response_model=FindingDetail, responses=ERROR_RESPONSES, summary="One finding with its evidence and the revision it belongs to")
def get_finding(finding_id: uuid.UUID, db: DbSession):
    from app.models import ContentSubmission, ReviewFinding, ReviewRun
    from app.core.errors import NotFoundError

    finding = db.get(ReviewFinding, finding_id)
    if finding is None:
        raise NotFoundError("Finding not found.")
    run = db.get(ReviewRun, finding.review_run_id)
    sub = db.get(ContentSubmission, run.content_submission_id)
    read: FindingRead = finding_reads(db, [finding])[0]
    return FindingDetail(finding=read, revision_number=sub.revision_number, submission_id=sub.id)


@router.post("/findings/{finding_id}/suggest-correction", response_model=SuggestionRead, responses=ERROR_RESPONSES,
             summary="Ask the AI provider for a proposed replacement of one claim",
             description="A proposal only: nothing is saved or applied. 503 `ai_unavailable` when no provider is configured (manual correction still works); "
                         "409 `no_current_evidence` when the finding cites no currently approved fact. " + ROLE_NOTE)
def suggest_correction(finding_id: uuid.UUID, db: DbSession, actor: CurrentActor, provider=Depends(get_review_provider)):
    return corrections.suggest(db, finding_id, provider)


@router.post("/content/{content_id}/submit-review", response_model=WorkflowRead, responses=ERROR_RESPONSES,
             summary="Submit a reviewed draft revision for human approval",
             description="draft -> in_review. Needs a finished review of this exact text (a failed or missing review gives 409). " + ROLE_NOTE)
def submit_review(content_id: uuid.UUID, db: DbSession, actor: CurrentActor):
    workflow.submit_for_review(db, content_id, actor)
    return workflow.workflow_read(db, content_id, actor)


@router.get("/content/{content_id}/workflow", response_model=WorkflowRead, responses=ERROR_RESPONSES,
            summary="Workflow state, approval readiness, decision history and the actions the caller may take",
            description="Identity headers are optional here; without them `available_actions` is empty.")
def get_workflow(content_id: uuid.UUID, db: DbSession, actor: OptionalActor):
    return workflow.workflow_read(db, content_id, actor)


@router.post("/content/{content_id}/decisions", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES,
             summary="Approve, request changes on, or reject a revision (reviewers only)",
             description="in_review -> approved | changes_requested | rejected. Approving needs the latest finished review of this exact text, and a recorded override "
                         "with a reason for each high-risk finding. `resolve_impact_ids` resolves eligible impacts in the same transaction. " + ROLE_NOTE)
def create_decision(content_id: uuid.UUID, data: DecisionCreate, db: DbSession, actor: ReviewerActor):
    workflow.decide(db, content_id, data, actor)
    return workflow.workflow_read(db, content_id, actor)


@router.post("/fact-change-impacts/{impact_id}/resolve", response_model=ImpactResolutionRead, responses=ERROR_RESPONSES,
             summary="Resolve an impact with an approved, later revision (reviewers only)",
             description="Only after the corrected revision was reviewed and approved against the current fact; see docs/API.md for every condition. Repeating the same request is idempotent. " + ROLE_NOTE)
def resolve_impact(impact_id: uuid.UUID, data: ImpactResolveIn, db: DbSession, actor: ReviewerActor):
    row = impact_resolution.resolve_by_id(db, impact_id, data.resolving_submission_id, data.rationale, actor)
    return _resolution(db, row)


@router.post("/fact-change-impacts/{impact_id}/dismiss", response_model=ImpactResolutionRead, responses=ERROR_RESPONSES,
             summary="Dismiss an impact: no action needed (reviewers only, reason required)", description=ROLE_NOTE)
def dismiss_impact(impact_id: uuid.UUID, data: ImpactDismissIn, db: DbSession, actor: ReviewerActor):
    return _resolution(db, impact_resolution.dismiss(db, impact_id, data.rationale, actor))


@router.get("/fact-change-impacts/{impact_id}/history", response_model=ImpactHistory, responses=ERROR_RESPONSES,
            summary="The impact's resolution record, the asset's revisions and every workflow event")
def impact_history(impact_id: uuid.UUID, db: DbSession):
    return impact_resolution.history(db, impact_id)


def _resolution(db, row) -> ImpactResolutionRead:
    from app.models import ContentSubmission

    sub = db.get(ContentSubmission, row.resolving_submission_id) if row.resolving_submission_id else None
    return impact_resolution.resolution_read(row, sub.revision_number if sub else None)
