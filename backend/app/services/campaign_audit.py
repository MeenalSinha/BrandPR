"""Phase 6 campaign audit, consistency analysis, release-readiness evaluation, and release execution."""
from datetime import datetime
import re
from typing import Any, Optional
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.approved_fact import ApprovedFact
from app.models.campaign import (
    Campaign, CampaignAsset, CampaignAudit, CampaignAuditFinding, CampaignReleaseDecision,
)
from app.models.fact_change_impact import FactChangeImpact
from app.models.guideline import GuidelineRule
from app.models.review import (
    ContentAsset, ContentSubmission, FindingEvidence, ReviewFinding, ReviewRun,
)
from app.schemas.campaign import (
    AuditComparisonOut, CampaignAuditFindingOut, CampaignAuditOut, ReleaseEvaluationOut,
)


class CampaignAuditError(AppError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message, code=code)
        self.status_code = status_code



def _extract_metric_numbers(text: str) -> list[tuple[float, str, str]]:
    """Extracts numeric values with units or key metrics from text for cross-asset comparison."""
    results = []
    # e.g., 24 hours, 18 hours, 99.9%, 20%, 500GB, 10x, $49, etc.
    pattern = r'\b(\d+(?:\.\d+)?)\s*(hours?|days?|weeks?|months?|%|percent|x|times|gb|tb|mah|w|ghz|k)\b'
    for match in re.finditer(pattern, text, re.IGNORECASE):
        try:
            val = float(match.group(1))
            unit = match.group(2).lower()
            results.append((val, unit, match.group(0)))
        except ValueError:
            continue
    return results


def check_campaign_audit_staleness(db: Session, campaign_id: uuid.UUID, audit: CampaignAudit) -> tuple[bool, Optional[str]]:
    """Checks if an audit has become stale due to changed assets, revisions, facts, or guidelines."""
    if audit.is_stale:
        return True, audit.stale_reason

    campaign = db.execute(select(Campaign).where(Campaign.id == campaign_id)).scalars().first()
    if not campaign:
        return True, "Campaign not found"

    summary = audit.summary or {}
    evaluated_assets = summary.get("evaluated_assets", [])
    evaluated_facts = summary.get("evaluated_facts_versions", {})
    evaluated_rules = summary.get("evaluated_rules_versions", {})

    # 1. Compare current campaign assets count and revisions
    current_assets = db.execute(
        select(CampaignAsset).where(CampaignAsset.campaign_id == campaign_id)
    ).scalars().all()

    if len(current_assets) != len(evaluated_assets):
        reason = f"Asset count changed: {len(evaluated_assets)} evaluated vs {len(current_assets)} currently"
        audit.is_stale = True
        audit.stale_reason = reason
        db.commit()
        return True, reason

    eval_map = {item["asset_id"]: item for item in evaluated_assets}
    for ca in current_assets:
        aid_str = str(ca.asset_id)
        if aid_str not in eval_map:
            reason = "Campaign asset membership changed"
            audit.is_stale = True
            audit.stale_reason = reason
            db.commit()
            return True, reason

        if str(ca.selected_submission_id) != eval_map[aid_str].get("submission_id"):
            reason = f"Selected revision for asset changed"
            audit.is_stale = True
            audit.stale_reason = reason
            db.commit()
            return True, reason

    # 2. Check if any evaluated fact version has changed
    for fact_id_str, old_version in evaluated_facts.items():
        try:
            fid = uuid.UUID(fact_id_str)
            fact = db.execute(select(ApprovedFact).where(ApprovedFact.id == fid)).scalars().first()
            if fact and fact.version > old_version:
                reason = f"Fact '{fact.name}' updated to version {fact.version} (was {old_version})"
                audit.is_stale = True
                audit.stale_reason = reason
                db.commit()
                return True, reason
        except Exception:
            continue


    # 3. Check if any active guideline rule version has changed
    for rule_id_str, old_version in evaluated_rules.items():
        try:
            rid = uuid.UUID(rule_id_str)
            rule = db.execute(select(GuidelineRule).where(GuidelineRule.id == rid)).scalars().first()
            if rule and rule.current_version > old_version:
                reason = f"Guideline rule '{rule.title}' updated to version {rule.current_version} (was {old_version})"
                audit.is_stale = True
                audit.stale_reason = reason
                db.commit()
                return True, reason
        except Exception:
            continue

    return False, None


