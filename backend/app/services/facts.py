"""Approved-fact rules: validation, provenance, approval lifecycle, history and date logic.

Key rules:
  * Approval status (status) is independent of validity (valid_from / expires_at).
  * effective_state combines both, evaluated today, so an expired fact is never reported as current.
  * A missing expiry date is reported as a warning; it is never silently treated as 'valid forever'.
  * Editing a material field of an active fact returns it to 'proposed' so changed wording is re-approved.
  * Every create / edit / status change appends a fact_revisions row in the same transaction.
  * Phase 3: an edit or status change also records which reviewed content relied on the previous version
    (services/impacts.py), in that same transaction.
"""
import uuid
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailed, field_error
from app.models import ApprovedFact, FactRevision, SourceDocument
from app.models import DocumentSection
from app.schemas.fact import (
    FactCreate, FactRead, FactSourceRead, FactStatusUpdate, FactSummary, FactUpdate,
)
from app.services.brands import get_brand

A = ApprovedFact
MATERIAL_FIELDS = {
    "name", "value", "category", "qualifications", "unit",
    "source_document_id", "source_page", "source_excerpt", "source_note",
}
EDITABLE_FIELDS = MATERIAL_FIELDS | {"owner", "valid_from", "review_date", "expires_at"}
TRANSITIONS: dict[str, set[str]] = {
    "proposed": {"active", "rejected"},
    "active": {"proposed", "expired", "retired"},
    "rejected": {"proposed"},
    "expired": {"active", "retired"},
    "retired": set(),
}
REASON_REQUIRED = {"rejected", "expired", "retired"}
EFFECTIVE_STATES = ("current", "pending", "expired", "unapproved", "retired")
REVIEW_STATES = ("overdue", "due_soon", "scheduled", "unscheduled", "not_applicable")


# ---------------------------------------------------------------- date logic (Python)
def effective_state(fact: ApprovedFact, today: date) -> str:
    if fact.status in ("proposed", "rejected"):
        return "unapproved"
    if fact.status == "retired":
        return "retired"
    if fact.status == "expired":
        return "expired"
    if fact.expires_at is not None and fact.expires_at < today:
        return "expired"
    if fact.valid_from is not None and fact.valid_from > today:
        return "pending"
    return "current"


def review_state(fact: ApprovedFact, today: date, warn_days: int) -> str:
    if fact.status in ("rejected", "retired"):
        return "not_applicable"
    if fact.review_date is None:
        return "unscheduled"
    if fact.review_date < today:
        return "overdue"
    if (fact.review_date - today).days <= warn_days:
        return "due_soon"
    return "scheduled"


# ---------------------------------------------------------------- date logic (SQL, same rules)
def effective_clause(state: str, today: date) -> ColumnElement[bool]:
    expired_by_date = and_(A.status == "active", A.expires_at.is_not(None), A.expires_at < today)
    if state == "unapproved":
        return A.status.in_(("proposed", "rejected"))
    if state == "retired":
        return A.status == "retired"
    if state == "expired":
        return or_(A.status == "expired", expired_by_date)
    if state == "pending":
        return and_(A.status == "active", ~expired_by_date, A.valid_from.is_not(None), A.valid_from > today)
    if state == "current":
        return and_(
            A.status == "active",
            or_(A.expires_at.is_(None), A.expires_at >= today),
            or_(A.valid_from.is_(None), A.valid_from <= today),
        )
    raise ValidationFailed(f"Unknown effective_state '{state}'.")


def review_clause(state: str, today: date, warn_days: int) -> ColumnElement[bool]:
    from datetime import timedelta

    applicable = A.status.in_(("proposed", "active", "expired"))
    horizon = today + timedelta(days=warn_days)
    if state == "not_applicable":
        return A.status.in_(("rejected", "retired"))
    if state == "unscheduled":
        return and_(applicable, A.review_date.is_(None))
    if state == "overdue":
        return and_(applicable, A.review_date < today)
    if state == "due_soon":
        return and_(applicable, A.review_date >= today, A.review_date <= horizon)
    if state == "scheduled":
        return and_(applicable, A.review_date > horizon)
    raise ValidationFailed(f"Unknown review_state '{state}'.")


# ---------------------------------------------------------------- source resolution
def _norm(s: str) -> str:
    return " ".join(s.split()).casefold()


