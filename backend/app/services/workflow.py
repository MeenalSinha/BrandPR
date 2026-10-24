"""Human approval workflow (Phase 4).

State machine (per revision; enforced here AND by a database trigger on content_submissions):

    draft --submit--> in_review --approve--------> approved
                                 +-request_changes-> changes_requested
                                 +-reject---------> rejected

approved, changes_requested and rejected are final for that revision. The creator continues with a NEW revision, which starts as a
draft and needs its own review and decision. Approval is never inherited.

Approval requires, all checked here against stored records (never against anything the browser says):
  * the revision exists, is `in_review` and is still the newest revision of its asset;
  * the actor is a reviewer and is not the person who created the revision (separation of duties);
  * the LATEST review run of that exact revision finished (completed or completed_limited), and its content hash equals the
    revision's stored hash and the hash of the stored text;
  * the reviewer names that run (so they approve what they actually looked at; a newer run makes the request stale);
  * every high-risk finding that is not 'supported' has a recorded override with a reason (RiskOverride). Findings are never edited.
"""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Actor
from app.core.errors import ConflictError, Forbidden, NotFoundError, ValidationFailed, field_error
from app.models import (
    ContentSubmission, ReviewFinding, ReviewRun, RevisionCorrection, RiskOverride, WorkflowEvent,
)
from app.schemas.workflow import (
    BlockingFinding, CorrectionRead, DecisionCreate, OverrideRead, Readiness, WorkflowEventRead, WorkflowRead,
)
from app.services import impact_resolution
from app.services.content import _brief, _counts, content_hash, has_newer_revision

COMPLETED = ("completed", "completed_limited")
FINAL = {"approve": ("approved", "approved"), "request_changes": ("changes_requested", "changes_requested"), "reject": ("rejected", "rejected")}


NOT_READY_CODES = {"no_review": "review_required", "review_in_progress": "review_in_progress", "review_failed": "review_failed", "content_mismatch": "review_content_mismatch"}


class InvalidTransition(ConflictError):
    code = "invalid_transition"


def get_submission(db: Session, content_id: uuid.UUID, *, lock: bool = False) -> ContentSubmission:
    stmt = select(ContentSubmission).where(ContentSubmission.id == content_id)
    row = db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise NotFoundError("Content not found.")
    return row


def latest_run(db: Session, submission_id: uuid.UUID) -> ReviewRun | None:
    return db.scalar(select(ReviewRun).where(ReviewRun.content_submission_id == submission_id).order_by(ReviewRun.started_at.desc(), ReviewRun.id.desc()).limit(1))


# ------------------------------------------------------------------ readiness
def readiness(db: Session, sub: ContentSubmission) -> Readiness:
    run = latest_run(db, sub.id)
    empty = dict(review=None, review_status=None, analysis_mode=None, limited_mode=False, limitations=[], counts={}, blocking_findings=[])
    if run is None:
        return Readiness(state="no_review", ready_for_decision=False, reasons=["This revision has not been reviewed yet. Run a review first."], **empty)
    counts = _counts(db, [run.id])[run.id]
    base = dict(review=_brief(run, counts), review_status=run.status, analysis_mode=run.analysis_mode, counts=counts)
    summary = run.summary or {}
    limitations = list(summary.get("limitations", []))
    limited = run.status == "completed_limited"
    if run.status in ("pending", "running"):
        return Readiness(state="review_in_progress", ready_for_decision=False, reasons=["The latest review has not finished."], limited_mode=False, limitations=[], blocking_findings=[], **base)
    if run.status == "failed":
        why = run.error_message or "The review failed."
        return Readiness(state="review_failed", ready_for_decision=False, reasons=[f"The latest review failed and is not evidence of anything: {why} Run the review again."], limited_mode=False, limitations=[], blocking_findings=[], **base)
    if not (run.content_hash == sub.content_hash == content_hash(sub.content)):
        return Readiness(state="content_mismatch", ready_for_decision=False, reasons=["The review does not match this revision's text. Run a new review."], limited_mode=limited, limitations=limitations, blocking_findings=[], **base)
    overridden = set(db.scalars(select(RiskOverride.finding_id).where(RiskOverride.review_run_id == run.id)))
    blocking = [
        BlockingFinding(finding_id=f.id, claim_text=f.claim_text, status=f.status, severity=f.severity, explanation=f.explanation, overridden=f.id in overridden)
        for f in db.scalars(select(ReviewFinding).where(ReviewFinding.review_run_id == run.id, ReviewFinding.severity == "high", ReviewFinding.status != "supported").order_by(ReviewFinding.claim_index))
    ]
    reasons = []
    if limited:
        reasons.append("Limited analysis: no AI provider was available, so only deterministic rules ran. Paraphrased claims may not have been detected.")
    open_blocking = [b for b in blocking if not b.overridden]
    if open_blocking:
        reasons.append(f"{len(open_blocking)} high-risk finding(s) need a reviewer's recorded override with a reason before approval.")
    return Readiness(state="ready", ready_for_decision=True, reasons=reasons, limited_mode=limited, limitations=limitations, blocking_findings=blocking, **base)


