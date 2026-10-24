"""Evidence matching and claim classification. Pure functions: no database access, no model calls.

Statuses
  supported    a current approved fact substantiates the claim, including its conditions
  conflicting  a current approved fact contradicts the claim
  outdated     the claim matches a fact that has expired or been retired (or superseded by a newer fact)
  uncertain    evidence exists but the relationship cannot be resolved (qualification omitted, units differ,
               values only partly comparable, facts disagree, or a possible paraphrase)
  unsupported  no current approved evidence was found. This does NOT mean the claim is false.

Only facts whose effective state is 'current' can support or contradict a claim.
"""
import re
from dataclasses import dataclass

from app.models import ApprovedFact
from app.services.review.claims import COMPARATIVE_RE, Claim
from app.services.review.text import Quantity, comparable, fact_quantity, norm_ws, parse_quantities, to_base, tokens
from app.services.review.types import EvidenceSpec, FactView, Outcome

QUALIFIED_CATEGORIES = {"product_spec", "approved_claim", "pricing", "legal_disclaimer"}
QUALIFICATION_COVERAGE = 0.6
CONDITION_MARKERS = re.compile(r"\b(real[- ]world|typical use|everyday use|normal use|heavy use|all[- ]day|in practice)\b", re.I)


@dataclass
class FactResult:
    kind: str  # match | match_unqualified | conflict | narrower | broader | unclear | text_match | text_unqualified | text_probable | none
    detail: str = ""
    missing: str | None = None
    claim_quantity: Quantity | None = None


def show(f: ApprovedFact) -> str:
    value = f"{f.value} {f.unit}" if f.unit and re.fullmatch(r"\d[\d,]*(?:\.\d+)?", f.value.strip()) else f.value
    return f"\u201c{f.name}: {value}\u201d"


# ------------------------------------------------------------------ qualification checks
def lead_clause(qualifications: str) -> str:
    return re.split(r"[:;.]", qualifications, maxsplit=1)[0]


def missing_qualification(f: ApprovedFact, claim_text: str) -> str | None:
    """The approved conditions the claim leaves out, or None if it states them (or none are required)."""
    if f.category not in QUALIFIED_CATEGORIES or not f.qualifications:
        return None
    lead = tokens(lead_clause(f.qualifications), drop_generic=True)
    if not lead:
        return None
    coverage = len(lead & tokens(claim_text)) / len(lead)
    return None if coverage >= QUALIFICATION_COVERAGE else lead_clause(f.qualifications).strip()


def condition_mismatch(f: ApprovedFact, claim_text: str) -> str | None:
    marker = CONDITION_MARKERS.search(claim_text)
    if marker and marker.group(0).casefold() not in (f.qualifications or "").casefold():
        return (f"The claim refers to \u201c{marker.group(0)}\u201d conditions, which are not part of the approved conditions"
                f" for {show(f)}.")
    return None


# ------------------------------------------------------------------ numeric comparison
def compare_quantity(c: Quantity, f: Quantity) -> tuple[str, str]:
    cv, fv = to_base(c)[1], to_base(f)[1]
    fq, cq = f.qualifier, c.qualifier
    claim, fact = f"\u201c{c.raw}\u201d", f"\u201c{f.raw}\u201d"
    if cv == fv:
        if fq == "up_to":
            if cq in ("up_to", "approx"):
                return "match", f"{claim} matches the approved maximum {fact}."
            if cq == "absolute":
                return "conflict", (f"The claim presents {claim} as guaranteed or constant, but the approved value {fact} is only a maximum, "
                                    "so the claim is broader than the approved statement.")
            return "broader", f"The claim states {claim} without \u201cup to\u201d, but the approved value {fact} is a maximum. The claim is broader than the approved wording."
        if fq in ("from", "at_least"):
            return ("match", f"{claim} matches {fact}.") if cq in ("exact", "from", "at_least", "approx") else ("unclear", f"{claim} and {fact} use different qualifiers.")
        if cq in ("exact", "approx", "absolute"):
            return "match", f"{claim} matches {fact}."
        return "unclear", f"{claim} is worded as a limit, while the approved value {fact} is exact."
    if fq == "up_to":
        if cv > fv:
            return "conflict", f"The claim states {claim}, which is higher than the approved maximum {fact}."
        if cq in ("up_to", "exact", "approx"):
            return "narrower", f"The claim states {claim}, which is lower than the approved maximum {fact}. It is not the approved wording, so it cannot be treated as verified."
        return "unclear", f"{claim} and {fact} cannot be reconciled from the wording."
    if fq in ("from", "at_least"):
        if cv < fv and cq != "at_most":
            return "conflict", f"The claim states {claim}, which is below the approved {fact}."
        return "unclear", f"The claim states {claim}; the approved value is {fact}, so the two cannot be compared directly."
    if cq == "at_least" and cv < fv:
        return "unclear", f"{claim} is a weaker statement than the approved exact value {fact}."
    if cq == "at_most" and cv > fv:
        return "unclear", f"{claim} is a weaker statement than the approved exact value {fact}."
    return "conflict", f"The claim states {claim}, but the approved value is {fact}."


