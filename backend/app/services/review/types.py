from dataclasses import dataclass, field

from app.models import ApprovedFact, DocumentSection


@dataclass
class FactView:
    """An approved-facts row plus its effective state today and pre-computed subject tokens."""

    fact: ApprovedFact
    effective: str  # current | pending | expired | unapproved | retired
    name_tokens: frozenset[str]
    value_tokens: frozenset[str]


@dataclass
class EvidenceSpec:
    role: str  # supports | conflicts | outdated | context | related_source
    fact: ApprovedFact | None = None
    section: DocumentSection | None = None
    excerpt: str | None = None  # for related_source: a verbatim sentence from the section
    note: str | None = None


@dataclass
class Outcome:
    status: str
    explanation: str
    recommended_action: str | None
    evidence: list[EvidenceSpec] = field(default_factory=list)
    matched_fact: ApprovedFact | None = None
    method: str = "deterministic"
    severity_hint: str | None = None  # terminology findings set their own policy key
    needs_ai: bool = False  # deterministic result could be improved by a semantic check
    ai_candidates: list[FactView] = field(default_factory=list)
    term_kind: str | None = None