# ------------------------------------------------------------------ submit
def submit_for_review(db: Session, content_id: uuid.UUID, actor: Actor) -> ContentSubmission:
    sub = get_submission(db, content_id, lock=True)
    if sub.workflow_status != "draft":
        db.rollback()
        raise InvalidTransition(f"This revision is {sub.workflow_status.replace('_', ' ')}; only a draft can be submitted for review.")
    if has_newer_revision(db, sub):
        db.rollback()
        raise ConflictError("A newer revision exists; submit that one instead.", code="revision_superseded")
    ready = readiness(db, sub)
    if not ready.ready_for_decision:
        db.rollback()
        raise ConflictError(ready.reasons[0], code=NOT_READY_CODES[ready.state])
    run = latest_run(db, sub.id)
    assert run is not None
    try:
        db.add(WorkflowEvent(
            brand_id=sub.brand_id, asset_id=sub.asset_id, submission_id=sub.id, review_run_id=run.id, action="submitted",
            from_status="draft", to_status="in_review", actor=actor.name, actor_role=actor.role,
        ))
        sub.workflow_status = "in_review"
        db.commit()
    except IntegrityError:
        db.rollback()
        raise InvalidTransition("This revision was already submitted.") from None
    db.refresh(sub)
    return sub


# ------------------------------------------------------------------ decide
def decide(db: Session, content_id: uuid.UUID, data: DecisionCreate, actor: Actor) -> ContentSubmission:
    sub = get_submission(db, content_id, lock=True)
    if sub.workflow_status != "in_review":
        db.rollback()
        raise InvalidTransition(f"A decision can only be recorded on a revision that is in review; this one is {sub.workflow_status.replace('_', ' ')}.")
    if has_newer_revision(db, sub):
        db.rollback()
        raise ConflictError("A newer revision exists, so this one can no longer be decided.", code="revision_superseded")
    if sub.submitted_by and sub.submitted_by.strip().lower() == actor.name.strip().lower():
        db.rollback()
        raise Forbidden("A reviewer cannot decide on a revision they created themselves.", code="self_review_not_allowed")

    run = latest_run(db, sub.id)
    run_findings = {f.id: f for f in db.scalars(select(ReviewFinding).where(ReviewFinding.review_run_id == run.id))} if run else {}
    new_status, action = FINAL[data.action]
    rationale = data.rationale
    overrides: list = []

    def fail(exc: Exception):
        db.rollback()
        return exc

    if data.action == "approve":
        if data.review_run_id is None:
            raise fail(ValidationFailed("Name the review run you approved.", details=[field_error("review_run_id", "Required to approve.")]))
        ready = readiness(db, sub)
        if not ready.ready_for_decision:
            raise fail(ConflictError(ready.reasons[0], code=NOT_READY_CODES[ready.state]))
        assert run is not None
        if data.review_run_id != run.id:
            raise fail(ConflictError("A newer review exists for this revision than the one you approved. Look at the latest review first.", code="stale_review"))
        blocking = {b.finding_id: b for b in ready.blocking_findings}
        given = {o.finding_id: o for o in data.overrides}
        if len(given) != len(data.overrides):
            raise fail(ValidationFailed("Each finding can be overridden once.", details=[field_error("overrides", "Duplicate finding_id.")]))
        unknown = [str(fid) for fid in given if fid not in blocking]
        if unknown:
            raise fail(ValidationFailed(
                "Only high-risk findings of the latest review can be overridden.",
                details=[field_error("overrides", f"Not an overridable finding: {fid}") for fid in unknown],
            ))
        missing = [b for fid, b in blocking.items() if fid not in given]
        if missing:
            raise fail(ConflictError(
                "High-risk findings must be fixed in a new revision, or accepted by a reviewer with a recorded reason.", code="high_risk_unresolved",
                details=[field_error(str(b.finding_id), f"{b.status}: {b.claim_text[:120]}") for b in missing],
            ))
        overrides = list(given.values())
    else:
        if not rationale:
            raise fail(ValidationFailed("A reason is required.", details=[field_error("rationale", "Explain why changes are needed." if data.action == "request_changes" else "Explain why this revision is rejected.")]))
        if data.overrides or data.resolve_impact_ids:
            raise fail(ValidationFailed("Overrides and impact resolution only apply to an approval.", details=[field_error("action", "Use action 'approve'.")]))
        bad = [str(fid) for fid in data.finding_ids if fid not in run_findings]
        if bad:
            raise fail(ValidationFailed("A linked finding is not part of the latest review.", details=[field_error("finding_ids", f"Unknown finding: {fid}") for fid in bad]))

    details: dict = {}
    if data.finding_ids:
        details["finding_ids"] = [str(f) for f in data.finding_ids]
    try:
        event = WorkflowEvent(
            brand_id=sub.brand_id, asset_id=sub.asset_id, submission_id=sub.id, review_run_id=run.id if run else None, action=action,
            from_status="in_review", to_status=new_status, actor=actor.name, actor_role=actor.role, rationale=rationale, details=details,
        )
        db.add(event)
        db.flush()
        for o in overrides:
            db.add(RiskOverride(brand_id=sub.brand_id, event_id=event.id, review_run_id=run.id, finding_id=o.finding_id, reason=o.reason, actor=actor.name))
        sub.workflow_status = new_status
        db.flush()
        for impact_id in data.resolve_impact_ids:  # same transaction: either the approval and all resolutions are saved, or none
            impact_resolution.resolve(db, impact_id, sub, data.resolution_rationale or rationale or "Resolved by the approved revision.", actor, event=event, commit=False)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise InvalidTransition("A decision has already been recorded for this revision.") from None
    except Exception:
        db.rollback()
        raise
    db.refresh(sub)
    return sub