def assess(claim: Claim, fv: FactView) -> FactResult:
    f = fv.fact
    fq = fact_quantity(f.value, f.unit)
    cqs = parse_quantities(claim.text)
    if fq is not None and cqs:
        same = [q for q in cqs if comparable(q, fq)]
        if not same:
            return FactResult(
                "unclear",
                f"The claim's number(s) ({', '.join(q.raw for q in cqs)}) are not in the same unit as the approved value {show(f)}, so they cannot be compared.",
            )
        chosen = next((q for q in same if to_base(q)[1] == to_base(fq)[1]), same[0])
        kind, detail = compare_quantity(chosen, fq)
        if kind == "match":
            missing = missing_qualification(f, claim.text)
            if missing:
                return FactResult("match_unqualified", detail, missing, chosen)
            different = condition_mismatch(f, claim.text)
            if different:
                return FactResult("unclear", different, None, chosen)
        return FactResult(kind, detail, None, chosen)
    if fq is not None:
        return FactResult("none")
    # Non-numeric fact: textual evidence.
    claim_norm, value_norm = norm_ws(claim.text), norm_ws(f.value)
    matched = len(f.value.split()) >= 3 and value_norm in claim_norm
    if not matched:
        terms = {m.group(0).casefold() for m in COMPARATIVE_RE.finditer(claim.text)}
        matched = bool(terms) and f.category in ("approved_claim", "general", "product_spec") and any(t in value_norm for t in terms)
    if matched:
        missing = missing_qualification(f, claim.text)
        if missing:
            return FactResult("text_unqualified", f"The claim repeats the approved statement {show(f)} but leaves out its conditions.", missing)
        return FactResult("text_match", f"The claim repeats the approved statement {show(f)}.")
    if len(fv.value_tokens) >= 3 and len(fv.value_tokens & tokens(claim.text)) / len(fv.value_tokens) >= 0.8:
        return FactResult("text_probable", f"The claim may paraphrase {show(f)}, but the wording differs and this cannot be confirmed without a semantic check.")
    return FactResult("none")


# ------------------------------------------------------------------ classification
def _names(views: list[FactView]) -> str:
    return ", ".join(sorted({fv.fact.name for fv in views}))


