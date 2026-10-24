"""Review orchestration: extraction -> retrieval -> matching -> classification -> explanation -> persistence.

Each step lives in its own module. This file only sequences them and owns the run lifecycle:

  running -> completed          full analysis (an AI provider is configured and answered correctly)
  running -> completed_limited  deterministic rules only (no provider configured); limitations are recorded
  running -> failed             provider unavailable / invalid output / persistence failure; no findings are kept

A review is never reported as completed unless its findings were saved in the same transaction as the status change.
"""
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.models import Brand, ContentSubmission, ReviewFinding, ReviewRun
from app.services.review import ai, claims as claim_mod, evidence, policy, retrieval, terminology
from app.services.review.matching import assess, classify, missing_qualification, show
from app.services.review.providers import LLMProvider, ProviderError
from app.services.review.types import EvidenceSpec, FactView, Outcome

logger = logging.getLogger("brandpr.review")

LIMITED_MESSAGE = (
    "Limited analysis: no AI provider is configured (LLM_API_KEY is empty), so only deterministic rules were applied. "
    "Claims written as paraphrases, and paraphrased support in approved facts, cannot be recognised. "
    "A result of 'no findings' does not mean the content has no claims."
)


class ReviewPersistenceError(AppError):
    status_code = 503
    code = "review_persistence_failed"


@dataclass
class Analysis:
    items: list[tuple[claim_mod.Claim, Outcome]]
    limitations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ analysis (no database writes)
def _refine_with_ai(provider: LLMProvider, claim: claim_mod.Claim, outcome: Outcome, kb: retrieval.KnowledgeBase, notes: list[str]) -> Outcome:
    pool = [fv for fv in (outcome.ai_candidates or retrieval.loosely_related(kb, claim.text)) if fv.effective == "current"][:5]
    if not pool:
        return outcome
    payload = [{"id": str(fv.fact.id), "name": fv.fact.name, "value": fv.fact.value, "qualifications": fv.fact.qualifications} for fv in pool]
    interpretations, discarded = ai.interpret_claim(provider, claim.text, payload)
    if discarded:
        notes.append(f"Discarded {discarded} model assessment(s) that cited a record the system had not retrieved for this claim.")
    by_id: dict[uuid.UUID, FactView] = {fv.fact.id: fv for fv in pool}
    supports = [i for i in interpretations if i.relation == "supports"]
    contradicts = [i for i in interpretations if i.relation == "contradicts"]
    unclear = [i for i in interpretations if i.relation == "unclear"]

    if supports and contradicts:
        return Outcome(
            "uncertain", "The AI-assisted check found both supporting and contradicting approved facts. A person must decide.",
            "Ask the fact owners to confirm which wording is correct.", [], method="ai_assisted",
        )
    if contradicts:
        i = contradicts[0]
        f = by_id[i.fact_id].fact
        return Outcome(
            "conflicting", f"AI-assisted check: the claim appears to contradict {show(f)}. {i.reason or ''}".strip(),
            f"Correct the claim to match {show(f)}, or remove it. A person should confirm this finding.",
            [EvidenceSpec("conflicts", f, note=f"AI-assisted: {i.reason or 'contradiction'}")], matched_fact=f, method="ai_assisted",
        )
    if supports:
        i = supports[0]
        fv = by_id[i.fact_id]
        r = assess(claim, fv)
        if r.kind == "conflict":
            notes.append("A model 'supports' assessment was overridden because the deterministic comparison found a numeric conflict.")
            return Outcome(
                "conflicting", r.detail + " Approved evidence contradicts this claim.", f"Correct the claim to match {show(fv.fact)}, or remove it.",
                [EvidenceSpec("conflicts", fv.fact, note=r.detail)], matched_fact=fv.fact,
            )
        missing = missing_qualification(fv.fact, claim.text)
        if missing:
            return Outcome(
                "uncertain", f"The AI-assisted check relates the claim to {show(fv.fact)}, but the claim omits its condition \u201c{missing}\u201d.",
                f"Add \u201c{missing}\u201d to the claim.", [EvidenceSpec("supports", fv.fact, note=f"AI-assisted match; claim omits: {missing}")],
                matched_fact=fv.fact, method="ai_assisted",
            )
        return Outcome(
            "supported", f"AI-assisted check: current approved fact {show(fv.fact)} supports this claim. {i.reason or ''}".strip(),
            "A person should confirm this AI-assisted match.", [EvidenceSpec("supports", fv.fact, note=f"AI-assisted: {i.reason or 'paraphrase'}")],
            matched_fact=fv.fact, method="ai_assisted",
        )
    if unclear and outcome.status == "unsupported":
        f = by_id[unclear[0].fact_id].fact
        return Outcome(
            "uncertain", f"The AI-assisted check could not decide how this claim relates to {show(f)}. {unclear[0].reason or ''}".strip(),
            "Reword the claim to match an approved fact, or ask the owner to confirm.", [], matched_fact=f, method="ai_assisted",
        )
    return outcome