def _resolve_source(db: Session, brand_id: uuid.UUID, v: dict[str, Any]) -> tuple[bool | None, list[dict]]:
    """Validate the cited source against the brand and return (excerpt_verified, errors)."""
    errors: list[dict] = []
    doc_id, page, excerpt, note = v.get("source_document_id"), v.get("source_page"), v.get("source_excerpt"), v.get("source_note")
    if doc_id is None:
        if page is not None:
            errors.append(field_error("source_page", "A page can only be set when a source document is cited."))
        if not note:
            errors.append(field_error("source_note", "Describe the source (for example 'Confirmed by product team, 2026-10-01') when no document is cited."))
        return None, errors
    doc = db.get(SourceDocument, doc_id)
    if doc is None:
        return None, [field_error("source_document_id", "The cited source document does not exist.")]
    if doc.brand_id != brand_id:
        return None, [field_error("source_document_id", "The cited source document belongs to a different brand.")]
    if doc.processing_status != "processed":
        return None, [field_error("source_document_id", "The cited source document has not been processed successfully.")]
    if doc.archived_at is not None:
        return None, [field_error("source_document_id", "The cited source document is archived.")]
    if page is not None:
        if doc.source_type != "pdf":
            errors.append(field_error("source_page", "Page references are only available for PDF documents."))
        elif page > (doc.page_count or 0):
            errors.append(field_error("source_page", f"The document has {doc.page_count} page(s); page {page} does not exist."))
    if errors or not excerpt:
        return None, errors
    if page is not None:
        haystack = db.scalar(
            select(DocumentSection.text).where(DocumentSection.document_id == doc.id, DocumentSection.page_number == page)
        ) or ""
    else:
        haystack = doc.extracted_text or ""
    return _norm(excerpt) in _norm(haystack), []


SOURCE_FIELDS = {"source_document_id", "source_page", "source_excerpt", "source_note"}


def _validate(
    db: Session, brand_id: uuid.UUID, v: dict[str, Any], *, activating: bool = False, check_source: bool = True
) -> bool | None:
    errors: list[dict] = []
    vf, ra, ex = v.get("valid_from"), v.get("review_date"), v.get("expires_at")
    if vf and ex and ex < vf:
        errors.append(field_error("expires_at", "Expiry date must be on or after the valid-from date."))
    if ra and ex and ra > ex:
        errors.append(field_error("review_date", "Review date must be on or before the expiry date."))
    if activating and ex and ex < clock.today():
        errors.append(field_error("expires_at", "The expiry date is in the past. Extend it before approving the fact."))
    verified: bool | None = None
    if check_source:
        verified, source_errors = _resolve_source(db, brand_id, v)
        errors.extend(source_errors)
    if errors:
        raise ValidationFailed("The fact could not be saved.", details=errors)
    return verified


# ---------------------------------------------------------------- history
def _jsonable(value: Any) -> Any:
    if isinstance(value, (date,)) or hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _snapshot(f: ApprovedFact) -> dict[str, Any]:
    cols = [
        "name", "value", "category", "qualifications", "unit", "status", "source_document_id", "source_page",
        "source_excerpt", "source_note", "owner", "valid_from", "review_date", "expires_at", "approved_by",
        "approved_at", "version",
    ]
    return {c: _jsonable(getattr(f, c)) for c in cols}


def _record(db: Session, f: ApprovedFact, action: str, changes: dict, actor: str | None, reason: str | None) -> FactRevision:
    revision = FactRevision(
        fact_id=f.id, revision_number=f.version, action=action, changes=changes, snapshot=_snapshot(f),
        changed_by=actor, change_reason=reason,
    )
    db.add(revision)
    return revision


def _propagate(db: Session, fact: ApprovedFact, revision: FactRevision) -> None:
    """Phase 3: flag content that relied on the previous version. Runs inside the caller's transaction, before commit:
    if recording impacts fails, the fact edit is rolled back with it (never a half-saved change)."""
    from app.services import impacts  # imported here because impacts builds on this module

    impacts.propagate_revision(db, fact, revision)


# ---------------------------------------------------------------- reads
def get_fact(db: Session, fact_id: uuid.UUID, *, lock: bool = False) -> ApprovedFact:
    stmt = select(A).where(A.id == fact_id)
    if lock:
        stmt = stmt.with_for_update()
    fact = db.scalar(stmt)
    if fact is None:
        raise NotFoundError("Fact not found.")
    return fact