def classify(claim: Claim, candidates: list[FactView]) -> Outcome:
    results = [(fv, assess(claim, fv)) for fv in candidates]
    results = [(fv, r) for fv, r in results if r.kind != "none"]
    current = [(fv, r) for fv, r in results if fv.effective == "current"]
    lapsed = [(fv, r) for fv, r in results if fv.effective in ("expired", "retired") and r.kind in ("match", "match_unqualified", "text_match", "text_unqualified")]
    not_usable = [(fv, r) for fv, r in results if fv.effective in ("unapproved", "pending") and r.kind in ("match", "match_unqualified", "text_match", "text_unqualified")]

    matches = [(fv, r) for fv, r in current if r.kind in ("match", "text_match")]
    conflicts = [(fv, r) for fv, r in current if r.kind == "conflict"]
    unqualified = [(fv, r) for fv, r in current if r.kind in ("match_unqualified", "text_unqualified")]
    partial = [(fv, r) for fv, r in current if r.kind in ("narrower", "broader", "unclear", "text_probable")]

    if matches and conflicts:
        both = matches + conflicts
        return Outcome(
            "uncertain",
            "Current approved facts disagree about this claim: " + " ".join(r.detail for _, r in both) + " Resolve the conflict between the approved facts first.",
            "Ask the fact owners which approved fact is correct before publishing this claim.",
            [EvidenceSpec("supports", fv.fact, note=r.detail) for fv, r in matches] + [EvidenceSpec("conflicts", fv.fact, note=r.detail) for fv, r in conflicts],
            matched_fact=conflicts[0][0].fact,
        )
    if conflicts:
        evidence = [EvidenceSpec("conflicts", fv.fact, note=r.detail) for fv, r in conflicts]
        for fv, r in lapsed:
            if r.claim_quantity is not None:
                evidence.append(EvidenceSpec("outdated", fv.fact, note=f"The claim matches this {fv.effective} fact. {r.detail}"))
        outdated_hit = any(e.role == "outdated" for e in evidence)
        first = conflicts[0]
        if outdated_hit:
            old = next(e.fact for e in evidence if e.role == "outdated")
            return Outcome(
                "outdated",
                f"The claim matches {show(old)}, which is no longer current ({_state_phrase(old, lapsed)}). The current approved fact {show(first[0].fact)} says otherwise. {first[1].detail}",
                f"Update the claim to the current approved wording: {show(first[0].fact)}.",
                evidence, matched_fact=old,
            )
        return Outcome(
            "conflicting", f"{first[1].detail} Approved evidence contradicts this claim.",
            f"Correct the claim to match {show(first[0].fact)}, or remove it.", evidence, matched_fact=first[0].fact,
        )
    if matches:
        fv, r = matches[0]
        return Outcome(
            "supported", f"Current approved fact {show(fv.fact)} supports this claim, including its stated conditions. {r.detail}",
            None, [EvidenceSpec("supports", f.fact, note=rr.detail) for f, rr in matches], matched_fact=fv.fact,
        )
    if unqualified:
        fv, r = unqualified[0]
        return Outcome(
            "uncertain",
            f"{r.detail} The approved fact {show(fv.fact)} applies \u201c{r.missing}\u201d, which the claim does not state, so it is not automatically treated as supported.",
            f"Add the approved condition (\u201c{r.missing}\u201d) to the claim, then review again.",
            [EvidenceSpec("context", fv.fact, note=f"Matches on value; claim omits: {r.missing}")], matched_fact=fv.fact,
        )
    if lapsed:
        fv, r = lapsed[0]
        evidence = [EvidenceSpec("outdated", f.fact, note=f"The claim matches this {f.effective} fact.") for f, _ in lapsed]
        evidence += [EvidenceSpec("context", f.fact, note=rr.detail) for f, rr in partial]
        current_note = f" The current approved fact {show(partial[0][0].fact)} should be used instead." if partial else " No current approved fact was found to replace it."
        return Outcome(
            "outdated", f"The claim matches {show(fv.fact)}, which is no longer current ({_state_phrase(fv.fact, lapsed)}).{current_note}",
            "Update the claim to the current approved wording, or remove it." if partial else "Remove the claim or ask the fact owner for a current approved fact.",
            evidence, matched_fact=fv.fact,
        )
    if partial:
        fv, r = partial[0]
        return Outcome(
            "uncertain", r.detail + " A person should confirm whether the claim is acceptable.",
            f"Reword the claim to match {show(fv.fact)} exactly, or ask the fact owner to confirm the wording.",
            [EvidenceSpec("context", f.fact, note=rr.detail) for f, rr in partial], matched_fact=fv.fact, needs_ai=True,
            ai_candidates=[f for f, _ in partial],
        )
    note = ""
    if not_usable:
        fv, _ = not_usable[0]
        reason = {"unapproved": f"has not been approved (status: {fv.fact.status})", "pending": "is not valid yet"}[fv.effective]
        note = f" A fact with matching wording, {show(fv.fact)}, exists but {reason}, so it cannot be used as evidence."
    related = [fv for fv in candidates if fv.effective == "current"]
    if related and not note:
        note = f" Current approved facts about the same subject ({_names(related)}) do not substantiate this claim."
    return Outcome(
        "unsupported",
        "No suitable approved evidence was found for this claim. Unsupported does not mean the claim is false; it means the approved knowledge base does not substantiate it." + note,
        "Remove the claim, reword it to match an approved fact, or ask the owner to add and approve evidence for it.",
        [], needs_ai=True,
    )


def _state_phrase(fact: ApprovedFact, lapsed: list[tuple[FactView, FactResult]]) -> str:
    view = next((fv for fv, _ in lapsed if fv.fact.id == fact.id), None)
    if view is not None and view.effective == "retired":
        return "retired / superseded"
    if fact.status == "expired":
        return "marked expired"
    return f"expired on {fact.expires_at.isoformat()}" if fact.expires_at else "expired"
