"""Service for running policy sandbox simulations against historical content.

Simulations evaluate proposed guideline changes against historical content records without altering
previous review runs, findings, evidence snapshots, or workflow decisions.
"""
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationFailed, field_error
from app.models.guideline import GuidelineRule, PolicySimulation, PolicySimulationResult
from app.models.review import ContentSubmission, ReviewRun
from app.schemas.guideline import (
    PolicySimulationCreate, PolicySimulationListOut, PolicySimulationOut, PolicySimulationResultOut,
)

COMPARATIVE_PHRASES = (
    "faster than", "better than", "more than", "superior to", "superior performance",
    "beats", "versus", "vs ", "outperforms",
)


def evaluate_content_against_rule(
    content_text: str,
    rule_dict: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], str, str]:
    """
    Evaluates content against a rule snapshot.
    Returns: (outcome, findings, explanation, evaluation_status)
    outcome: 'pass' | 'flagged' | 'not_evaluable'
    evaluation_status: 'evaluated' | 'not_evaluable'
    """
    category = (rule_dict.get("category") or "general").lower()
    conditions = rule_dict.get("conditions") or {}
    rule_text = (rule_dict.get("rule_text") or "").lower()

    prohibited_terms = conditions.get("prohibited_terms", [])
    required_terms = conditions.get("required_terms", [])
    required_phrases = conditions.get("required_phrases", [])
    comparative_prohibited = conditions.get("comparative_prohibited")
    comparative_permitted = conditions.get("comparative_permitted")

    # If no conditions dict, check if rule is a clear comparative or prohibition rule from text
    if not conditions:
        if ("comparative" in category or "comparative" in rule_text or category in ("claim", "general")) and ("must not" in rule_text or "prohibited" in rule_text or "never" in rule_text):
            comparative_prohibited = True
        elif ("comparative" in category or "comparative" in rule_text or category in ("claim", "general")) and ("may be used" in rule_text or "permitted" in rule_text or "allowed" in rule_text or "supported" in rule_text):
            comparative_permitted = True

    # If rule has no testable conditions, mark as not_evaluable
    has_testable_condition = bool(
        prohibited_terms
        or required_terms
        or required_phrases
        or comparative_prohibited is not None
        or comparative_permitted is not None
    )

    if not has_testable_condition:
        return (
            "not_evaluable",
            [],
            "Rule lacks testable condition parameters (unstructured natural language). Marked not evaluable.",
            "not_evaluable",
        )

    content_lower = content_text.lower()
    violations: list[dict[str, Any]] = []

    # Check prohibited terms
    for term in prohibited_terms:
        if term and term.lower() in content_lower:
            violations.append({
                "type": "prohibited_term",
                "term": term,
                "detail": f"Content contains prohibited term '{term}'.",
            })

    # Check required terms
    for term in required_terms:
        if term and term.lower() not in content_lower:
            violations.append({
                "type": "missing_required_term",
                "term": term,
                "detail": f"Content is missing required term '{term}'.",
            })

    # Check required phrases
    for phrase in required_phrases:
        if phrase and phrase.lower() not in content_lower:
            violations.append({
                "type": "missing_required_phrase",
                "phrase": phrase,
                "detail": f"Content is missing required phrase '{phrase}'.",
            })

    # Check comparative language
    if comparative_prohibited is True:
        found_comp = next((cp for cp in COMPARATIVE_PHRASES if cp in content_lower), None)
        if found_comp:
            violations.append({
                "type": "comparative_prohibited",
                "phrase": found_comp,
                "detail": f"Content contains comparative phrase '{found_comp}' prohibited by rule.",
            })

    if violations:
        reasons = "; ".join(v["detail"] for v in violations)
        return ("flagged", violations, f"Flagged: {reasons}", "evaluated")
    else:
        return ("pass", [], "Complies with tested rule conditions.", "evaluated")


