"""Content revisions (Phase 4).

A ContentSubmission is one immutable revision of a ContentAsset. Correcting content never edits a submission: it appends the next
revision. Reviews, findings, evidence and Phase 3 impacts keep pointing at the exact revision they were created for.

Concurrency: create_revision locks the asset row, so two simultaneous requests are serialised. The second one finds that its
base revision is no longer the latest and receives 409 `revision_conflict` (its text is not lost: the client still has it).
Even without the lock, UNIQUE (asset_id, revision_number) and UNIQUE (parent_submission_id) would reject a duplicate.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Actor
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailed, field_error
from app.models import (
    ContentAsset, ContentSubmission, FactChangeImpact, ReviewFinding, ReviewRun, RevisionCorrection, WorkflowEvent,
)
from app.schemas.review import ReviewRunBrief
from app.schemas.workflow import DecisionBrief, RevisionCreate, RevisionHistory, RevisionRead
from app.services.content import _brief, _counts, content_hash, get_content


def latest_revision(db: Session, asset_id: uuid.UUID) -> ContentSubmission:
    row = db.scalar(select(ContentSubmission).where(ContentSubmission.asset_id == asset_id).order_by(ContentSubmission.revision_number.desc()).limit(1))
    assert row is not None
    return row


def _revision_conflict(latest: ContentSubmission) -> ConflictError:
    return ConflictError(
        f"A newer revision (revision {latest.revision_number}) already exists for this content. Open it and re-apply your changes; "
        "nothing you typed has been overwritten.",
        code="revision_conflict",
        details=[field_error("latest_revision_id", str(latest.id)), field_error("latest_revision_number", str(latest.revision_number))],
    )


def create_revision(db: Session, content_id: uuid.UUID, data: RevisionCreate, actor: Actor) -> ContentSubmission:
    base = get_content(db, content_id)
    limit = get_settings().max_content_chars
    if len(data.content) > limit:
        raise ValidationFailed("The content is too long.", details=[field_error("content", f"Content is limited to {limit:,} characters; this draft has {len(data.content):,}.")])
    # Serialise revision creation for this asset.
    asset = db.scalar(select(ContentAsset).where(ContentAsset.id == base.asset_id, ContentAsset.brand_id == base.brand_id).with_for_update())
    if asset is None:  # cannot happen with the composite foreign key; fail closed anyway
        raise NotFoundError("Content asset not found.")
    latest = latest_revision(db, asset.id)
    if latest.id != base.id:
        db.rollback()
        raise _revision_conflict(latest)
    if base.workflow_status == "in_review":
        db.rollback()
        raise ConflictError(
            "This revision is waiting for a reviewer's decision. Wait for the decision before creating another revision.", code="revision_in_review",
        )
    title = data.title or base.title
    if data.content == base.content and title == base.title:
        db.rollback()
        raise ValidationFailed("Nothing changed.", details=[field_error("content", "The new revision is identical to the current one.")])

    corrections = data.corrections
    if corrections:
        valid = set(db.scalars(
            select(ReviewFinding.id).join(ReviewRun, ReviewRun.id == ReviewFinding.review_run_id)
            .where(ReviewRun.content_submission_id == base.id, ReviewFinding.id.in_([c.finding_id for c in corrections]))
        ))
        for i, c in enumerate(corrections):
            if c.finding_id not in valid:
                db.rollback()
                raise ValidationFailed(
                    "A correction refers to a finding that does not belong to the revision being corrected.",
                    details=[field_error(f"corrections.{i}.finding_id", "Not a finding of a review of the base revision.")],
                )
        if len({c.finding_id for c in corrections}) != len(corrections):
            db.rollback()
            raise ValidationFailed("A finding can have one correction record per revision.", details=[field_error("corrections", "Duplicate finding_id.")])

    row = ContentSubmission(
        brand_id=base.brand_id, asset_id=asset.id, revision_number=base.revision_number + 1, parent_submission_id=base.id,
        workflow_status="draft", title=title, content=data.content, content_hash=content_hash(data.content), submitted_by=actor.name,
        change_note=data.change_note,
    )
    try:
        db.add(row)
        db.flush()
        asset.title = title
        for c in corrections:
            db.add(RevisionCorrection(
                brand_id=base.brand_id, submission_id=row.id, finding_id=c.finding_id, decision=c.decision, source=c.source,
                original_text=c.original_text, replacement_text=c.replacement_text,
            ))
        db.add(WorkflowEvent(
            brand_id=base.brand_id, asset_id=asset.id, submission_id=row.id, action="created", from_status=None, to_status="draft",
            actor=actor.name, actor_role=actor.role, rationale=data.change_note, details={"parent_submission_id": str(base.id)},
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _revision_conflict(latest_revision(db, base.asset_id)) from None
    db.refresh(row)
    return row


def _decision_brief(event: WorkflowEvent) -> DecisionBrief:
    return DecisionBrief(
        id=event.id, action=event.action, actor=event.actor, actor_role=event.actor_role, rationale=event.rationale,
        review_run_id=event.review_run_id, created_at=event.created_at,
    )


def revision_reads(db: Session, rows: list[ContentSubmission]) -> list[RevisionRead]:
    if not rows:
        return []
    ids = [r.id for r in rows]
    latest_id = max(rows, key=lambda r: r.revision_number).id
    run_total = dict(db.execute(select(ReviewRun.content_submission_id, func.count()).where(ReviewRun.content_submission_id.in_(ids)).group_by(ReviewRun.content_submission_id)).all())
    latest_run: dict[uuid.UUID, ReviewRun] = {}
    for run in db.scalars(select(ReviewRun).where(ReviewRun.content_submission_id.in_(ids)).order_by(ReviewRun.started_at, ReviewRun.id)):
        latest_run[run.content_submission_id] = run
    counts = _counts(db, [r.id for r in latest_run.values()])
    decisions = {
        e.submission_id: e for e in db.scalars(select(WorkflowEvent).where(WorkflowEvent.submission_id.in_(ids), WorkflowEvent.action.in_(("approved", "changes_requested", "rejected"))))
    }
    corrections = dict(db.execute(select(RevisionCorrection.submission_id, func.count()).where(RevisionCorrection.submission_id.in_(ids)).group_by(RevisionCorrection.submission_id)).all())
    impacts = dict(db.execute(
        select(FactChangeImpact.content_submission_id, func.count()).where(FactChangeImpact.content_submission_id.in_(ids), FactChangeImpact.status == "needs_review")
        .group_by(FactChangeImpact.content_submission_id)
    ).all())
    out: list[RevisionRead] = []
    for r in sorted(rows, key=lambda r: r.revision_number):
        run = latest_run.get(r.id)
        out.append(RevisionRead(
            id=r.id, asset_id=r.asset_id, brand_id=r.brand_id, revision_number=r.revision_number, parent_submission_id=r.parent_submission_id,
            title=r.title, created_by=r.submitted_by, created_at=r.created_at, change_note=r.change_note, char_count=len(r.content),
            content_hash=r.content_hash, workflow_status=r.workflow_status, is_latest=r.id == latest_id, review_count=run_total.get(r.id, 0),
            latest_review=_brief(run, counts[run.id]) if run else None, decision=_decision_brief(decisions[r.id]) if r.id in decisions else None,
            correction_count=corrections.get(r.id, 0), open_impact_count=impacts.get(r.id, 0),
        ))
    return out


def asset_revisions(db: Session, asset_id: uuid.UUID) -> list[ContentSubmission]:
    return list(db.scalars(select(ContentSubmission).where(ContentSubmission.asset_id == asset_id).order_by(ContentSubmission.revision_number)))


def revision_history(db: Session, content_id: uuid.UUID) -> RevisionHistory:
    row = get_content(db, content_id)
    asset = db.get(ContentAsset, row.asset_id)
    assert asset is not None
    rows = asset_revisions(db, asset.id)
    reads = revision_reads(db, rows)
    return RevisionHistory(asset_id=asset.id, brand_id=asset.brand_id, title=asset.title, latest_revision_id=reads[-1].id, items=reads)