def to_read_many(db: Session, facts: list[ApprovedFact]) -> list[FactRead]:
    settings = get_settings()
    today = clock.today()
    doc_ids = {f.source_document_id for f in facts if f.source_document_id}
    docs = {d.id: d for d in db.scalars(select(SourceDocument).where(SourceDocument.id.in_(doc_ids)))} if doc_ids else {}
    out = []
    for f in facts:
        eff, rev = effective_state(f, today), review_state(f, today, settings.review_warning_days)
        warnings: list[str] = []
        if f.status == "active" and eff == "expired":
            warnings.append("expired_by_date")
        if f.status in ("active", "proposed") and f.expires_at is None:
            warnings.append("no_expiry_date")
        if rev == "overdue":
            warnings.append("review_overdue")
        elif rev == "due_soon":
            warnings.append("review_due_soon")
        doc = docs.get(f.source_document_id) if f.source_document_id else None
        if doc is not None and doc.archived_at is not None:
            warnings.append("source_document_archived")
        if f.source_excerpt and f.source_excerpt_verified is False:
            warnings.append("excerpt_not_found_in_source")
        source = (
            FactSourceRead(
                document_id=doc.id, title=doc.title, filename=doc.filename, source_type=doc.source_type,
                processing_status=doc.processing_status, page_count=doc.page_count, archived=doc.archived_at is not None,
            )
            if doc else None
        )
        out.append(
            FactRead(
                id=f.id, brand_id=f.brand_id, name=f.name, value=f.value, category=f.category,
                qualifications=f.qualifications, unit=f.unit, status=f.status, effective_state=eff, review_state=rev,
                warnings=warnings, source_document_id=f.source_document_id, source_page=f.source_page,
                source_excerpt=f.source_excerpt, source_excerpt_verified=f.source_excerpt_verified,
                source_note=f.source_note, provenance="document" if f.source_document_id else "manual", source=source,
                owner=f.owner, valid_from=f.valid_from, review_date=f.review_date, expires_at=f.expires_at,
                approved_by=f.approved_by, approved_at=f.approved_at, version=f.version,
                created_at=f.created_at, updated_at=f.updated_at,
            )
        )
    return out


def to_read(db: Session, fact: ApprovedFact) -> FactRead:
    return to_read_many(db, [fact])[0]


SORTS = {
    "updated_at": A.updated_at.desc(), "name": A.name.asc(), "review_date": A.review_date.asc().nulls_last(),
    "expires_at": A.expires_at.asc().nulls_last(), "created_at": A.created_at.desc(),
}


def list_facts(
    db: Session, brand_id: uuid.UUID, *, limit: int, offset: int, status: str | None = None, category: str | None = None,
    effective: str | None = None, review: str | None = None, review_within_days: int | None = None,
    source_document_id: uuid.UUID | None = None, q: str | None = None, sort: str = "updated_at",
) -> tuple[list[ApprovedFact], int]:
    get_brand(db, brand_id)
    settings, today = get_settings(), clock.today()
    cond: list[ColumnElement[bool]] = [A.brand_id == brand_id]
    if status:
        cond.append(A.status == status)
    if category:
        cond.append(A.category == category)
    if effective:
        cond.append(effective_clause(effective, today))
    if review:
        cond.append(review_clause(review, today, settings.review_warning_days))
    if review_within_days is not None:
        from datetime import timedelta
        cond.append(and_(A.status.in_(("proposed", "active", "expired")), A.review_date.is_not(None),
                         A.review_date <= today + timedelta(days=review_within_days)))
    if source_document_id:
        cond.append(A.source_document_id == source_document_id)
    if q and q.strip():
        like = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
        cond.append(or_(*(col.ilike(like, escape="\\") for col in (A.name, A.value, A.qualifications, A.owner))))
    if sort not in SORTS:
        raise ValidationFailed(f"Unknown sort '{sort}'.", details=[field_error("sort", f"Choose one of: {', '.join(SORTS)}.")])
    total = db.scalar(select(func.count()).select_from(A).where(*cond)) or 0
    rows = db.scalars(select(A).where(*cond).order_by(SORTS[sort], A.id).limit(limit).offset(offset)).all()
    return list(rows), total


def summary(db: Session, brand_id: uuid.UUID) -> FactSummary:
    get_brand(db, brand_id)
    settings, today = get_settings(), clock.today()

    def count(clause: ColumnElement[bool]) -> int:
        return db.scalar(select(func.count()).select_from(A).where(A.brand_id == brand_id, clause)) or 0

    total = db.scalar(select(func.count()).select_from(A).where(A.brand_id == brand_id)) or 0
    return FactSummary(
        total=total,
        by_effective_state={s: count(effective_clause(s, today)) for s in EFFECTIVE_STATES},
        by_review_state={s: count(review_clause(s, today, settings.review_warning_days)) for s in REVIEW_STATES},
        review_warning_days=settings.review_warning_days,
    )