def run_campaign_audit(db: Session, campaign_id: uuid.UUID, actor_name: Optional[str] = None) -> CampaignAudit:
    """Executes a full consistency and readiness audit across all selected campaign assets."""
    campaign = db.execute(select(Campaign).where(Campaign.id == campaign_id)).scalars().first()
    if not campaign:
        raise CampaignAuditError("campaign_not_found", "Campaign not found", 404)

    # Invalidate prior non-stale audits
    db.execute(
        update(CampaignAudit)
        .where(CampaignAudit.campaign_id == campaign_id, CampaignAudit.is_stale == False)
        .values(is_stale=True, stale_reason="Superseded by newer campaign audit")
    )

    # Fetch all campaign assets
    ca_rows = db.execute(
        select(CampaignAsset, ContentAsset, ContentSubmission)
        .join(ContentAsset, ContentAsset.id == CampaignAsset.asset_id)
        .join(ContentSubmission, ContentSubmission.id == CampaignAsset.selected_submission_id)
        .where(CampaignAsset.campaign_id == campaign_id)
        .order_by(CampaignAsset.display_order.asc())
    ).all()

    audit_count = db.execute(
        select(func.count(CampaignAudit.id)).where(CampaignAudit.campaign_id == campaign_id)
    ).scalar() or 0
    audit_number = audit_count + 1

    audit = CampaignAudit(
        campaign_id=campaign_id,
        audit_number=audit_number,
        status="completed",
        readiness_outcome="ready_for_release",
        is_stale=False,
        asset_count=len(ca_rows),
        blocker_count=0,
        warning_count=0,
        review_required_count=0,
        passed_checks_count=0,
        created_by=actor_name,
    )
    db.add(audit)
    db.flush()

    findings: list[CampaignAuditFinding] = []
    evaluated_assets_summary = []
    evaluated_facts_versions: dict[str, int] = {}
    evaluated_rules_versions: dict[str, int] = {}

    if not ca_rows:
        audit.readiness_outcome = "needs_review"
        audit.review_required_count = 1
        finding = CampaignAuditFinding(
            audit_id=audit.id,
            finding_type="unreviewed_content",
            severity="warning",
            confidence="confirmed",
            explanation="Campaign currently has no assets attached.",
            recommended_action="Add one or more brand content assets to the campaign.",
            requires_human_review=True,
        )
        findings.append(finding)
        db.add(finding)
        db.commit()
        db.refresh(audit)
        return audit

    # Track claims across assets for cross-asset comparison
    asset_claims_collected: list[dict[str, Any]] = []

    # 1. Inspect each asset individually
    for ca, content_asset, sub in ca_rows:
        evaluated_assets_summary.append({
            "asset_id": str(content_asset.id),
            "title": content_asset.title,
            "submission_id": str(sub.id),
            "revision_number": sub.revision_number,
            "content_hash": sub.content_hash,
            "workflow_status": sub.workflow_status,
        })

        # Check A: Review run completeness
        run = db.execute(
            select(ReviewRun)
            .where(ReviewRun.content_submission_id == sub.id)
            .order_by(ReviewRun.started_at.desc())
        ).scalars().first()

        if not run:
            audit.blocker_count += 1
            findings.append(CampaignAuditFinding(
                audit_id=audit.id,
                asset_id=content_asset.id,
                submission_id=sub.id,
                revision_number=sub.revision_number,
                content_hash=sub.content_hash,
                finding_type="unreviewed_content",
                severity="hard_blocker",
                confidence="confirmed",
                explanation=f"Asset '{content_asset.title}' (revision {sub.revision_number}) has never been reviewed.",
                recommended_action="Run a content review on this revision.",
                requires_human_review=False,
            ))
        elif run.status == "failed":
            audit.blocker_count += 1
            findings.append(CampaignAuditFinding(
                audit_id=audit.id,
                asset_id=content_asset.id,
                submission_id=sub.id,
                revision_number=sub.revision_number,
                content_hash=sub.content_hash,
                finding_type="failed_review",
                severity="hard_blocker",
                confidence="confirmed",
                explanation=f"Latest review run for asset '{content_asset.title}' failed: {run.error_code or 'review_failure'}.",
                recommended_action="Re-run review to obtain a successful review verdict.",
                requires_human_review=False,
            ))
        else:
            audit.passed_checks_count += 1

            # Check findings for this review run
            review_findings = db.execute(
                select(ReviewFinding).where(ReviewFinding.review_run_id == run.id)
            ).scalars().all()

            for rf in review_findings:
                # Collect claim for cross-asset evaluation
                asset_claims_collected.append({
                    "asset": content_asset,
                    "submission": sub,
                    "finding": rf,
                    "claim_text": rf.claim_text,
                    "status": rf.status,
                })

                # Check evidence attached to finding
                ev = db.execute(
                    select(FindingEvidence).where(FindingEvidence.finding_id == rf.id)
                ).scalars().first()

                if rf.status == "conflicting":
                    audit.blocker_count += 1
                    findings.append(CampaignAuditFinding(
                        audit_id=audit.id,
                        asset_id=content_asset.id,
                        submission_id=sub.id,
                        revision_number=sub.revision_number,
                        content_hash=sub.content_hash,
                        finding_type="fact_contradiction",
                        severity="hard_blocker",
                        confidence="confirmed",
                        claim_text=rf.claim_text,
                        explanation=f"Claim in asset '{content_asset.title}' conflicts with approved brand facts.",
                        recommended_action="Revise content to align with approved fact specifications.",
                        related_review_finding_id=rf.id,
                        related_fact_id=ev.fact_id if ev else None,
                        related_fact_version=ev.fact_version if ev else None,
                        source_document_id=ev.source_document_id if ev else None,
                        source_page=ev.source_page if ev else None,
                        source_excerpt=ev.excerpt if ev else None,
                    ))


                elif rf.status in ("unsupported", "uncertain"):
                    audit.review_required_count += 1
                    audit.warning_count += 1
                    findings.append(CampaignAuditFinding(
                        audit_id=audit.id,
                        asset_id=content_asset.id,
                        submission_id=sub.id,
                        revision_number=sub.revision_number,
                        content_hash=sub.content_hash,
                        finding_type="human_review_required",
                        severity="warning",
                        confidence="uncertain",
                        claim_text=rf.claim_text,
                        explanation=f"Claim in asset '{content_asset.title}' is {rf.status} and requires human verification.",
                        recommended_action="Provide supporting documentation or approve an exception.",
                        requires_human_review=True,
                        related_review_finding_id=rf.id,
                    ))

                # Check if evidence fact has expired or been revised
                if ev and ev.fact_id:
                    fact = db.execute(select(ApprovedFact).where(ApprovedFact.id == ev.fact_id)).scalars().first()
                    if fact:
                        evaluated_facts_versions[str(fact.id)] = fact.version
                        if fact.version > ev.fact_version:
                            audit.blocker_count += 1
                            findings.append(CampaignAuditFinding(
                                audit_id=audit.id,
                                asset_id=content_asset.id,
                                submission_id=sub.id,
                                revision_number=sub.revision_number,
                                content_hash=sub.content_hash,
                                finding_type="outdated_fact",
                                severity="hard_blocker",
                                confidence="confirmed",
                                claim_text=rf.claim_text,
                                explanation=f"Claim in '{content_asset.title}' was reviewed against v{ev.fact_version} of '{fact.name}', but v{fact.version} is current.",
                                recommended_action="Re-review content against current fact version.",
                                related_fact_id=fact.id,
                                related_fact_version=fact.version,
                            ))

                        if fact.status == "expired":
                            audit.blocker_count += 1
                            findings.append(CampaignAuditFinding(
                                audit_id=audit.id,
                                asset_id=content_asset.id,
                                submission_id=sub.id,
                                revision_number=sub.revision_number,
                                content_hash=sub.content_hash,
                                finding_type="outdated_fact",
                                severity="hard_blocker",
                                confidence="confirmed",
                                claim_text=rf.claim_text,
                                explanation=f"Fact '{fact.name}' cited by '{content_asset.title}' has expired.",
                                recommended_action="Renew fact validity or remove the expired claim.",
                                related_fact_id=fact.id,
                            ))

        # Check B: Unresolved fact-change impacts
        open_impacts = db.execute(
            select(FactChangeImpact)
            .where(FactChangeImpact.content_submission_id == sub.id, FactChangeImpact.status == "needs_review")
        ).scalars().all()
        for imp in open_impacts:
            audit.blocker_count += 1
            findings.append(CampaignAuditFinding(
                audit_id=audit.id,
                asset_id=content_asset.id,
                submission_id=sub.id,
                revision_number=sub.revision_number,
                content_hash=sub.content_hash,
                finding_type="open_impact",
                severity="hard_blocker",
                confidence="confirmed",
                explanation=f"Asset '{content_asset.title}' has an open fact-change impact from fact change v{imp.from_version}->v{imp.to_version}.",
                recommended_action="Resolve or dismiss the fact-change impact via the revision workflow.",
                related_impact_id=imp.id,
                related_fact_id=imp.fact_id,
            ))

        # Check C: Asset approval status
        if sub.workflow_status != "approved":
            audit.blocker_count += 1
            findings.append(CampaignAuditFinding(
                audit_id=audit.id,
                asset_id=content_asset.id,
                submission_id=sub.id,
                revision_number=sub.revision_number,
                content_hash=sub.content_hash,
                finding_type="incomplete_approval",
                severity="hard_blocker",
                confidence="confirmed",
                explanation=f"Asset '{content_asset.title}' (revision {sub.revision_number}) is in '{sub.workflow_status}' status and has not been approved.",
                recommended_action="Review and approve the asset revision before campaign release.",
                requires_human_review=False,
            ))
        else:
            audit.passed_checks_count += 1

    # 2. Check active guideline compliance
    active_rules = db.execute(
        select(GuidelineRule).where(GuidelineRule.brand_id == campaign.brand_id, GuidelineRule.status == "active")
    ).scalars().all()

    for rule in active_rules:
        evaluated_rules_versions[str(rule.id)] = rule.current_version
        prohibited = []
        if rule.conditions and isinstance(rule.conditions, dict):
            prohibited = rule.conditions.get("prohibited_terms", [])
        if not prohibited and "prohibit" in rule.rule_text.lower():
            # Check for words in quotes
            quoted = re.findall(r'["\']([^"\']+)["\']', rule.rule_text)
            prohibited.extend(quoted)

        for ca, content_asset, sub in ca_rows:
            content_lower = sub.content.lower()
            for term in prohibited:
                if term.lower() in content_lower:
                    audit.blocker_count += 1
                    findings.append(CampaignAuditFinding(
                        audit_id=audit.id,
                        asset_id=content_asset.id,
                        submission_id=sub.id,
                        revision_number=sub.revision_number,
                        content_hash=sub.content_hash,
                        finding_type="guideline_violation",
                        severity="hard_blocker",
                        confidence="confirmed",
                        claim_text=term,
                        explanation=f"Asset '{content_asset.title}' contains prohibited term '{term}' violating active guideline rule '{rule.title}'.",
                        recommended_action=f"Replace prohibited term according to guideline rule: {rule.rule_text}",
                        related_rule_id=rule.id,
                        related_rule_version=rule.current_version,
                        source_document_id=rule.source_document_id,
                        source_page=rule.source_page,
                        source_excerpt=rule.source_excerpt,
                    ))

    # 3. Cross-Asset Consistency Analysis (Compare pairs of assets)
    if len(ca_rows) > 1:
        # Compare claims for contradictory values
        for i in range(len(asset_claims_collected)):
            for j in range(i + 1, len(asset_claims_collected)):
                item_a = asset_claims_collected[i]
                item_b = asset_claims_collected[j]

                # Skip if comparing same asset
                if item_a["asset"].id == item_b["asset"].id:
                    continue

                text_a = item_a["claim_text"]
                text_b = item_b["claim_text"]

                metrics_a = _extract_metric_numbers(text_a)
                metrics_b = _extract_metric_numbers(text_b)

                # Check if same unit mentioned with different numeric values
                for val_a, unit_a, raw_a in metrics_a:
                    for val_b, unit_b, raw_b in metrics_b:
                        # Normalize units (hours, hour -> hour; days, day -> day)
                        u_a = unit_a.rstrip('s')
                        u_b = unit_b.rstrip('s')
                        if u_a == u_b and val_a != val_b:
                            audit.blocker_count += 1
                            findings.append(CampaignAuditFinding(
                                audit_id=audit.id,
                                asset_id=item_a["asset"].id,
                                submission_id=item_a["submission"].id,
                                revision_number=item_a["submission"].revision_number,
                                content_hash=item_a["submission"].content_hash,
                                finding_type="cross_asset_inconsistency",
                                severity="hard_blocker",
                                confidence="confirmed",
                                claim_text=f"'{raw_a}' vs '{raw_b}'",
                                explanation=f"Incompatible metrics: '{item_a['asset'].title}' claims '{raw_a}' while '{item_b['asset'].title}' claims '{raw_b}'.",
                                recommended_action="Harmonize specifications and performance metrics across campaign assets.",
                                related_asset_id=item_b["asset"].id,
                                related_submission_id=item_b["submission"].id,
                            ))

                # Check if one asset is supported and the other is conflicting regarding the same fact
                ev_a = db.execute(
                    select(FindingEvidence).where(FindingEvidence.finding_id == item_a["finding"].id)
                ).scalars().first()
                ev_b = db.execute(
                    select(FindingEvidence).where(FindingEvidence.finding_id == item_b["finding"].id)
                ).scalars().first()


                if ev_a and ev_b and ev_a.fact_id and ev_a.fact_id == ev_b.fact_id:
                    if (item_a["status"] == "supported" and item_b["status"] == "conflicting") or (
                        item_a["status"] == "conflicting" and item_b["status"] == "supported"
                    ):
                        fact = db.execute(select(ApprovedFact).where(ApprovedFact.id == ev_a.fact_id)).scalars().first()
                        fact_name = fact.name if fact else "fact"
                        audit.blocker_count += 1
                        findings.append(CampaignAuditFinding(
                            audit_id=audit.id,
                            asset_id=item_a["asset"].id,
                            submission_id=item_a["submission"].id,
                            revision_number=item_a["submission"].revision_number,
                            content_hash=item_a["submission"].content_hash,
                            finding_type="cross_asset_inconsistency",
                            severity="hard_blocker",
                            confidence="confirmed",
                            claim_text=f"'{text_a}' vs '{text_b}'",
                            explanation=f"Contradiction regarding approved fact '{fact_name}': '{item_a['asset'].title}' has status {item_a['status']} while '{item_b['asset'].title}' has status {item_b['status']}.",
                            recommended_action="Ensure both assets make consistent and verified claims.",
                            related_asset_id=item_b["asset"].id,
                            related_submission_id=item_b["submission"].id,
                            related_fact_id=ev_a.fact_id,
                        ))

    # Determine readiness outcome
    if audit.blocker_count > 0:
        audit.readiness_outcome = "blocked"
    elif audit.review_required_count > 0:
        audit.readiness_outcome = "needs_review"
    else:
        audit.readiness_outcome = "ready_for_release"

    audit.summary = {
        "evaluated_assets": evaluated_assets_summary,
        "evaluated_facts_versions": evaluated_facts_versions,
        "evaluated_rules_versions": evaluated_rules_versions,
        "checks_executed": [
            "review_completeness",
            "asset_approval_status",
            "fact_consistency",
            "fact_expiry_and_impacts",
            "human_review_requirements",
            "guideline_compliance",
            "cross_asset_consistency",
        ],
    }

    # Persist all findings
    for f in findings:
        db.add(f)

    # Update campaign status if not already released
    if campaign.status != "released":
        campaign.status = audit.readiness_outcome

    db.commit()
    db.refresh(audit)
    return audit