# ------------------------------------------------------------------ read model
def _event_read(e: WorkflowEvent, revision_number: int) -> WorkflowEventRead:
    return WorkflowEventRead(
        id=e.id, submission_id=e.submission_id, revision_number=revision_number, action=e.action, from_status=e.from_status, to_status=e.to_status,
        actor=e.actor, actor_role=e.actor_role, rationale=e.rationale, review_run_id=e.review_run_id,
        finding_ids=[uuid.UUID(x) for x in (e.details or {}).get("finding_ids", [])], created_at=e.created_at,
    )


def asset_events(db: Session, asset_id: uuid.UUID) -> list[WorkflowEventRead]:
    rows = db.execute(
        select(WorkflowEvent, ContentSubmission.revision_number).join(ContentSubmission, ContentSubmission.id == WorkflowEvent.submission_id)
        .where(WorkflowEvent.asset_id == asset_id).order_by(WorkflowEvent.created_at, ContentSubmission.revision_number, WorkflowEvent.id)
    ).all()
    return [_event_read(e, n) for e, n in rows]


def available_actions(sub: ContentSubmission, latest: bool, ready: Readiness, actor: Actor) -> list[str]:
    actions: list[str] = []
    if latest and sub.workflow_status == "draft":
        actions.append("run_review")
        if ready.ready_for_decision:
            actions.append("submit_review")
    if latest and sub.workflow_status != "in_review":
        actions.append("create_revision")
    if actor.is_reviewer and latest and sub.workflow_status == "in_review" and (sub.submitted_by or "").strip().lower() != actor.name.strip().lower():
        actions += ["request_changes", "reject"]
        if ready.ready_for_decision:
            actions.append("approve")
    return actions


def workflow_read(db: Session, content_id: uuid.UUID, actor: Actor | None) -> WorkflowRead:
    sub = get_submission(db, content_id)
    latest = not has_newer_revision(db, sub)
    ready = readiness(db, sub)
    approved = db.scalar(select(WorkflowEvent).where(WorkflowEvent.submission_id == sub.id, WorkflowEvent.action == "approved"))
    return WorkflowRead(
        submission_id=sub.id, asset_id=sub.asset_id, brand_id=sub.brand_id, title=sub.title, revision_number=sub.revision_number, is_latest=latest,
        created_by=sub.submitted_by, workflow_status=sub.workflow_status, readiness=ready, events=asset_events(db, sub.asset_id),
        overrides=[OverrideRead.model_validate(o) for o in db.scalars(
            select(RiskOverride).join(WorkflowEvent, WorkflowEvent.id == RiskOverride.event_id).where(WorkflowEvent.asset_id == sub.asset_id).order_by(RiskOverride.created_at, RiskOverride.id)
        )],
        corrections=[CorrectionRead.model_validate(c) for c in db.scalars(select(RevisionCorrection).where(RevisionCorrection.submission_id == sub.id).order_by(RevisionCorrection.created_at, RevisionCorrection.id))],
        available_actions=available_actions(sub, latest, ready, actor) if actor else [], approved_run_id=approved.review_run_id if approved else None,
    )
