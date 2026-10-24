"""Content submissions and read access to review runs and findings."""
import hashlib
import uuid

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationFailed, field_error
from app.models import ContentAsset, ContentSubmission, FindingEvidence, ReviewFinding, ReviewRun, WorkflowEvent
from app.schemas.review import (
    ContentCreate, ContentRead, ContentSummary, EvidenceRead, FindingRead, ReviewRunBrief, ReviewRunRead,
)
from app.services.brands import get_brand

STATUSES = ("supported", "unsupported", "conflicting", "outdated", "uncertain")


# ------------------------------------------------------------------ content
def create_content(db: Session, brand_id: uuid.UUID, data: ContentCreate) -> ContentSubmission:
    get_brand(db, brand_id)
    limit = get_settings().max_content_chars
    if len(data.content) > limit:
        raise ValidationFailed(
            "The content is too long.", details=[field_error("content", f"Content is limited to {limit:,} characters; this draft has {len(data.content):,}.")]
        )
    # Phase 4: every submission is revision 1 of a new logical asset (a later revision is created with revisions.create_revision).
    asset = ContentAsset(brand_id=brand_id, title=data.title, created_by=data.submitted_by)
    db.add(asset)
    db.flush()
    row = ContentSubmission(
        brand_id=brand_id, asset_id=asset.id, revision_number=1, workflow_status="draft", title=data.title, content=data.content,
        submitted_by=data.submitted_by, content_hash=content_hash(data.content),
    )
    db.add(row)
    db.flush()
    db.add(WorkflowEvent(
        brand_id=brand_id, asset_id=asset.id, submission_id=row.id, action="created", from_status=None, to_status="draft",
        actor=data.submitted_by or "anonymous", actor_role="creator",
    ))
    db.commit()
    db.refresh(row)
    return row


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_content(db: Session, content_id: uuid.UUID) -> ContentSubmission:
    row = db.get(ContentSubmission, content_id)
    if row is None:
        raise NotFoundError("Content not found.")
    return row


def _counts(db: Session, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    out = {rid: {s: 0 for s in STATUSES} for rid in run_ids}
    if run_ids:
        for run_id, status, n in db.execute(
            select(ReviewFinding.review_run_id, ReviewFinding.status, func.count()).where(ReviewFinding.review_run_id.in_(run_ids)).group_by(ReviewFinding.review_run_id, ReviewFinding.status)
        ):
            out[run_id][status] = n
    return out


def _brief(run: ReviewRun, counts: dict[str, int]) -> ReviewRunBrief:
    return ReviewRunBrief(id=run.id, status=run.status, analysis_mode=run.analysis_mode, started_at=run.started_at, completed_at=run.completed_at, counts=counts)


def _latest(db: Session, content_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, ReviewRunBrief | None]]:
    result: dict[uuid.UUID, tuple[int, ReviewRunBrief | None]] = {cid: (0, None) for cid in content_ids}
    if not content_ids:
        return result
    totals = dict(db.execute(select(ReviewRun.content_submission_id, func.count()).where(ReviewRun.content_submission_id.in_(content_ids)).group_by(ReviewRun.content_submission_id)).all())
    latest: dict[uuid.UUID, ReviewRun] = {}
    for run in db.scalars(select(ReviewRun).where(ReviewRun.content_submission_id.in_(content_ids)).order_by(ReviewRun.started_at, ReviewRun.id)):
        latest[run.content_submission_id] = run
    counts = _counts(db, [r.id for r in latest.values()])
    for cid in content_ids:
        run = latest.get(cid)
        result[cid] = (totals.get(cid, 0), _brief(run, counts[run.id]) if run else None)
    return result


def has_newer_revision(db: Session, row: ContentSubmission) -> bool:
    return bool(db.scalar(select(exists().where(ContentSubmission.parent_submission_id == row.id))))


def content_read(db: Session, row: ContentSubmission) -> ContentRead:
    n, latest = _latest(db, [row.id])[row.id]
    return ContentRead(
        id=row.id, brand_id=row.brand_id, asset_id=row.asset_id, revision_number=row.revision_number,
        parent_submission_id=row.parent_submission_id, workflow_status=row.workflow_status, is_latest=not has_newer_revision(db, row),
        change_note=row.change_note, title=row.title, content=row.content, content_hash=row.content_hash, submitted_by=row.submitted_by,
        created_at=row.created_at, updated_at=row.updated_at, review_count=n, latest_review=latest,
    )