def get_campaign_audit(db: Session, audit_id: uuid.UUID) -> Optional[dict[str, Any]]:
    audit = db.execute(select(CampaignAudit).where(CampaignAudit.id == audit_id)).scalars().first()
    if not audit:
        return None

    # Check staleness on fetch
    check_campaign_audit_staleness(db, audit.campaign_id, audit)

    findings = db.execute(
        select(CampaignAuditFinding, ContentAsset.title.label("asset_title"))
        .outerjoin(ContentAsset, ContentAsset.id == CampaignAuditFinding.asset_id)
        .where(CampaignAuditFinding.audit_id == audit_id)
        .order_by(CampaignAuditFinding.severity.desc(), CampaignAuditFinding.created_at.asc())
    ).all()

    finding_outs = []
    for f, asset_title in findings:
        related_title = None
        if f.related_asset_id:
            rel = db.execute(select(ContentAsset.title).where(ContentAsset.id == f.related_asset_id)).scalar()
            related_title = rel

        finding_outs.append(CampaignAuditFindingOut(
            id=f.id,
            audit_id=f.audit_id,
            asset_id=f.asset_id,
            asset_title=asset_title,
            submission_id=f.submission_id,
            revision_number=f.revision_number,
            content_hash=f.content_hash,
            finding_type=f.finding_type,
            severity=f.severity,
            confidence=f.confidence,
            claim_text=f.claim_text,
            explanation=f.explanation,
            recommended_action=f.recommended_action,
            requires_human_review=f.requires_human_review,
            related_asset_id=f.related_asset_id,
            related_asset_title=related_title,
            related_submission_id=f.related_submission_id,
            related_fact_id=f.related_fact_id,
            related_fact_version=f.related_fact_version,
            related_rule_id=f.related_rule_id,
            related_rule_version=f.related_rule_version,
            related_impact_id=f.related_impact_id,
            related_review_finding_id=f.related_review_finding_id,
            source_document_id=f.source_document_id,
            source_page=f.source_page,
            source_excerpt=f.source_excerpt,
            created_at=f.created_at,
        ))

    return {
        "id": audit.id,
        "campaign_id": audit.campaign_id,
        "audit_number": audit.audit_number,
        "status": audit.status,
        "readiness_outcome": audit.readiness_outcome,
        "is_stale": audit.is_stale,
        "stale_reason": audit.stale_reason,
        "asset_count": audit.asset_count,
        "blocker_count": audit.blocker_count,
        "warning_count": audit.warning_count,
        "review_required_count": audit.review_required_count,
        "passed_checks_count": audit.passed_checks_count,
        "summary": audit.summary,
        "created_by": audit.created_by,
        "created_at": audit.created_at,
        "findings": finding_outs,
    }


