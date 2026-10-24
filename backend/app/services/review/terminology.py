"""Deterministic terminology checks driven by current approved terminology facts.

Recognised fact shapes (category 'terminology'):
  * avoided words    name/conditions mention avoid / never use / do not use / prohibited, value is a comma-separated list
  * approved name    name like 'Product name' or 'Brand name'; the value is the exact spelling to use
Any other terminology fact is left for people (it is not guessed at).
"""
import re

from app.models import ApprovedFact
from app.services.review.claims import Claim
from app.services.review.matching import show
from app.services.review.retrieval import TERMINOLOGY, KnowledgeBase
from app.services.review.types import EvidenceSpec, Outcome

AVOID_RE = re.compile(r"\b(avoid|never use|do not use|don't use|must not use|prohibited|banned|forbidden|restricted)\b", re.I)
NAME_RE = re.compile(r"\b(product|brand|company)\s+name\b|\bapproved\s+name\b", re.I)


def avoided_terms(f: ApprovedFact) -> list[str]:
    if not AVOID_RE.search(f"{f.name} {f.qualifications or ''}"):
        return []
    return [t.strip(" '\"") for t in re.split(r"[,;]|\bor\b", f.value) if t.strip(" '\"")]


def check(content: str, kb: KnowledgeBase) -> list[tuple[Claim, Outcome]]:
    found: list[tuple[Claim, Outcome]] = []
    for fv in kb.facts:
        f = fv.fact
        if f.category != TERMINOLOGY or fv.effective != "current":
            continue
        for term in avoided_terms(f):
            for m in re.finditer(rf"(?<![\w-]){re.escape(term)}(?![\w-])", content, re.I):
                claim = Claim(text=content[m.start():m.end()], start=m.start(), end=m.end(), category="terminology")
                found.append((claim, Outcome(
                    "conflicting",
                    f"\u201c{claim.text}\u201d is an avoided term. The approved terminology rule {show(f)} says: {f.qualifications or 'do not use it'}.",
                    f"Remove or replace \u201c{claim.text}\u201d, or ask the brand team for an approved exception.",
                    [EvidenceSpec("conflicts", f, note=f"Terminology rule: avoid \u201c{term}\u201d.")], matched_fact=f, term_kind="avoided",
                )))
        if NAME_RE.search(f.name):
            name = f.value.strip()
            for m in re.finditer(rf"(?<![\w-]){re.escape(name)}(?![\w-])", content, re.I):
                if m.group(0) == name:
                    continue
                claim = Claim(text=m.group(0), start=m.start(), end=m.end(), category="terminology")
                found.append((claim, Outcome(
                    "conflicting",
                    f"The name is written \u201c{m.group(0)}\u201d but the approved spelling is \u201c{name}\u201d ({show(f)}).",
                    f"Write the name exactly as \u201c{name}\u201d.",
                    [EvidenceSpec("conflicts", f, note=f"Approved spelling: {name}")], matched_fact=f, term_kind="casing",
                )))
    return found