def list_content(db: Session, brand_id: uuid.UUID, limit: int, offset: int, *, latest_only: bool = False) -> tuple[list[ContentSummary], int]:
    get_brand(db, brand_id)
    cond = [ContentSubmission.brand_id == brand_id]
    if latest_only:  # one row per asset: the newest revision
        child = ContentSubmission.__table__.alias("child")
        cond.append(~exists().where(child.c.parent_submission_id == ContentSubmission.id))
    total = db.scalar(select(func.count()).select_from(ContentSubmission).where(*cond)) or 0
    rows = list(db.scalars(select(ContentSubmission).where(*cond).order_by(ContentSubmission.created_at.desc(), ContentSubmission.id).limit(limit).offset(offset)))
    info = _latest(db, [r.id for r in rows])
    parents = set(db.scalars(select(ContentSubmission.parent_submission_id).where(ContentSubmission.parent_submission_id.in_([r.id for r in rows])))) if rows else set()
    return [
        ContentSummary(id=r.id, brand_id=r.brand_id, asset_id=r.asset_id, revision_number=r.revision_number, workflow_status=r.workflow_status,
                       is_latest=r.id not in parents, title=r.title, char_count=len(r.content), submitted_by=r.submitted_by, created_at=r.created_at,
                       review_count=info[r.id][0], latest_review=info[r.id][1])
        for r in rows
    ], total


# ------------------------------------------------------------------ reviews
def get_run(db: Session, review_id: uuid.UUID) -> ReviewRun:
    run = db.get(ReviewRun, review_id)
    if run is None:
        raise NotFoundError("Review not found.")
    return run


def finding_reads(db: Session, findings: list[ReviewFinding]) -> list[FindingRead]:
    ids = [f.id for f in findings]
    evidence: dict[uuid.UUID, list[FindingEvidence]] = {i: [] for i in ids}
    if ids:
        for ev in db.scalars(select(FindingEvidence).where(FindingEvidence.finding_id.in_(ids)).order_by(FindingEvidence.created_at, FindingEvidence.id)):
            evidence[ev.finding_id].append(ev)
    return [
        FindingRead(
            id=f.id, review_run_id=f.review_run_id, claim_index=f.claim_index, claim_text=f.claim_text, claim_category=f.claim_category,
            start_offset=f.start_offset, end_offset=f.end_offset, status=f.status, severity=f.severity, explanation=f.explanation,
            recommended_action=f.recommended_action, requires_human_review=f.requires_human_review, method=f.method,
            extraction_method=f.extraction_method, matched_fact_id=f.matched_fact_id, created_at=f.created_at,
            evidence=[EvidenceRead.model_validate(e) for e in evidence[f.id]],
        )
        for f in findings
    ]


def list_findings(db: Session, review_id: uuid.UUID, *, status: str | None, limit: int, offset: int) -> tuple[list[FindingRead], int]:
    get_run(db, review_id)
    cond = [ReviewFinding.review_run_id == review_id]
    if status:
        cond.append(ReviewFinding.status == status)
    total = db.scalar(select(func.count()).select_from(ReviewFinding).where(*cond)) or 0
    rows = list(db.scalars(select(ReviewFinding).where(*cond).order_by(ReviewFinding.claim_index).limit(limit).offset(offset)))
    return finding_reads(db, rows), total


def run_read(db: Session, run: ReviewRun, *, include_findings: bool = False) -> ReviewRunRead:
    counts = _counts(db, [run.id])[run.id]
    summary = run.summary or {}
    findings = None
    if include_findings:
        findings = finding_reads(db, list(db.scalars(select(ReviewFinding).where(ReviewFinding.review_run_id == run.id).order_by(ReviewFinding.claim_index))))
    return ReviewRunRead(
        id=run.id, brand_id=run.brand_id, content_submission_id=run.content_submission_id, status=run.status, analysis_mode=run.analysis_mode,
        content_hash=run.content_hash, requested_by=run.requested_by, started_at=run.started_at, completed_at=run.completed_at,
        provider_name=run.provider_name, model_name=run.model_name, error_code=run.error_code, error_message=run.error_message,
        counts=counts, limitations=list(summary.get("limitations", [])), notes=list(summary.get("notes", [])),
        total_findings=sum(counts.values()), findings=findings,
    )


def list_runs(db: Session, content_id: uuid.UUID) -> list[ReviewRunRead]:
    get_content(db, content_id)
    runs = list(db.scalars(select(ReviewRun).where(ReviewRun.content_submission_id == content_id).order_by(ReviewRun.started_at.desc(), ReviewRun.id)))
    return [run_read(db, r) for r in runs]