def list_campaign_audits(db: Session, campaign_id: uuid.UUID) -> list[CampaignAudit]:
    query = select(CampaignAudit).where(CampaignAudit.campaign_id == campaign_id).order_by(CampaignAudit.audit_number.desc())
    audits = list(db.execute(query).scalars().all())
    for audit in audits:
        check_campaign_audit_staleness(db, campaign_id, audit)
    return audits


def compare_campaign_audits(db: Session, audit_id: uuid.UUID, previous_audit_id: uuid.UUID) -> AuditComparisonOut:
    """Compares current audit findings against a previous audit snapshot."""
    curr = get_campaign_audit(db, audit_id)
    prev = get_campaign_audit(db, previous_audit_id)

    if not curr or not prev:
        raise CampaignAuditError("audit_not_found", "One or both audits not found", 404)

    curr_findings = curr["findings"]
    prev_findings = prev["findings"]

    def _make_key(f: CampaignAuditFindingOut) -> str:
        # Identify finding by type, asset_id, and claim text / core explanation
        aid = str(f.asset_id or "")
        return f"{f.finding_type}:{aid}:{f.claim_text or f.explanation[:40]}"

    prev_map = {_make_key(f): f for f in prev_findings}
    curr_map = {_make_key(f): f for f in curr_findings}

    new_findings = []
    persistent_findings = []
    resolved_findings = []
    unevaluable_findings = []

    for k, f in curr_map.items():
        if f.confidence == "not_evaluable":
            unevaluable_findings.append(f)
        elif k in prev_map:
            persistent_findings.append(f)
        else:
            new_findings.append(f)

    for k, f in prev_map.items():
        if k not in curr_map:
            resolved_findings.append(f)

    return AuditComparisonOut(
        audit_id=audit_id,
        previous_audit_id=previous_audit_id,
        new_findings=new_findings,
        persistent_findings=persistent_findings,
        resolved_findings=resolved_findings,
        unevaluable_findings=unevaluable_findings,
        summary={
            "new_count": len(new_findings),
            "persistent_count": len(persistent_findings),
            "resolved_count": len(resolved_findings),
            "unevaluable_count": len(unevaluable_findings),
        },
    )


