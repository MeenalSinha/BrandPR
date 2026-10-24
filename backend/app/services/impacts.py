"""Claim Ledger fact-change propagation (Phase 3).

When an approved fact that an earlier review relied on changes or lapses, the content behind that review is flagged
for another review by writing a FactChangeImpact. Nothing else is touched: content, review runs, findings and
evidence are never edited, and nothing is approved or rejected automatically.

Two kinds of event create impacts:

  fact_revision  An explicit edit or status change recorded in fact_revisions. propagate_revision() is called by
                 facts.update_fact / facts.change_status BEFORE their commit, so the fact, its revision and its
                 impacts are saved in one transaction. If recording impacts fails, the fact change is rolled back
                 and the caller sees an error; propagation never fails silently.

  fact_expiry    A fact stored as 'active' whose expires_at has passed. No revision exists for this, so
                 detect_expired() sweeps on demand whenever the impact list is requested. It is NOT a background job:
                 impacts appear the first time someone asks after the expiry date. The expiry date is inclusive,
                 exactly like facts.effective_state.

What counts as "relied on the fact":
  * a finding_evidence row with fact_id = the fact, whose saved fact_effective_state was 'current' and whose saved
    fact_version is older than the new version, inside a completed review run; or
  * a finding with matched_fact_id = the fact that has no evidence row for it (for example an undecided AI match).
    The version is then inferred from the revision timeline: the last revision saved at or before the run started,
    and only if that version was approved and valid on that day.
  Failed, pending and running runs never count. Facts of other brands never match (every query is brand-scoped and
  the foreign keys are composite).

Duplicate prevention (enforced by PostgreSQL, not only by checks here):
  * UNIQUE (trigger_key, content_submission_id): one impact per content item per event, safe under concurrency
    because the insert is ON CONFLICT DO NOTHING.
  * UNIQUE (finding_id, fact_id) on the link table: a historical finding is attributed to the first event that
    invalidated the fact it relied on. Later events only flag findings from reviews made after the fact was
    approved again.
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import NotFoundError
from app.models import (
    ApprovedFact, ContentSubmission, FactChangeImpact, FactChangeImpactFinding, FactChangeImpactResolution, FactRevision, FindingEvidence,
    ReviewFinding, ReviewRun,
)
from app.schemas.impact import (
    ImpactContentBrief, ImpactDetail, ImpactFactBrief, ImpactFindingRead, ImpactRead, ImpactResolutionBrief, ImpactRevisionRead, ImpactSummary,
)
from app.schemas.review import ReviewRunBrief
from app.services import facts as fact_svc
from app.services.brands import get_brand
from app.services.content import _brief, _counts, finding_reads

logger = logging.getLogger("brandpr.impacts")

# Fields whose change alters the meaning or the evidence of an approved claim.
CONTENT_FIELDS = (
    "name", "value", "category", "unit", "qualifications", "source_document_id", "source_page", "source_excerpt", "source_note",
)
# Validity dates matter only when the change makes the fact stop being current.
DATE_FIELDS = ("valid_from", "expires_at")
# Administrative metadata: never creates an impact (owner, review reminder date).
ADMINISTRATIVE_FIELDS = ("owner", "review_date")
COMPLETED_RUNS = ("completed", "completed_limited")
FIELD_LABELS = {
    "name": "name", "value": "value", "category": "category", "unit": "unit", "qualifications": "conditions",
    "source_document_id": "source document", "source_page": "source page", "source_excerpt": "source excerpt",
    "source_note": "source note", "valid_from": "valid-from date", "expires_at": "expiry date", "status": "approval status",
}
STATUS_WORDS = {"proposed": "proposed", "active": "approved", "rejected": "rejected", "expired": "marked expired", "retired": "retired"}


# ------------------------------------------------------------------ rules (pure functions)
def _as_date(value: Any) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) and value else None


def state_of_snapshot(snapshot: dict[str, Any], today: date) -> str:
    """Effective state of a stored revision snapshot, using the same rules as facts.effective_state."""
    stand_in = SimpleNamespace(
        status=snapshot.get("status"), expires_at=_as_date(snapshot.get("expires_at")), valid_from=_as_date(snapshot.get("valid_from")),
    )
    return fact_svc.effective_state(stand_in, today)  # type: ignore[arg-type]


def _short(value: Any, limit: int = 70) -> str:
    text = "not set" if value in (None, "") else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def value_text(snapshot: dict[str, Any]) -> str:
    value = str(snapshot.get("value") or "")
    unit = snapshot.get("unit")
    return f"{value} {unit}" if unit else value


@dataclass(frozen=True)
class Assessment:
    change_type: str
    material_fields: tuple[str, ...]
    before_state: str
    after_state: str
    headline: str


def assess_revision(before: dict[str, Any], after: dict[str, Any], today: date) -> Assessment | None:
    """Decide whether the change from `before` to `after` (consecutive revision snapshots) invalidates earlier reviews.

    An impact is possible only if the fact WAS current approved evidence before the change. Then:
      * a change to any CONTENT_FIELDS value means earlier reviews saw different evidence  -> material_edit
      * otherwise, if the fact is no longer current (status withdrawn)                     -> no_longer_approved
      * otherwise, if a date change made it expired or not yet valid                       -> validity_changed
      * anything else (owner, review reminder date, extending a date) creates no impact.
    """
    before_state, after_state = state_of_snapshot(before, today), state_of_snapshot(after, today)
    if before_state != "current":
        return None
    name = after.get("name") or before.get("name") or "Fact"
    changed_content = tuple(f for f in CONTENT_FIELDS if before.get(f) != after.get(f))
    status_changed = before.get("status") != after.get("status")
    if changed_content:
        parts = []
        for f in changed_content:
            if f == "value" or (f == "unit" and "value" not in changed_content):
                parts.append(f"value changed from \"{_short(value_text(before))}\" to \"{_short(value_text(after))}\"")
            elif f == "unit":
                continue  # already shown together with the value
            elif f in ("source_document_id", "source_page"):
                parts.append(f"{FIELD_LABELS[f]} changed")
            else:
                parts.append(f"{FIELD_LABELS[f]} changed from \"{_short(before.get(f))}\" to \"{_short(after.get(f))}\"")
        headline = f"{name}: " + "; ".join(parts)
        if after_state != "current":
            headline += f"; it is no longer current approved evidence ({STATUS_WORDS.get(after.get('status'), after.get('status'))})"
        return Assessment("material_edit", changed_content, before_state, after_state, headline)
    if after_state != "current" and status_changed:
        return Assessment(
            "no_longer_approved", (), before_state, after_state,
            f"{name}: approval status changed from {STATUS_WORDS.get(before.get('status'), before.get('status'))} to "
            f"{STATUS_WORDS.get(after.get('status'), after.get('status'))}, so it is no longer current approved evidence",
        )
    if after_state != "current":
        changed_dates = [f for f in DATE_FIELDS if before.get(f) != after.get(f)]
        if changed_dates:
            detail = "; ".join(f"{FIELD_LABELS[f]} changed from {_short(before.get(f))} to {_short(after.get(f))}" for f in changed_dates)
            return Assessment("validity_changed", (), before_state, after_state, f"{name}: {detail}, so the fact is no longer valid today ({after_state})")
    return None


def _reason(headline: str) -> str:
    return (
        f"{headline}. This content was reviewed against an earlier version of this fact that is no longer the current "
        "approved evidence, so its claims about this fact may now be wrong or unsupported. Another review is recommended. "
        "BrandPR has not changed, approved or rejected anything automatically."
    )


# ------------------------------------------------------------------ dependency query
@dataclass
class Dependent:
    content_id: uuid.UUID
    run_id: uuid.UUID
    run_started_at: datetime
    finding_id: uuid.UUID
    evidence_id: uuid.UUID | None
    relied_version: int
    basis: str


def _find_dependents(db: Session, brand_id: uuid.UUID, fact_id: uuid.UUID, version_limit: int) -> list[Dependent]:
    """Historical findings that relied on `fact_id` at a version below `version_limit` and are not yet attributed
    to an earlier impact. Uses ix_finding_evidence_fact and ix_review_findings_matched_fact; never scans all content."""
    FE, RF, RR, LK = FindingEvidence, ReviewFinding, ReviewRun, FactChangeImpactFinding
    already = exists().where(LK.finding_id == RF.id, LK.fact_id == fact_id)

    by_evidence = db.execute(
        select(FE.id, FE.fact_version, RF.id, RR.id, RR.started_at, RR.content_submission_id)
        .join(RF, RF.id == FE.finding_id).join(RR, RR.id == RF.review_run_id)
        .where(
            FE.fact_id == fact_id, FE.brand_id == brand_id, RR.status.in_(COMPLETED_RUNS), FE.fact_effective_state == "current",
            FE.fact_version.is_not(None), FE.fact_version < version_limit, ~already,
        )
        .order_by(RR.started_at, RF.claim_index, FE.created_at, FE.id)
    ).all()
    found: dict[uuid.UUID, Dependent] = {}
    for ev_id, version, finding_id, run_id, started_at, content_id in by_evidence:
        found.setdefault(finding_id, Dependent(content_id, run_id, started_at, finding_id, ev_id, version, "evidence"))

    has_evidence = exists().where(FE.finding_id == RF.id, FE.fact_id == fact_id)
    by_match = db.execute(
        select(RF.id, RR.id, RR.started_at, RR.content_submission_id)
        .join(RR, RR.id == RF.review_run_id)
        .where(RF.matched_fact_id == fact_id, RF.brand_id == brand_id, RR.status.in_(COMPLETED_RUNS), ~has_evidence, ~already)
        .order_by(RR.started_at, RF.claim_index)
    ).all()
    if by_match:
        timeline = db.execute(
            select(FactRevision.revision_number, FactRevision.created_at, FactRevision.snapshot)
            .where(FactRevision.fact_id == fact_id).order_by(FactRevision.revision_number)
        ).all()
        for finding_id, run_id, started_at, content_id in by_match:
            in_force = [r for r in timeline if r.created_at <= started_at]
            if not in_force:
                continue
            last = in_force[-1]
            if last.revision_number >= version_limit or state_of_snapshot(last.snapshot, started_at.date()) != "current":
                continue
            found.setdefault(finding_id, Dependent(content_id, run_id, started_at, finding_id, None, last.revision_number, "matched_fact"))
    return list(found.values())


# ------------------------------------------------------------------ creating impacts
def _record_event(
    db: Session, *, fact: ApprovedFact, trigger_type: str, trigger_key: str, revision_id: uuid.UUID | None, change_type: str,
    current_version: int, version_limit: int, new_snapshot: dict[str, Any], changes: dict[str, Any], headline: str,
    before_state: str, after_state: str, material_fields: tuple[str, ...] = (),
) -> list[FactChangeImpact]:
    """Create one impact per affected content item for this event. Safe to call repeatedly and concurrently."""
    dependents = _find_dependents(db, fact.brand_id, fact.id, version_limit)
    if not dependents:
        return []
    by_content: dict[uuid.UUID, list[Dependent]] = {}
    for d in dependents:
        by_content.setdefault(d.content_id, []).append(d)
    needed = {d.relied_version for d in dependents}
    history = {
        number: snapshot for number, snapshot in db.execute(
            select(FactRevision.revision_number, FactRevision.snapshot).where(FactRevision.fact_id == fact.id, FactRevision.revision_number.in_(needed))
        )
    }
    created: list[uuid.UUID] = []
    for content_id, deps in by_content.items():
        source = max(deps, key=lambda d: (d.run_started_at, str(d.run_id)))
        previous_version = max(d.relied_version for d in deps if d.run_id == source.run_id)
        summary = {
            "headline": headline, "material_fields": list(material_fields), "changes": changes,
            "before_effective_state": before_state, "after_effective_state": after_state,
            "previous_snapshot": history.get(previous_version, {}), "new_snapshot": new_snapshot,
        }
        inserted = db.execute(
            pg_insert(FactChangeImpact).values(
                brand_id=fact.brand_id, fact_id=fact.id, content_submission_id=content_id, fact_revision_id=revision_id,
                trigger_type=trigger_type, trigger_key=trigger_key, change_type=change_type, previous_fact_version=previous_version,
                current_fact_version=max(current_version, previous_version), source_review_run_id=source.run_id,
                change_summary=summary, reason=_reason(headline), status="needs_review",
            ).on_conflict_do_nothing(index_elements=["trigger_key", "content_submission_id"]).returning(FactChangeImpact.id)
        ).scalar()
        if inserted is None:
            continue  # this event already produced an impact for this content item
        links = db.execute(
            pg_insert(FactChangeImpactFinding).values([
                dict(brand_id=fact.brand_id, impact_id=inserted, finding_id=d.finding_id, fact_id=fact.id, review_run_id=d.run_id,
                     evidence_id=d.evidence_id, match_basis=d.basis, relied_fact_version=d.relied_version)
                for d in deps
            ]).on_conflict_do_nothing(index_elements=["finding_id", "fact_id"]).returning(FactChangeImpactFinding.finding_id)
        ).all()
        if not links:  # every finding was attributed concurrently by another event; an impact without findings is meaningless
            db.execute(delete(FactChangeImpact).where(FactChangeImpact.id == inserted))
            continue
        created.append(inserted)
    if not created:
        return []
    return list(db.scalars(select(FactChangeImpact).where(FactChangeImpact.id.in_(created)).order_by(FactChangeImpact.created_at, FactChangeImpact.id)))


def _record_expiry(db: Session, fact: ApprovedFact, snapshot: dict[str, Any], version: int, expires_at: date) -> list[FactChangeImpact]:
    headline = f"{fact.name}: approval lapsed because its expiry date ({expires_at.isoformat()}, inclusive) has passed"
    return _record_event(
        db, fact=fact, trigger_type="fact_expiry", trigger_key=f"expiry:{fact.id}:{expires_at.isoformat()}", revision_id=None,
        change_type="expired", current_version=version, version_limit=version + 1, new_snapshot=snapshot,
        changes={"expires_at": {"old": expires_at.isoformat(), "new": expires_at.isoformat()}}, headline=headline,
        before_state="current", after_state="expired",
    )


def propagate_revision(db: Session, fact: ApprovedFact, revision: FactRevision) -> list[FactChangeImpact]:
    """Record impacts for one fact revision. Does NOT commit: the caller commits the fact, revision and impacts together.

    Returns only impacts created by this call; calling it again for the same revision creates nothing new.
    """
    if revision.action == "created" or revision.revision_number < 2:
        return []
    db.flush()
    before_row = db.scalar(select(FactRevision).where(FactRevision.fact_id == fact.id, FactRevision.revision_number == revision.revision_number - 1))
    if before_row is None:
        raise RuntimeError(f"Revision {revision.revision_number - 1} of fact {fact.id} is missing; cannot assess the change.")
    before, today = before_row.snapshot, clock.today()
    created: list[FactChangeImpact] = []
    # If the fact had already lapsed by date before this edit, that lapse is recorded now. Otherwise an edit that
    # moves the fact to 'proposed' (or extends the date) would hide it from the expiry sweep forever.
    lapsed = _as_date(before.get("expires_at"))
    if before.get("status") == "active" and lapsed is not None and lapsed < today:
        created += _record_expiry(db, fact, before, before_row.revision_number, lapsed)
    assessment = assess_revision(before, revision.snapshot, today)
    if assessment is None:
        return created
    created += _record_event(
        db, fact=fact, trigger_type="fact_revision", trigger_key=f"revision:{revision.id}", revision_id=revision.id,
        change_type=assessment.change_type, current_version=revision.revision_number, version_limit=revision.revision_number,
        new_snapshot=revision.snapshot, changes=revision.changes, headline=assessment.headline,
        before_state=assessment.before_state, after_state=assessment.after_state, material_fields=assessment.material_fields,
    )
    if created:
        logger.info("Fact %s revision %s flagged %d content item(s)", fact.id, revision.revision_number, len(created))
    return created


def propagate_revision_by_id(db: Session, revision_id: uuid.UUID) -> list[FactChangeImpact]:
    """Re-run propagation for a stored revision (safe to repeat) and commit."""
    revision = db.get(FactRevision, revision_id)
    if revision is None:
        raise NotFoundError("Fact revision not found.")
    fact = fact_svc.get_fact(db, revision.fact_id, lock=True)
    created = propagate_revision(db, fact, revision)
    db.commit()
    return created


def detect_expired(db: Session, brand_id: uuid.UUID) -> int:
    """On-demand expiry sweep for one brand. Idempotent. Commits. Returns the number of impacts created."""
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"fact_expiry:{brand_id}"))))  # serialise concurrent sweeps per brand
    today = clock.today()
    A = ApprovedFact
    has_history = or_(
        exists().where(FindingEvidence.fact_id == A.id), exists().where(ReviewFinding.matched_fact_id == A.id),
    )
    # SKIP LOCKED: a fact being edited right now records its own lapse when that edit is saved (propagate_revision).
    expired = db.scalars(
        select(A).where(A.brand_id == brand_id, A.status == "active", A.expires_at.is_not(None), A.expires_at < today, has_history)
        .order_by(A.created_at, A.id).with_for_update(skip_locked=True, of=A)
    ).all()
    created = 0
    for fact in expired:
        assert fact.expires_at is not None
        created += len(_record_expiry(db, fact, fact_svc._snapshot(fact), fact.version, fact.expires_at))
    db.commit()
    if created:
        logger.info("Expiry sweep for brand %s flagged %d content item(s)", brand_id, created)
    return created


# ------------------------------------------------------------------ reads
def _display_value(fact: ApprovedFact) -> str:
    return f"{fact.value} {fact.unit}" if fact.unit else fact.value


def _reads(db: Session, rows: list[FactChangeImpact]) -> list[ImpactRead]:
    if not rows:
        return []
    today = clock.today()
    impact_ids = [r.id for r in rows]
    facts = {f.id: f for f in db.scalars(select(ApprovedFact).where(ApprovedFact.id.in_({r.fact_id for r in rows})))}
    contents = {c.id: c for c in db.scalars(select(ContentSubmission).where(ContentSubmission.id.in_({r.content_submission_id for r in rows})))}
    runs = {r.id: r for r in db.scalars(select(ReviewRun).where(ReviewRun.id.in_({r.source_review_run_id for r in rows})))}
    link_rows = db.execute(
        select(FactChangeImpactFinding.impact_id, FactChangeImpactFinding.review_run_id, ReviewFinding.claim_text, ReviewFinding.start_offset, ReviewFinding.claim_index)
        .join(ReviewFinding, ReviewFinding.id == FactChangeImpactFinding.finding_id)
        .where(FactChangeImpactFinding.impact_id.in_(impact_ids)).order_by(ReviewFinding.start_offset, ReviewFinding.claim_index)
    ).all()
    counts: dict[uuid.UUID, int] = {}
    first_claim: dict[uuid.UUID, str] = {}
    by_id = {r.id: r for r in rows}
    for impact_id, run_id, claim, _start, _idx in link_rows:
        counts[impact_id] = counts.get(impact_id, 0) + 1
        if run_id == by_id[impact_id].source_review_run_id and impact_id not in first_claim:
            first_claim[impact_id] = claim
    latest = dict(db.execute(
        select(ReviewRun.content_submission_id, func.max(ReviewRun.started_at))
        .where(ReviewRun.content_submission_id.in_(list(contents)), ReviewRun.status.in_(COMPLETED_RUNS)).group_by(ReviewRun.content_submission_id)
    ).all())
    asset_ids = {c.asset_id for c in contents.values()}
    tips: dict[uuid.UUID, ContentSubmission] = {}
    revision_numbers: dict[uuid.UUID, int] = {}
    for rev in db.scalars(select(ContentSubmission).where(ContentSubmission.asset_id.in_(asset_ids)).order_by(ContentSubmission.revision_number)):
        tips[rev.asset_id] = rev
        revision_numbers[rev.id] = rev.revision_number
    resolutions = {x.impact_id: x for x in db.scalars(select(FactChangeImpactResolution).where(FactChangeImpactResolution.impact_id.in_(impact_ids)))}
    out: list[ImpactRead] = []
    for r in rows:
        fact, content, run = facts[r.fact_id], contents[r.content_submission_id], runs[r.source_review_run_id]
        res = resolutions.get(r.id)
        tip = tips[content.asset_id]
        summary = r.change_summary or {}
        newest = latest.get(r.content_submission_id)
        out.append(ImpactRead(
            id=r.id, brand_id=r.brand_id, status=r.status, trigger_type=r.trigger_type, change_type=r.change_type,
            headline=summary.get("headline", ""), reason=r.reason, detected_at=r.created_at,
            fact=ImpactFactBrief(
                id=fact.id, name=fact.name, status=fact.status, effective_state=fact_svc.effective_state(fact, today),
                version=fact.version, value=fact.value, unit=fact.unit,
            ),
            previous_fact_version=r.previous_fact_version, current_fact_version=r.current_fact_version,
            previous_value=value_text(summary.get("previous_snapshot", {})), current_value=_display_value(fact),
            content=ImpactContentBrief(
                id=content.id, title=content.title, created_at=content.created_at, asset_id=content.asset_id, revision_number=content.revision_number,
                latest_revision_id=tip.id, latest_revision_number=tip.revision_number, latest_revision_status=tip.workflow_status,
            ),
            resolution=ImpactResolutionBrief(
                action=res.action, actor=res.actor, rationale=res.rationale, created_at=res.created_at, resolving_submission_id=res.resolving_submission_id,
                resolving_revision_number=revision_numbers.get(res.resolving_submission_id) if res.resolving_submission_id else None,
                resolving_review_run_id=res.resolving_review_run_id,
            ) if res else None,
            source_review_run_id=r.source_review_run_id, source_review_started_at=run.started_at,
            affected_claim=first_claim.get(r.id), affected_finding_count=counts.get(r.id, 0),
            latest_review_started_at=newest, reviewed_since_detection=newest is not None and newest > r.created_at,
        ))
    return out


def list_impacts(
    db: Session, brand_id: uuid.UUID, *, limit: int, offset: int, fact_id: uuid.UUID | None = None, status: str | None = None,
    trigger_type: str | None = None, content_id: uuid.UUID | None = None, sweep: bool = True,
) -> tuple[list[ImpactRead], int]:
    get_brand(db, brand_id)
    if fact_id is not None:
        fact = db.get(ApprovedFact, fact_id)
        if fact is None or fact.brand_id != brand_id:
            raise NotFoundError("Fact not found for this brand.")
    if sweep:
        detect_expired(db, brand_id)  # a failure here propagates: an unreadable ledger is never shown as an empty one
    cond = [FactChangeImpact.brand_id == brand_id]
    if fact_id is not None:
        cond.append(FactChangeImpact.fact_id == fact_id)
    if status:
        cond.append(FactChangeImpact.status == status)
    if trigger_type:
        cond.append(FactChangeImpact.trigger_type == trigger_type)
    if content_id is not None:
        cond.append(FactChangeImpact.content_submission_id == content_id)
    total = db.scalar(select(func.count()).select_from(FactChangeImpact).where(*cond)) or 0
    rows = list(db.scalars(
        select(FactChangeImpact).where(*cond).order_by(FactChangeImpact.created_at.desc(), FactChangeImpact.id).limit(limit).offset(offset)
    ))
    return _reads(db, rows), total


def list_for_fact(db: Session, fact_id: uuid.UUID, *, limit: int, offset: int, status: str | None, trigger_type: str | None) -> tuple[list[ImpactRead], int]:
    fact = fact_svc.get_fact(db, fact_id)
    return list_impacts(db, fact.brand_id, limit=limit, offset=offset, fact_id=fact_id, status=status, trigger_type=trigger_type)


def summary(db: Session, brand_id: uuid.UUID) -> ImpactSummary:
    get_brand(db, brand_id)
    detect_expired(db, brand_id)
    I = FactChangeImpact
    base = (I.brand_id == brand_id, I.status == "needs_review")

    def distinct(column, *extra) -> int:
        return db.scalar(select(func.count(func.distinct(column))).where(*base, *extra)) or 0

    def total(status: str | None = None) -> int:
        cond = [I.brand_id == brand_id] + ([I.status == status] if status else [])
        return db.scalar(select(func.count()).select_from(I).where(*cond)) or 0

    return ImpactSummary(
        open_impacts=db.scalar(select(func.count()).select_from(I).where(*base)) or 0,
        resolved_impacts=total("resolved"), dismissed_impacts=total("dismissed"), total_impacts=total(),
        facts_with_changes=distinct(I.fact_id), content_needing_review=distinct(I.content_submission_id),
        expiry_affected_content=distinct(I.content_submission_id, I.trigger_type == "fact_expiry"),
        revision_affected_content=distinct(I.content_submission_id, I.trigger_type == "fact_revision"),
    )


def get_impact(db: Session, impact_id: uuid.UUID) -> ImpactDetail:
    row = db.get(FactChangeImpact, impact_id)
    if row is None:
        raise NotFoundError("Impact not found.")
    base = _reads(db, [row])[0]
    links = db.execute(
        select(FactChangeImpactFinding, ReviewFinding)
        .join(ReviewFinding, ReviewFinding.id == FactChangeImpactFinding.finding_id)
        .where(FactChangeImpactFinding.impact_id == row.id).order_by(ReviewFinding.start_offset, ReviewFinding.claim_index)
    ).all()
    reads = finding_reads(db, [f for _, f in links])
    run_ids = list({link.review_run_id for link, _ in links})
    run_rows = {r.id: r for r in db.scalars(select(ReviewRun).where(ReviewRun.id.in_(run_ids)))}
    counts = _counts(db, run_ids)
    findings = [
        ImpactFindingRead(
            finding=read, match_basis=link.match_basis, relied_fact_version=link.relied_fact_version,
            review_run=_brief(run_rows[link.review_run_id], counts[link.review_run_id]),
        )
        for (link, _), read in zip(links, reads)
    ]
    revision = db.get(FactRevision, row.fact_revision_id) if row.fact_revision_id else None
    summary_json = row.change_summary or {}
    fact = db.get(ApprovedFact, row.fact_id)
    assert fact is not None
    return ImpactDetail(
        **base.model_dump(), change_summary=summary_json, previous_snapshot=summary_json.get("previous_snapshot", {}),
        new_snapshot=summary_json.get("new_snapshot", {}), current_fact=fact_svc.to_read(db, fact),
        trigger_revision=ImpactRevisionRead(
            id=revision.id, revision_number=revision.revision_number, action=revision.action, changes=revision.changes,
            changed_by=revision.changed_by, change_reason=revision.change_reason, created_at=revision.created_at,
        ) if revision else None,
        findings=findings,
    )
