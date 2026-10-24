"""Service for calculating Governance Intelligence metrics and evidence-backed recommendations.

All metrics are computed from real persisted database records without synthetic fixtures or hardcoded constants.
Brand isolation is strictly enforced across all database queries.
"""
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.fact_change_impact import FactChangeImpact
from app.models.guideline import GuidelineLintResult, GuidelineRule, PolicySimulation
from app.models.review import ReviewFinding, ReviewRun
from app.models.workflow import WorkflowEvent
from app.schemas.guideline import GovernanceInsightsOut


def get_governance_insights(
    db: Session,
    brand_id: uuid.UUID,
    period: str = "all",
) -> GovernanceInsightsOut:
    now = datetime.now(timezone.utc)
    cutoff = None
    if period == "7d":
        cutoff = now - timedelta(days=7)
    elif period == "30d":
        cutoff = now - timedelta(days=30)

    # 1. Completed Review Runs Count
    run_query = select(func.count(ReviewRun.id)).where(
        ReviewRun.brand_id == brand_id,
        ReviewRun.status.in_(("completed", "completed_limited")),
    )
    if cutoff:
        run_query = run_query.where(ReviewRun.started_at >= cutoff)
    completed_reviews = db.scalar(run_query) or 0

    # 2. Findings Aggregations (Avoid joining FindingEvidence to avoid double-counting!)
    # We join ReviewRun only to scope to brand and review run completion
    finding_query = (
        select(ReviewFinding.status, ReviewFinding.severity, ReviewFinding.claim_category, ReviewFinding.claim_text, ReviewFinding.explanation)
        .join(ReviewRun, ReviewFinding.review_run_id == ReviewRun.id)
        .where(
            ReviewRun.brand_id == brand_id,
            ReviewRun.status.in_(("completed", "completed_limited")),
        )
    )
    if cutoff:
        finding_query = finding_query.where(ReviewRun.started_at >= cutoff)

    raw_findings = list(db.execute(finding_query))
    total_findings = len(raw_findings)

    by_status: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    terms_counter: Counter[str] = Counter()
    finding_samples_by_term: dict[str, list[str]] = {}

    stop_words = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with", "is", "are", "was", "were", "this", "that", "it", "of", "by", "as"}

    for status, severity, category, claim_text, explanation in raw_findings:
        by_status[status] = by_status.get(status, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1

        # Extract meaningful terms from non-supported claims
        if status in ("conflicting", "unsupported", "outdated"):
            tokens = re.findall(r"\b[A-Za-z0-9_-]{4,}\b", claim_text or "")
            for tok in tokens:
                t_lower = tok.lower()
                if t_lower not in stop_words:
                    terms_counter[t_lower] += 1
                    if t_lower not in finding_samples_by_term:
                        finding_samples_by_term[t_lower] = []
                    if len(finding_samples_by_term[t_lower]) < 3 and claim_text not in finding_samples_by_term[t_lower]:
                        finding_samples_by_term[t_lower].append(claim_text)

    # 3. Open Impacts Count
    impact_query = select(func.count(FactChangeImpact.id)).where(
        FactChangeImpact.brand_id == brand_id,
        FactChangeImpact.status == "needs_review",
    )
    open_impacts = db.scalar(impact_query) or 0

    # 4. Workflow Decisions Counts
    dec_query = select(WorkflowEvent.action, func.count(WorkflowEvent.id)).where(
        WorkflowEvent.brand_id == brand_id,
        WorkflowEvent.action.in_(("approved", "changes_requested", "rejected")),
    )
    if cutoff:
        dec_query = dec_query.where(WorkflowEvent.created_at >= cutoff)
    dec_counts = {action: count for action, count in db.execute(dec_query.group_by(WorkflowEvent.action)).all()}
    decisions = {
        "approved": dec_counts.get("approved", 0),
        "changes_requested": dec_counts.get("changes_requested", 0),
        "rejected": dec_counts.get("rejected", 0),
    }

    # 5. Guideline Rules Breakdown
    rule_query = select(GuidelineRule.status, func.count(GuidelineRule.id)).where(
        GuidelineRule.brand_id == brand_id
    ).group_by(GuidelineRule.status)
    rule_counts = {status: count for status, count in db.execute(rule_query).all()}
    rules_summary = {
        "active": rule_counts.get("active", 0),
        "proposed": rule_counts.get("proposed", 0),
        "retired": rule_counts.get("retired", 0),
        "total": sum(rule_counts.values()),
    }

    # 6. Top Problematic Terms / Claims
    top_terms = [
        {"term": term, "count": count, "samples": finding_samples_by_term.get(term, [])}
        for term, count in terms_counter.most_common(5)
    ]

    # 7. Repeated issues (terms that occur 2+ times in non-supported findings)
    repeated_issues = [
        {
            "term": term,
            "occurrences": count,
            "representative_claims": finding_samples_by_term.get(term, []),
        }
        for term, count in terms_counter.items()
        if count >= 2
    ]

    # 8. Governance Recommendations (Evidence-backed from actual persisted records)
    recommendations: list[dict[str, Any]] = []

    # Rec A: Repeated problematic terms
    for item in top_terms[:2]:
        if item["count"] >= 2:
            recommendations.append({
                "category": "terminology",
                "pattern": f"Frequent review flags for '{item['term']}' ({item['count']} times)",
                "count": item["count"],
                "representative_findings": item["samples"],
                "suggested_action": f"Establish an explicit approved guideline rule or approved fact clarifying '{item['term']}' usage.",
                "requires_human_assessment": True,
            })

    # Rec B: Active rules with unresolved lint issues
    lint_query = (
        select(GuidelineLintResult, GuidelineRule.title)
        .join(GuidelineRule, GuidelineLintResult.rule_id == GuidelineRule.id)
        .where(
            GuidelineLintResult.brand_id == brand_id,
            GuidelineRule.status == "active",
        )
        .limit(3)
    )
    unresolved_lints = list(db.execute(lint_query))
    for lr, rtitle in unresolved_lints:
        recommendations.append({
            "category": "guideline_ambiguity",
            "pattern": f"Active rule '{rtitle}' has potential {lr.issue_category.replace('_', ' ')}",
            "count": 1,
            "relevant_rule_ids": [str(lr.rule_id)],
            "representative_findings": [lr.explanation],
            "suggested_action": lr.suggested_action,
            "requires_human_assessment": True,
        })

    # Rec C: Open fact-change impacts
    if open_impacts > 0:
        recommendations.append({
            "category": "fact_change_impacts",
            "pattern": f"{open_impacts} content piece(s) affected by approved fact changes require review",
            "count": open_impacts,
            "representative_findings": [],
            "suggested_action": "Review and update affected campaign drafts or resolve impacts with new approved revisions.",
            "requires_human_assessment": True,
        })

    # Rec D: High-risk findings dominance
    high_risk_count = by_severity.get("high", 0)
    if high_risk_count > 0:
        recommendations.append({
            "category": "risk_management",
            "pattern": f"{high_risk_count} high-severity findings recorded in review history",
            "count": high_risk_count,
            "representative_findings": [],
            "suggested_action": "Check whether claims involve comparative statements or unapproved product specifications.",
            "requires_human_assessment": True,
        })

    # 9. Simulations Summary
    sim_count = db.scalar(select(func.count(PolicySimulation.id)).where(PolicySimulation.brand_id == brand_id)) or 0
    sims = list(db.scalars(select(PolicySimulation).where(PolicySimulation.brand_id == brand_id).limit(20)))
    total_changed_outcomes = sum(s.summary.get("changed", 0) for s in sims if s.summary)
    total_sim_evaluated = sum(s.summary.get("total_evaluated", 0) for s in sims if s.summary)

    simulations_summary = {
        "total_simulations": sim_count,
        "total_evaluated_content": total_sim_evaluated,
        "total_changed_outcomes": total_changed_outcomes,
    }

    overview = {
        "completed_reviews": completed_reviews,
        "total_findings": total_findings,
        "open_impacts": open_impacts,
        "decisions": decisions,
        "rules_summary": rules_summary,
    }

    finding_patterns = {
        "by_status": by_status,
        "by_severity": by_severity,
        "by_category": by_category,
        "top_problematic_terms": top_terms,
    }

    return GovernanceInsightsOut(
        brand_id=brand_id,
        period=period,
        overview=overview,
        finding_patterns=finding_patterns,
        repeated_issues=repeated_issues,
        governance_recommendations=recommendations,
        simulations_summary=simulations_summary,
    )