def evaluate_release_readiness(db: Session, campaign_id: uuid.UUID) -> ReleaseEvaluationOut:
    """Evaluates whether the campaign passes all release criteria."""
    campaign = db.execute(select(Campaign).where(Campaign.id == campaign_id)).scalars().first()
    if not campaign:
        raise CampaignAuditError("campaign_not_found", "Campaign not found", 404)

    latest_audit = db.execute(
        select(CampaignAudit)
        .where(CampaignAudit.campaign_id == campaign_id)
        .order_by(CampaignAudit.audit_number.desc())
    ).scalars().first()

    blockers = []
    if not latest_audit:
        blockers.append("No campaign audit has been executed.")
        return ReleaseEvaluationOut(
            campaign_id=campaign_id,
            status=campaign.status,
            is_stale=True,
            can_release=False,
            blocker_count=1,
            warning_count=0,
            review_required_count=0,
            blockers=blockers,
        )

    is_stale, reason = check_campaign_audit_staleness(db, campaign_id, latest_audit)
    if is_stale:
        blockers.append(f"Campaign audit is stale: {reason or 'Assets or dependencies changed.'}")

    if latest_audit.blocker_count > 0:
        blockers.append(f"{latest_audit.blocker_count} hard release blocker(s) must be resolved.")

    if latest_audit.review_required_count > 0:
        blockers.append(f"{latest_audit.review_required_count} human review requirement(s) pending.")

    # Check that individual assets are all approved
    ca_rows = db.execute(
        select(ContentSubmission.workflow_status, ContentAsset.title)
        .join(CampaignAsset, CampaignAsset.selected_submission_id == ContentSubmission.id)
        .join(ContentAsset, ContentAsset.id == CampaignAsset.asset_id)
        .where(CampaignAsset.campaign_id == campaign_id)
    ).all()

    for wf_status, title in ca_rows:
        if wf_status != "approved":
            blockers.append(f"Asset '{title}' is not approved (status: {wf_status}).")

    can_release = (len(blockers) == 0 and not is_stale and latest_audit.readiness_outcome == "ready_for_release")

    return ReleaseEvaluationOut(
        campaign_id=campaign_id,
        status=campaign.status,
        is_stale=is_stale,
        can_release=can_release,
        blocker_count=latest_audit.blocker_count,
        warning_count=latest_audit.warning_count,
        review_required_count=latest_audit.review_required_count,
        blockers=blockers,
        audit_id=latest_audit.id,
        readiness_outcome=latest_audit.readiness_outcome,
    )


def release_campaign(
    db: Session, campaign_id: uuid.UUID, actor_name: str, actor_role: str, release_notes: Optional[str] = None
) -> CampaignReleaseDecision:
    """Executes the guarded release transition of an audited, ready campaign."""
    if actor_role != "reviewer":
        raise CampaignAuditError("reviewer_required", "Only users with the reviewer role can release a campaign.", 403)

    evaluation = evaluate_release_readiness(db, campaign_id)
    if not evaluation.can_release:
        if evaluation.is_stale:
            raise CampaignAuditError("audit_stale", "Cannot release: campaign audit is stale. Run a fresh audit.", 422)
        raise CampaignAuditError(
            "release_blocked",
            f"Cannot release campaign: {'; '.join(evaluation.blockers)}",
            422,
        )

    campaign = db.execute(select(Campaign).where(Campaign.id == campaign_id)).scalars().first()
    campaign.status = "released"
    campaign.released_at = datetime.now()
    campaign.released_by = actor_name
    campaign.release_notes = release_notes

    decision = CampaignReleaseDecision(
        campaign_id=campaign_id,
        audit_id=evaluation.audit_id,
        decision="released",
        actor_name=actor_name,
        actor_role=actor_role,
        release_notes=release_notes,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision
