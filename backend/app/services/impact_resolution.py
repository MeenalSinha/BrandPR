"""Closing Phase 3 fact-change impacts (Phase 4).

An impact is never deleted and never loses its triggering record. It is closed in exactly one of two ways, each writing an
append-only row to fact_change_impact_resolutions in the same transaction as the status change (a database trigger refuses a
status change without that row):

  resolved   A later revision of the SAME asset was corrected, reviewed and APPROVED by a reviewer. All of these must hold:
               * the resolving revision is newer than the revision the impact was recorded against, in the same asset and brand;
               * it is `approved`, and the approval names a review run of exactly that revision that finished (completed or
                 completed_limited) with a content hash equal to the stored text's hash;
               * that run started after the impact was recorded (so it saw the changed fact);
               * the fact has not been revised again since that run started;
               * any evidence in that run about the fact is for the fact's CURRENT version while it is current;
               * no finding of that run that cites the fact is `conflicting` or `outdated`. A reviewer's risk override on such a
                 finding does not clear the impact: fix the claim or dismiss the impact explicitly.
             Opening a draft, editing, reviewing, or a failed/pending review never resolves anything.
  dismissed  A reviewer decides the change does not require action and records why.

Only reviewers can do either. Repeating the same resolve request is idempotent; any other attempt on a closed impact is a 409.
"""
import uuid

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Actor
from app.core.errors import ConflictError, Forbidden, NotFoundError, field_error
from app.models import (
    ApprovedFact, ContentSubmission, FactChangeImpact, FactChangeImpactResolution, FactRevision, FindingEvidence, ReviewFinding, ReviewRun,
    WorkflowEvent,
)
from app.schemas.workflow import ImpactHistory, ImpactResolutionRead
from app.services.content import content_hash

COMPLETED = ("completed", "completed_limited")


def _locked_impact(db: Session, impact_id: uuid.UUID) -> FactChangeImpact:
    impact = db.scalar(select(FactChangeImpact).where(FactChangeImpact.id == impact_id).with_for_update())
    if impact is None:
        raise NotFoundError("Impact not found.")
    return impact


def _require_reviewer(actor: Actor) -> None:
    if not actor.is_reviewer:
        raise Forbidden("Only a reviewer can close an impact.", code="reviewer_role_required")


def _close(db: Session, impact: FactChangeImpact, *, action: str, actor: Actor, rationale: str, sub: ContentSubmission | None, event: WorkflowEvent | None) -> FactChangeImpactResolution:
    row = FactChangeImpactResolution(
        brand_id=impact.brand_id, impact_id=impact.id, action=action, from_status=impact.status, to_status=action, actor=actor.name, actor_role=actor.role,
        rationale=rationale, resolving_submission_id=sub.id if sub else None, resolving_review_run_id=event.review_run_id if event else None,
        decision_event_id=event.id if event else None,
    )
    db.add(row)
    db.flush()  # the resolution row must exist before the status changes (database trigger)
    impact.status = action
    db.flush()
    return row


def resolve(db: Session, impact_id: uuid.UUID, sub: ContentSubmission, rationale: str, actor: Actor, *, event: WorkflowEvent | None = None, commit: bool = True) -> FactChangeImpactResolution:
    _require_reviewer(actor)
    impact = _locked_impact(db, impact_id)
    existing = db.scalar(select(FactChangeImpactResolution).where(FactChangeImpactResolution.impact_id == impact.id))
    if existing is not None:
        if existing.action == "resolved" and existing.resolving_submission_id == sub.id:
            return existing  # repeated request: same outcome, nothing new recorded
        raise ConflictError(f"This impact is already {existing.to_status}.", code="impact_not_open")
    if impact.brand_id != sub.brand_id:
        raise ConflictError("The resolving revision belongs to a different brand.", code="wrong_brand")
    affected = db.get(ContentSubmission, impact.content_submission_id)
    assert affected is not None
    if sub.asset_id != affected.asset_id:
        raise ConflictError("The resolving revision belongs to different content than the impact.", code="wrong_asset")
    if sub.revision_number <= affected.revision_number:
        raise ConflictError("The resolving revision must be newer than the revision the impact was recorded against.", code="wrong_revision")
    if sub.workflow_status != "approved":
        raise ConflictError(f"The revision is {sub.workflow_status.replace('_', ' ')}, not approved, so it cannot resolve an impact.", code="revision_not_approved")
    event = event or db.scalar(select(WorkflowEvent).where(WorkflowEvent.submission_id == sub.id, WorkflowEvent.action == "approved"))
    if event is None or event.review_run_id is None:
        raise ConflictError("No approval with a review run is recorded for this revision.", code="no_approval_evidence")
    run = db.get(ReviewRun, event.review_run_id)
    if run is None or run.content_submission_id != sub.id or run.status not in COMPLETED:
        raise ConflictError("The approving review did not finish for this revision, so it cannot resolve an impact.", code="review_not_completed")
    if not (run.content_hash == sub.content_hash == content_hash(sub.content)):
        raise ConflictError("The approving review does not match the revision's text.", code="review_hash_mismatch")
    if run.started_at < impact.created_at:
        raise ConflictError("The approving review ran before this impact was recorded, so it did not see the changed fact. Review the revision again.", code="review_predates_impact")

    fact = db.get(ApprovedFact, impact.fact_id)
    assert fact is not None
    changed_after = db.scalar(select(exists().where(FactRevision.fact_id == fact.id, FactRevision.created_at > run.started_at)))
    if changed_after:
        raise ConflictError("The fact changed again after the approving review. Review the revision against the current fact.", code="fact_changed_since_review")
    cites = (ReviewFinding.matched_fact_id == fact.id) | exists().where(FindingEvidence.finding_id == ReviewFinding.id, FindingEvidence.fact_id == fact.id)
    cited = list(db.scalars(select(ReviewFinding).where(ReviewFinding.review_run_id == run.id, cites).order_by(ReviewFinding.claim_index)))
    unresolved = [f for f in cited if f.status in ("conflicting", "outdated")]
    if unresolved:
        raise ConflictError(
            "The approved review still reports a conflict with, or outdated reliance on, the changed fact. Correct the claim, or dismiss the impact with a reason.",
            code="conflict_unresolved", details=[field_error(str(f.id), f"{f.status}: {f.claim_text[:120]}") for f in unresolved],
        )
    stale = list(db.scalars(
        select(FindingEvidence).join(ReviewFinding, ReviewFinding.id == FindingEvidence.finding_id)
        .where(ReviewFinding.review_run_id == run.id, FindingEvidence.fact_id == fact.id)
    ))
    if any(e.fact_version != fact.version or e.fact_effective_state != "current" for e in stale):
        raise ConflictError("The approved review relied on an earlier version of the fact.", code="stale_evidence")

    try:
        row = _close(db, impact, action="resolved", actor=actor, rationale=rationale, sub=sub, event=event)
        if commit:
            db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("This impact was closed by another request.", code="impact_not_open") from None
    return row