def run_policy_simulation(
    db: Session,
    brand_id: uuid.UUID,
    data: PolicySimulationCreate,
    actor_name: str,
) -> PolicySimulationOut:
    rule = db.scalar(select(GuidelineRule).where(GuidelineRule.id == data.rule_id, GuidelineRule.brand_id == brand_id))
    if not rule:
        raise NotFoundError("Guideline rule not found for this brand.", code="rule_not_found")

    base_rule_dict = {
        "title": rule.title,
        "rule_text": rule.rule_text,
        "category": rule.category,
        "severity": rule.severity,
        "scope": rule.scope,
        "conditions": rule.conditions,
        "examples": rule.examples,
    }

    proposed_rule_dict = dict(data.proposed_rule) if data.proposed_rule else {}
    if data.proposed_rule_text and not proposed_rule_dict.get("rule_text"):
        proposed_rule_dict["rule_text"] = data.proposed_rule_text
    if data.proposed_conditions and not proposed_rule_dict.get("conditions"):
        proposed_rule_dict["conditions"] = data.proposed_conditions
    if not proposed_rule_dict.get("rule_text"):
        proposed_rule_dict["rule_text"] = rule.rule_text
    if not proposed_rule_dict.get("category"):
        proposed_rule_dict["category"] = rule.category
    if not proposed_rule_dict.get("scope"):
        proposed_rule_dict["scope"] = rule.scope
    if "conditions" not in proposed_rule_dict:
        proposed_rule_dict["conditions"] = rule.conditions

    # Fetch submissions to evaluate
    if data.content_submission_ids:
        # Cross-brand validation: all requested submissions must belong to this brand
        submissions = list(
            db.scalars(
                select(ContentSubmission).where(
                    ContentSubmission.id.in_(data.content_submission_ids)
                )
            )
        )
        if len(submissions) != len(data.content_submission_ids):
            raise NotFoundError("One or more content submissions not found.", code="submission_not_found")
        for sub in submissions:
            if sub.brand_id != brand_id:
                raise ValidationFailed(
                    "Cross-brand content cannot be included in a simulation.",
                    details=[field_error("content_submission_ids", f"Submission {sub.id} belongs to another brand.")],
                )
    else:
        submissions = list(
            db.scalars(
                select(ContentSubmission)
                .where(ContentSubmission.brand_id == brand_id)
                .order_by(ContentSubmission.created_at.desc())
                .limit(50)
            )
        )

    sim = PolicySimulation(
        brand_id=brand_id,
        rule_id=rule.id,
        base_rule_version=rule.current_version,
        proposed_rule_version=rule.current_version + 1,
        proposed_rule_snapshot=proposed_rule_dict,
        status="completed",
        created_by=actor_name,
        completed_at=datetime.utcnow(),
        summary={},
    )
    db.add(sim)
    db.flush()

    total_evaluated = 0
    changed_count = 0
    unchanged_count = 0
    not_evaluable_count = 0
    result_outs: list[PolicySimulationResultOut] = []

    for sub in submissions:
        # Find latest completed review run for this submission if exists
        run = db.scalar(
            select(ReviewRun)
            .where(ReviewRun.content_submission_id == sub.id, ReviewRun.status.in_(("completed", "completed_limited")))
            .order_by(ReviewRun.started_at.desc())
            .limit(1)
        )

        base_out, base_finds, base_exp, base_status = evaluate_content_against_rule(sub.content, base_rule_dict)
        prop_out, prop_finds, prop_exp, prop_status = evaluate_content_against_rule(sub.content, proposed_rule_dict)

        eval_status = "evaluated"
        if base_status == "not_evaluable" and prop_status == "not_evaluable":
            eval_status = "not_evaluable"
            not_evaluable_count += 1
        else:
            total_evaluated += 1

        is_changed = (base_out != prop_out)
        if is_changed:
            changed_count += 1
            diff_explanation = f"Outcome changed from {base_out.upper()} to {prop_out.upper()}. Baseline: {base_exp} | Proposed: {prop_exp}"
        else:
            unchanged_count += 1
            diff_explanation = f"Outcome remained {base_out.upper()}. Baseline: {base_exp} | Proposed: {prop_exp}"

        changed_findings = [
            {"source": "baseline", "findings": base_finds},
            {"source": "proposed", "findings": prop_finds},
        ]

        sim_res = PolicySimulationResult(
            simulation_id=sim.id,
            content_submission_id=sub.id,
            historical_review_run_id=run.id if run else None,
            baseline_outcome=base_out,
            simulated_outcome=prop_out,
            changed_findings=changed_findings,
            explanation=diff_explanation,
            evaluation_status=eval_status,
        )
        db.add(sim_res)
        db.flush()

        snippet = (sub.content[:80] + "...") if len(sub.content) > 80 else sub.content
        result_outs.append(
            PolicySimulationResultOut(
                id=sim_res.id,
                simulation_id=sim.id,
                content_submission_id=sub.id,
                content_title=sub.title,
                content_snippet=snippet,
                historical_review_run_id=run.id if run else None,
                baseline_outcome=base_out,
                simulated_outcome=prop_out,
                changed_findings=changed_findings,
                explanation=diff_explanation,
                evaluation_status=eval_status,
                created_at=sim_res.created_at,
            )
        )

    summary = {
        "total_submissions": len(submissions),
        "total_evaluated": total_evaluated,
        "changed": changed_count,
        "unchanged": unchanged_count,
        "not_evaluable": not_evaluable_count,
    }
    sim.summary = summary
    db.commit()
    db.refresh(sim)

    return PolicySimulationOut(
        id=sim.id,
        brand_id=sim.brand_id,
        rule_id=sim.rule_id,
        rule_title=rule.title,
        base_rule_version=sim.base_rule_version,
        proposed_rule_version=sim.proposed_rule_version,
        proposed_rule_snapshot=sim.proposed_rule_snapshot,
        status=sim.status,
        created_by=sim.created_by,
        created_at=sim.created_at,
        completed_at=sim.completed_at,
        summary=sim.summary,
        results=result_outs,
    )