# ---------------------------------------------------------------- writes
def create_fact(db: Session, brand_id: uuid.UUID, data: FactCreate) -> ApprovedFact:
    get_brand(db, brand_id)
    values = data.model_dump(exclude={"actor", "status"})
    verified = _validate(db, brand_id, values, activating=data.status == "active")
    fact = ApprovedFact(brand_id=brand_id, status=data.status, source_excerpt_verified=verified, version=1, **values)
    if data.status == "active":
        fact.approved_by, fact.approved_at = data.actor, clock.now()
    db.add(fact)
    db.flush()
    _record(db, fact, "created", {}, data.actor, None)
    db.commit()
    db.refresh(fact)
    return fact


def update_fact(db: Session, fact_id: uuid.UUID, data: FactUpdate) -> ApprovedFact:
    fact = get_fact(db, fact_id, lock=True)
    if data.expected_version is not None and data.expected_version != fact.version:
        raise ConflictError(
            "This fact was changed by someone else. Reload it and apply your edit again.", code="version_conflict"
        )
    sent = data.model_dump(exclude_unset=True)
    for required in ("name", "value"):
        if required in sent and sent[required] is None:
            raise ValidationFailed("The fact could not be saved.", details=[field_error(required, "Must not be empty.")])
    proposed = {k: sent[k] for k in sent if k in EDITABLE_FIELDS and sent[k] != getattr(fact, k)}
    if not proposed:
        return fact
    merged = {k: getattr(fact, k) for k in EDITABLE_FIELDS} | proposed
    # Only re-resolve the source when a source field changed, so unrelated edits (owner, dates) still
    # work after the cited document has been archived.
    source_changed = bool(SOURCE_FIELDS & proposed.keys())
    verified = _validate(db, fact.brand_id, merged, check_source=source_changed)
    if not source_changed:
        verified = fact.source_excerpt_verified
    changes = {k: {"old": _jsonable(getattr(fact, k)), "new": _jsonable(v)} for k, v in proposed.items()}
    for k, v in proposed.items():
        setattr(fact, k, v)
    fact.source_excerpt_verified = verified
    if fact.status == "active" and MATERIAL_FIELDS & proposed.keys():
        changes["status"] = {"old": "active", "new": "proposed"}
        fact.status, fact.approved_by, fact.approved_at = "proposed", None, None
    fact.version += 1
    revision = _record(db, fact, "updated", changes, data.actor, data.change_reason)
    _propagate(db, fact, revision)
    db.commit()
    db.refresh(fact)
    return fact


def change_status(db: Session, fact_id: uuid.UUID, data: FactStatusUpdate) -> ApprovedFact:
    fact = get_fact(db, fact_id, lock=True)
    if data.expected_version is not None and data.expected_version != fact.version:
        raise ConflictError("This fact was changed by someone else. Reload it and try again.", code="version_conflict")
    if data.status == fact.status:
        return fact
    if data.status not in TRANSITIONS[fact.status]:
        raise ValidationFailed(
            f"A {fact.status} fact cannot become {data.status}.",
            details=[field_error("status", f"Allowed from {fact.status}: {', '.join(sorted(TRANSITIONS[fact.status])) or 'none'}.")],
        )
    reason = (data.reason or "").strip() or None
    if data.status in REASON_REQUIRED and not reason:
        raise ValidationFailed("A reason is required.", details=[field_error("reason", f"Give a reason for marking a fact {data.status}.")])
    old = fact.status
    if data.status == "active":
        _validate(db, fact.brand_id, {k: getattr(fact, k) for k in EDITABLE_FIELDS}, activating=True, check_source=False)
        fact.approved_by, fact.approved_at = data.actor, clock.now()
    elif data.status == "proposed":
        fact.approved_by, fact.approved_at = None, None
    fact.status = data.status
    fact.version += 1
    revision = _record(db, fact, "status_changed", {"status": {"old": old, "new": data.status}}, data.actor, reason)
    _propagate(db, fact, revision)
    db.commit()
    db.refresh(fact)
    return fact


def list_revisions(db: Session, fact_id: uuid.UUID) -> list[FactRevision]:
    get_fact(db, fact_id)
    return list(db.scalars(select(FactRevision).where(FactRevision.fact_id == fact_id).order_by(FactRevision.revision_number)))