def resolve_by_id(db: Session, impact_id: uuid.UUID, submission_id: uuid.UUID, rationale: str, actor: Actor) -> FactChangeImpactResolution:
    _require_reviewer(actor)
    sub = db.scalar(select(ContentSubmission).where(ContentSubmission.id == submission_id))
    if sub is None:
        raise NotFoundError("Resolving revision not found.")
    try:
        return resolve(db, impact_id, sub, rationale, actor)
    except Exception:
        db.rollback()
        raise


def dismiss(db: Session, impact_id: uuid.UUID, rationale: str, actor: Actor) -> FactChangeImpactResolution:
    _require_reviewer(actor)
    impact = _locked_impact(db, impact_id)
    existing = db.scalar(select(FactChangeImpactResolution).where(FactChangeImpactResolution.impact_id == impact.id))
    if existing is not None:
        if existing.action == "dismissed" and existing.rationale == rationale:
            db.rollback()
            return existing
        db.rollback()
        raise ConflictError(f"This impact is already {existing.to_status}.", code="impact_not_open")
    try:
        row = _close(db, impact, action="dismissed", actor=actor, rationale=rationale, sub=None, event=None)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("This impact was closed by another request.", code="impact_not_open") from None
    return row


def resolution_read(row: FactChangeImpactResolution, revision_number: int | None) -> ImpactResolutionRead:
    return ImpactResolutionRead(
        id=row.id, impact_id=row.impact_id, action=row.action, from_status=row.from_status, to_status=row.to_status, actor=row.actor, actor_role=row.actor_role,
        rationale=row.rationale, resolving_submission_id=row.resolving_submission_id, resolving_revision_number=revision_number,
        resolving_review_run_id=row.resolving_review_run_id, decision_event_id=row.decision_event_id, created_at=row.created_at,
    )


def history(db: Session, impact_id: uuid.UUID) -> ImpactHistory:
    from app.services import revisions, workflow

    impact = db.get(FactChangeImpact, impact_id)
    if impact is None:
        raise NotFoundError("Impact not found.")
    affected = db.get(ContentSubmission, impact.content_submission_id)
    assert affected is not None
    rows = revisions.asset_revisions(db, affected.asset_id)
    numbers = {r.id: r.revision_number for r in rows}
    resolutions = [
        resolution_read(r, numbers.get(r.resolving_submission_id) if r.resolving_submission_id else None)
        for r in db.scalars(select(FactChangeImpactResolution).where(FactChangeImpactResolution.impact_id == impact.id).order_by(FactChangeImpactResolution.created_at, FactChangeImpactResolution.id))
    ]
    latest = rows[-1]
    return ImpactHistory(
        impact_id=impact.id, status=impact.status, detected_at=impact.created_at, affected_submission_id=affected.id, affected_revision_number=affected.revision_number,
        asset_id=affected.asset_id, latest_revision_id=latest.id, latest_revision_number=latest.revision_number, resolutions=resolutions,
        revisions=revisions.revision_reads(db, rows), events=workflow.asset_events(db, affected.asset_id),
    )
