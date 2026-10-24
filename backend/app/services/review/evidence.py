"""Turns an EvidenceSpec into a persisted-ready FindingEvidence row built only from real records.

Nothing here accepts a model-supplied citation. The fact, document, section and page come from the database, and the
saved excerpt is re-verified against the stored section text at review time.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.models import DocumentSection, FindingEvidence, SourceDocument
from app.services.facts import effective_state
from app.services.review.text import norm_ws
from app.services.review.types import EvidenceSpec


def _find_section(db: Session, doc: SourceDocument, page: int | None, excerpt: str | None) -> DocumentSection | None:
    if page is not None:
        return db.scalar(select(DocumentSection).where(DocumentSection.document_id == doc.id, DocumentSection.page_number == page))
    if excerpt:
        target = norm_ws(excerpt)
        for section in db.scalars(select(DocumentSection).where(DocumentSection.document_id == doc.id).order_by(DocumentSection.section_index)):
            if target in norm_ws(section.text):
                return section
    return None


def build(db: Session, brand_id: uuid.UUID, finding_id: uuid.UUID, spec: EvidenceSpec) -> FindingEvidence:
    row = FindingEvidence(brand_id=brand_id, finding_id=finding_id, role=spec.role, relation_note=spec.note)
    if spec.fact is None:
        # related_source: a verbatim sentence from a stored section of a brand document.
        assert spec.section is not None and spec.excerpt is not None
        doc = db.get(SourceDocument, spec.section.document_id)
        assert doc is not None and doc.brand_id == brand_id
        row.source_document_id, row.document_section_id = doc.id, spec.section.id
        row.source_title, row.source_page = doc.title, spec.section.page_number
        row.excerpt = spec.excerpt
        row.excerpt_verified = norm_ws(spec.excerpt) in norm_ws(spec.section.text)
        return row

    f = spec.fact
    assert f.brand_id == brand_id, "evidence must come from the same brand"
    row.fact_id = f.id
    row.fact_name, row.fact_value, row.fact_qualifications = f.name, f.value if not f.unit else f"{f.value} {f.unit}", f.qualifications
    row.fact_status, row.fact_version = f.status, f.version
    row.fact_effective_state = effective_state(f, clock.today())
    notes = [spec.note] if spec.note else []
    doc = db.get(SourceDocument, f.source_document_id) if f.source_document_id else None
    if doc is not None and doc.brand_id == brand_id:
        row.source_document_id, row.source_title = doc.id, doc.title
        section = _find_section(db, doc, f.source_page, f.source_excerpt)
        row.source_page = f.source_page or (section.page_number if section else None)
        if section is not None:
            row.document_section_id = section.id
        row.excerpt = f.source_excerpt
        if f.source_excerpt:
            row.excerpt_verified = section is not None and norm_ws(f.source_excerpt) in norm_ws(section.text)
        if doc.archived_at is not None:
            notes.append("The source document is archived.")
    else:
        notes.append(f"Manual source: {f.source_note}" if f.source_note else "No source document is cited for this fact.")
    row.relation_note = " ".join(notes) or None
    return row