def get_simulation(db: Session, simulation_id: uuid.UUID) -> PolicySimulationOut:
    sim = db.scalar(select(PolicySimulation).where(PolicySimulation.id == simulation_id))
    if not sim:
        raise NotFoundError("Policy simulation not found.", code="simulation_not_found")
    rule = db.scalar(select(GuidelineRule).where(GuidelineRule.id == sim.rule_id))

    raw_results = list(
        db.scalars(
            select(PolicySimulationResult)
            .where(PolicySimulationResult.simulation_id == sim.id)
            .order_by(PolicySimulationResult.created_at.asc())
        )
    )
    result_outs: list[PolicySimulationResultOut] = []
    for r in raw_results:
        sub = db.scalar(select(ContentSubmission).where(ContentSubmission.id == r.content_submission_id))
        snippet = ""
        title = None
        if sub:
            title = sub.title
            snippet = (sub.content[:80] + "...") if len(sub.content) > 80 else sub.content
        result_outs.append(
            PolicySimulationResultOut(
                id=r.id,
                simulation_id=r.simulation_id,
                content_submission_id=r.content_submission_id,
                content_title=title,
                content_snippet=snippet,
                historical_review_run_id=r.historical_review_run_id,
                baseline_outcome=r.baseline_outcome,
                simulated_outcome=r.simulated_outcome,
                changed_findings=r.changed_findings,
                explanation=r.explanation,
                evaluation_status=r.evaluation_status,
                created_at=r.created_at,
            )
        )

    return PolicySimulationOut(
        id=sim.id,
        brand_id=sim.brand_id,
        rule_id=sim.rule_id,
        rule_title=rule.title if rule else None,
        base_rule_version=sim.base_rule_version,
        proposed_rule_version=sim.proposed_rule_version,
        proposed_rule_snapshot=sim.proposed_rule_snapshot,
        status=sim.status,
        created_by=sim.created_by,
        created_at=sim.created_at,
        completed_at=sim.completed_at,
        summary=sim.summary,
        results=result_outs,
    )


def list_simulations(db: Session, brand_id: uuid.UUID, limit: int = 50, offset: int = 0) -> PolicySimulationListOut:
    total = db.scalar(
        select(func.count(PolicySimulation.id)).where(PolicySimulation.brand_id == brand_id)
    ) or 0
    sims = list(
        db.scalars(
            select(PolicySimulation)
            .where(PolicySimulation.brand_id == brand_id)
            .order_by(PolicySimulation.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    items = []
    for s in sims:
        rule = db.scalar(select(GuidelineRule).where(GuidelineRule.id == s.rule_id))
        items.append(
            PolicySimulationOut(
                id=s.id,
                brand_id=s.brand_id,
                rule_id=s.rule_id,
                rule_title=rule.title if rule else None,
                base_rule_version=s.base_rule_version,
                proposed_rule_version=s.proposed_rule_version,
                proposed_rule_snapshot=s.proposed_rule_snapshot,
                status=s.status,
                created_by=s.created_by,
                created_at=s.created_at,
                completed_at=s.completed_at,
                summary=s.summary,
                results=[],
            )
        )
    return PolicySimulationListOut(items=items, total=total)