def analyse(db: Session, content: ContentSubmission, provider: LLMProvider | None) -> Analysis:
    kb = retrieval.load_knowledge(db, content.brand_id)
    result = Analysis(items=[])
    claims = claim_mod.extract_deterministic(content.content)
    if provider is not None:
        brand = db.get(Brand, content.brand_id)
        suggested = ai.extract_claims(provider, content.content, brand.name if brand else "")
        claims, extra = claim_mod.merge_ai_claims(content.content, claims, suggested)
        result.notes += extra
    else:
        result.limitations.append(LIMITED_MESSAGE)

    for claim in claims:
        outcome = classify(claim, retrieval.candidates(kb, claim.text))
        if provider is not None and outcome.needs_ai:
            outcome = _refine_with_ai(provider, claim, outcome, kb, result.notes)
        if outcome.status == "unsupported":
            passage = retrieval.best_source_passage(db, content.brand_id, claim.text)
            if passage:
                section, sentence = passage
                outcome.evidence.append(EvidenceSpec(
                    "related_source", section=section, excerpt=sentence,
                    note="Related source text. It is not an approved fact, so it does not support the claim.",
                ))
        result.items.append((claim, outcome))
    result.items += terminology.check(content.content, kb)
    result.items.sort(key=lambda it: (it[0].start, it[0].end, it[0].category))
    if not result.items:
        result.notes.append("No candidate claims were detected in this content.")
    return result


# ------------------------------------------------------------------ lifecycle and persistence
def _fail(db: Session, run_id: uuid.UUID, code: str, message: str) -> None:
    try:
        db.rollback()
        db.execute(update(ReviewRun).where(ReviewRun.id == run_id).values(status="failed", completed_at=clock.now(), error_code=code, error_message=message))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not record failure of review run %s", run_id)


def _persist(db: Session, run: ReviewRun, analysis: Analysis, mode: str) -> None:
    counts = {s: 0 for s in ("supported", "unsupported", "conflicting", "outdated", "uncertain")}
    for index, (claim, outcome) in enumerate(analysis.items):
        severity = policy.severity_for(outcome.status, claim.category, outcome.term_kind)
        finding = ReviewFinding(
            brand_id=run.brand_id, review_run_id=run.id, claim_index=index, claim_text=claim.text, claim_category=claim.category,
            start_offset=claim.start, end_offset=claim.end, status=outcome.status, severity=severity, explanation=outcome.explanation,
            recommended_action=outcome.recommended_action,
            requires_human_review=policy.needs_human_review(outcome.status, claim.category, severity, outcome.method),
            method=outcome.method, extraction_method=claim.extraction_method,
            matched_fact_id=outcome.matched_fact.id if outcome.matched_fact else None,
        )
        db.add(finding)
        db.flush()
        for spec in outcome.evidence:
            db.add(evidence.build(db, run.brand_id, finding.id, spec))
        counts[outcome.status] += 1
    run.status = "completed" if mode == "full" else "completed_limited"
    run.completed_at = clock.now()
    run.summary = {"counts": counts, "limitations": analysis.limitations, "notes": analysis.notes}
    db.commit()


def run_review(db: Session, content: ContentSubmission, provider: LLMProvider | None, requested_by: str | None) -> ReviewRun:
    mode = "full" if provider is not None else "limited"
    run = ReviewRun(
        brand_id=content.brand_id, content_submission_id=content.id, status="running", analysis_mode=mode, content_hash=content.content_hash,
        requested_by=(requested_by or "").strip() or None, provider_name=getattr(provider, "name", None), model_name=getattr(provider, "model", None),
    )
    db.add(run)
    db.commit()  # the run exists (and is visibly 'running') before any analysis starts
    db.refresh(run)
    try:
        analysis = analyse(db, content, provider)
    except ProviderError as exc:
        logger.warning("Review %s failed: %s", run.id, exc.code)
        _fail(db, run.id, exc.code, str(exc))
        db.refresh(run)
        return run
    except SQLAlchemyError:
        _fail(db, run.id, "database_error", "The approved facts could not be read.")
        raise
    except Exception:
        logger.exception("Unexpected error in review %s", run.id)
        _fail(db, run.id, "internal_error", "The review could not be completed.")
        raise
    try:
        _persist(db, run, analysis, mode)
    except SQLAlchemyError as exc:
        logger.error("Persisting review %s failed: %s", run.id, exc.__class__.__name__)
        _fail(db, run.id, "persistence_failed", "The review results could not be saved.")
        raise ReviewPersistenceError("The review finished but its results could not be saved, so it was not recorded as completed.") from exc
    except Exception:
        logger.exception("Unexpected error saving review %s", run.id)
        _fail(db, run.id, "internal_error", "The review results could not be saved.")
        raise
    db.refresh(run)
    return run


def fail_interrupted_runs(db: Session) -> int:
    """Runs left 'pending' or 'running' by a crashed or restarted process are marked failed (single-instance assumption)."""
    ids = list(db.scalars(select(ReviewRun.id).where(ReviewRun.status.in_(("pending", "running")))))
    for run_id in ids:
        _fail(db, run_id, "interrupted", "The review was interrupted before it finished.")
    return len(ids)
