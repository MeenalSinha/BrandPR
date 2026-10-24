"""Approved-fact and source-section retrieval from the existing PostgreSQL tables.

Facts are always filtered by brand_id, so another brand's facts can never support a claim. Each fact carries its
effective state (status combined with validity dates), so only 'current' facts count as evidence.
"""
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.models import ApprovedFact, DocumentSection, SourceDocument
from app.services.facts import effective_state
from app.services.review.text import tokens
from app.services.review.types import FactView

TERMINOLOGY = "terminology"


@dataclass
class KnowledgeBase:
    brand_id: uuid.UUID
    facts: list[FactView]

    @property
    def current_facts(self) -> list[FactView]:
        return [f for f in self.facts if f.effective == "current"]

    def verifiable(self) -> list[FactView]:
        """Facts that describe product truth (everything except terminology rules)."""
        return [f for f in self.facts if f.fact.category != TERMINOLOGY]


def load_knowledge(db: Session, brand_id: uuid.UUID) -> KnowledgeBase:
    today = clock.today()
    rows = db.scalars(select(ApprovedFact).where(ApprovedFact.brand_id == brand_id).order_by(ApprovedFact.created_at, ApprovedFact.id)).all()
    views = [
        FactView(
            fact=f, effective=effective_state(f, today),
            name_tokens=frozenset(tokens(f.name, drop_generic=True)),
            value_tokens=frozenset(tokens(f"{f.value} {f.unit or ''}")),
        )
        for f in rows
    ]
    return KnowledgeBase(brand_id=brand_id, facts=views)


def candidates(kb: KnowledgeBase, claim_text: str) -> list[FactView]:
    """Non-terminology facts whose subject (name) shares a significant word with the claim, best first."""
    claim_tokens = tokens(claim_text)
    scored = []
    for fv in kb.verifiable():
        overlap = len(fv.name_tokens & claim_tokens)
        if overlap:
            scored.append((overlap / max(1, len(fv.name_tokens)), fv))
    scored.sort(key=lambda t: (-t[0], str(t[1].fact.id)))
    return [fv for _, fv in scored]


def loosely_related(kb: KnowledgeBase, claim_text: str, limit: int = 5) -> list[FactView]:
    """Current facts sharing any word with the claim in name, value or conditions. Used to give the model options."""
    claim_tokens = tokens(claim_text)
    scored = []
    for fv in kb.verifiable():
        if fv.effective != "current":
            continue
        pool = fv.name_tokens | fv.value_tokens | tokens(fv.fact.qualifications or "")
        overlap = len(pool & claim_tokens)
        if overlap:
            scored.append((overlap, fv))
    scored.sort(key=lambda t: (-t[0], str(t[1].fact.id)))
    return [fv for _, fv in scored[:limit]]


def best_source_passage(db: Session, brand_id: uuid.UUID, claim_text: str) -> tuple[DocumentSection, str] | None:
    """A real sentence from a processed, non-archived source document that covers (almost) every significant word
    of the claim. It is surfaced only as context for an unsupported claim: it is not an approved fact."""
    wanted = tokens(claim_text)
    if len(wanted) < 3:
        return None
    stmt = (
        select(DocumentSection)
        .join(SourceDocument, SourceDocument.id == DocumentSection.document_id)
        .where(SourceDocument.brand_id == brand_id, SourceDocument.processing_status == "processed", SourceDocument.archived_at.is_(None))
        .order_by(SourceDocument.uploaded_at, DocumentSection.section_index)
    )
    best: tuple[float, DocumentSection, str] | None = None
    for section in db.scalars(stmt):
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", section.text):
            sentence = sentence.strip()
            if not sentence:
                continue
            coverage = len(wanted & tokens(sentence)) / len(wanted)
            if coverage >= 0.75 and (best is None or coverage > best[0]):
                best = (coverage, section, sentence)
    return (best[1], best[2]) if best else None
