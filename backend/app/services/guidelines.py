"""Service for managing Guideline Rules, Rule Versions, Document Extraction, and Guideline Linting."""
import re
import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, Forbidden, NotFoundError, ValidationFailed, field_error
from app.models.guideline import GuidelineLintResult, GuidelineRule, GuidelineRuleVersion
from app.models.source_document import DocumentSection, SourceDocument
from app.schemas.guideline import (
    GuidelineLintIssueOut, GuidelineLintResponse, GuidelineRuleCreate, GuidelineRuleListOut, GuidelineRuleOut,
    GuidelineRuleUpdate, GuidelineRuleVersionCreate, GuidelineRuleVersionOut,
)

VAGUE_TERMS = (
    "high quality", "best-in-class", "innovative", "modern", "appropriate",
    "reasonable", "industry-leading", "market-leading", "world-class", "suitable", "cutting-edge",
    "optimal", "superior", "state-of-the-art", "best",
)
CONDITIONAL_TRIGGERS = (
    "when", "if ", "unless", "except", "only with approval", "permitted when", "subject to",
)
VALID_SCOPES = ("all", "headline", "body", "disclaimer", "claim", "pricing", "packaging")


def _version_to_out(v: GuidelineRuleVersion) -> GuidelineRuleVersionOut:
    return GuidelineRuleVersionOut(
        id=v.id,
        rule_id=v.rule_id,
        version_number=v.version_number,
        rule_text=v.rule_text,
        conditions=v.conditions,
        examples=v.examples,
        source_reference=v.source_reference,
        change_reason=v.change_reason,
        created_by=v.created_by,
        created_at=v.created_at,
    )


def _rule_to_out(rule: GuidelineRule, versions: list[GuidelineRuleVersion] | None = None) -> GuidelineRuleOut:
    version_outs = [_version_to_out(v) for v in (versions or [])]
    return GuidelineRuleOut(
        id=rule.id,
        brand_id=rule.brand_id,
        title=rule.title,
        description=rule.description,
        rule_text=rule.rule_text,
        category=rule.category,
        severity=rule.severity,
        scope=rule.scope,
        conditions=rule.conditions,
        examples=rule.examples,
        status=rule.status,
        source_document_id=rule.source_document_id,
        source_page=rule.source_page,
        source_excerpt=rule.source_excerpt,
        owner=rule.owner,
        created_by=rule.created_by,
        current_version=rule.current_version,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        versions=version_outs,
    )


def list_rules(
    db: Session,
    brand_id: uuid.UUID,
    status: str | None = None,
    category: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> GuidelineRuleListOut:
    query = select(GuidelineRule).where(GuidelineRule.brand_id == brand_id)
    if status:
        query = query.where(GuidelineRule.status == status)
    if category:
        query = query.where(GuidelineRule.category == category)
    query = query.order_by(GuidelineRule.created_at.desc())

    total = db.scalar(select(func.count(GuidelineRule.id)).where(GuidelineRule.brand_id == brand_id)) or 0
    active_count = db.scalar(
        select(func.count(GuidelineRule.id)).where(GuidelineRule.brand_id == brand_id, GuidelineRule.status == "active")
    ) or 0
    proposed_count = db.scalar(
        select(func.count(GuidelineRule.id)).where(GuidelineRule.brand_id == brand_id, GuidelineRule.status == "proposed")
    ) or 0
    retired_count = db.scalar(
        select(func.count(GuidelineRule.id)).where(GuidelineRule.brand_id == brand_id, GuidelineRule.status == "retired")
    ) or 0

    rules = list(db.scalars(query.offset(offset).limit(limit)))
    rule_ids = [r.id for r in rules]
    versions_by_rule: dict[uuid.UUID, list[GuidelineRuleVersion]] = {rid: [] for rid in rule_ids}
    if rule_ids:
        vers = db.scalars(
            select(GuidelineRuleVersion)
            .where(GuidelineRuleVersion.rule_id.in_(rule_ids))
            .order_by(GuidelineRuleVersion.version_number.desc())
        )
        for v in vers:
            versions_by_rule[v.rule_id].append(v)

    items = [_rule_to_out(r, versions_by_rule.get(r.id, [])) for r in rules]
    return GuidelineRuleListOut(
        items=items,
        total=total,
        active_count=active_count,
        proposed_count=proposed_count,
        retired_count=retired_count,
    )


def get_rule(db: Session, rule_id: uuid.UUID, brand_id: uuid.UUID | None = None) -> GuidelineRuleOut:
    query = select(GuidelineRule).where(GuidelineRule.id == rule_id)
    if brand_id:
        query = query.where(GuidelineRule.brand_id == brand_id)
    rule = db.scalar(query)
    if not rule:
        raise NotFoundError("Guideline rule not found.", code="rule_not_found")
    versions = list(
        db.scalars(
            select(GuidelineRuleVersion)
            .where(GuidelineRuleVersion.rule_id == rule_id)
            .order_by(GuidelineRuleVersion.version_number.desc())
        )
    )
    return _rule_to_out(rule, versions)


def create_rule(
    db: Session,
    brand_id: uuid.UUID,
    data: GuidelineRuleCreate,
    actor_name: str,
    actor_role: str,
) -> GuidelineRuleOut:
    # Validate source document if provided
    if data.source_document_id:
        doc = db.scalar(
            select(SourceDocument).where(
                SourceDocument.id == data.source_document_id, SourceDocument.brand_id == brand_id
            )
        )
        if not doc:
            raise ValidationFailed(
                "Source document not found for this brand.",
                details=[field_error("source_document_id", "Must belong to the same brand.")],
            )

    # Creators can only create "proposed" rules. Only reviewers can create active rules directly.
    status = data.status
    if status == "active" and actor_role != "reviewer":
        status = "proposed"

    rule = GuidelineRule(
        brand_id=brand_id,
        title=data.title.strip(),
        description=data.description.strip() if data.description else None,
        rule_text=data.rule_text.strip(),
        category=data.category.strip() or "general",
        severity=data.severity.strip() or "medium",
        scope=data.scope.strip() or "all",
        conditions=data.conditions,
        examples=data.examples,
        status=status,
        source_document_id=data.source_document_id,
        source_page=data.source_page,
        source_excerpt=data.source_excerpt.strip() if data.source_excerpt else None,
        owner=data.owner.strip() if data.owner else None,
        created_by=actor_name,
        current_version=1,
    )
    db.add(rule)
    db.flush()

    source_ref = None
    if rule.source_document_id:
        source_ref = {
            "source_document_id": str(rule.source_document_id),
            "source_page": rule.source_page,
            "source_excerpt": rule.source_excerpt,
        }

    version1 = GuidelineRuleVersion(
        rule_id=rule.id,
        version_number=1,
        rule_text=rule.rule_text,
        conditions=rule.conditions,
        examples=rule.examples,
        source_reference=source_ref,
        change_reason="Initial rule creation",
        created_by=actor_name,
    )
    db.add(version1)
    db.commit()
    db.refresh(rule)
    db.refresh(version1)
    return _rule_to_out(rule, [version1])


def update_rule(
    db: Session,
    rule_id: uuid.UUID,
    data: GuidelineRuleUpdate,
    actor_name: str,
    actor_role: str,
) -> GuidelineRuleOut:
    rule = db.scalar(select(GuidelineRule).where(GuidelineRule.id == rule_id))
    if not rule:
        raise NotFoundError("Guideline rule not found.", code="rule_not_found")

    # Authorisation checks for status changes
    if data.status and data.status != rule.status:
        if actor_role != "reviewer":
            raise Forbidden("Only an authorized reviewer can change rule status.", code="reviewer_role_required")
        rule.status = data.status

    text_changed = data.rule_text is not None and data.rule_text.strip() != rule.rule_text
    conditions_changed = data.conditions is not None and data.conditions != rule.conditions
    examples_changed = data.examples is not None and data.examples != rule.examples

    if data.title is not None:
        rule.title = data.title.strip()
    if data.description is not None:
        rule.description = data.description.strip() if data.description else None
    if data.category is not None:
        rule.category = data.category.strip()
    if data.severity is not None:
        rule.severity = data.severity.strip()
    if data.scope is not None:
        rule.scope = data.scope.strip()
    if data.owner is not None:
        rule.owner = data.owner.strip() if data.owner else None
    if data.source_document_id is not None:
        doc = db.scalar(
            select(SourceDocument).where(
                SourceDocument.id == data.source_document_id, SourceDocument.brand_id == rule.brand_id
            )
        )
        if not doc:
            raise ValidationFailed(
                "Source document not found for this brand.",
                details=[field_error("source_document_id", "Must belong to the same brand.")],
            )
        rule.source_document_id = data.source_document_id
    if data.source_page is not None:
        rule.source_page = data.source_page
    if data.source_excerpt is not None:
        rule.source_excerpt = data.source_excerpt.strip() if data.source_excerpt else None

    new_version_record = None
    if text_changed or conditions_changed or examples_changed:
        if text_changed and data.rule_text is not None:
            rule.rule_text = data.rule_text.strip()
        if conditions_changed:
            rule.conditions = data.conditions
        if examples_changed:
            rule.examples = data.examples

        # If rule was active and creator edited it, it returns to proposed unless reviewer approved it
        if rule.status == "active" and actor_role != "reviewer":
            rule.status = "proposed"

        source_ref = None
        if rule.source_document_id:
            source_ref = {
                "source_document_id": str(rule.source_document_id),
                "source_page": rule.source_page,
                "source_excerpt": rule.source_excerpt,
            }

        existing_v = db.scalar(
            select(GuidelineRuleVersion).where(
                GuidelineRuleVersion.rule_id == rule.id,
                GuidelineRuleVersion.rule_text == rule.rule_text,
            ).order_by(GuidelineRuleVersion.version_number.desc())
        )
        if existing_v:
            rule.current_version = existing_v.version_number
        else:
            max_v = db.scalar(
                select(func.coalesce(func.max(GuidelineRuleVersion.version_number), 0)).where(
                    GuidelineRuleVersion.rule_id == rule.id
                )
            ) or 0
            rule.current_version = max_v + 1
            new_version_record = GuidelineRuleVersion(
                rule_id=rule.id,
                version_number=rule.current_version,
                rule_text=rule.rule_text,
                conditions=rule.conditions,
                examples=rule.examples,
                source_reference=source_ref,
                change_reason=data.change_reason or "Rule updated",
                created_by=actor_name,
            )
            db.add(new_version_record)

    db.commit()
    db.refresh(rule)
    versions = list(
        db.scalars(
            select(GuidelineRuleVersion)
            .where(GuidelineRuleVersion.rule_id == rule_id)
            .order_by(GuidelineRuleVersion.version_number.desc())
        )
    )
    return _rule_to_out(rule, versions)


def create_rule_version(
    db: Session,
    rule_id: uuid.UUID,
    data: GuidelineRuleVersionCreate,
    actor_name: str,
    actor_role: str,
) -> GuidelineRuleVersionOut:
    rule = db.scalar(select(GuidelineRule).where(GuidelineRule.id == rule_id))
    if not rule:
        raise NotFoundError("Guideline rule not found.", code="rule_not_found")

    max_v = db.scalar(
        select(func.coalesce(func.max(GuidelineRuleVersion.version_number), 0)).where(
            GuidelineRuleVersion.rule_id == rule_id
        )
    ) or 0
    next_v = max_v + 1

    ver = GuidelineRuleVersion(
        rule_id=rule.id,
        version_number=next_v,
        rule_text=data.rule_text.strip(),
        conditions=data.conditions,
        examples=data.examples,
        source_reference=data.source_reference,
        change_reason=data.change_reason or f"Proposed version {next_v}",
        created_by=actor_name,
    )
    db.add(ver)
    db.commit()
    db.refresh(ver)
    return _version_to_out(ver)


def list_versions(db: Session, rule_id: uuid.UUID) -> list[GuidelineRuleVersionOut]:
    rule = db.scalar(select(GuidelineRule).where(GuidelineRule.id == rule_id))
    if not rule:
        raise NotFoundError("Guideline rule not found.", code="rule_not_found")
    vers = list(
        db.scalars(
            select(GuidelineRuleVersion)
            .where(GuidelineRuleVersion.rule_id == rule_id)
            .order_by(GuidelineRuleVersion.version_number.desc())
        )
    )
    return [_version_to_out(v) for v in vers]


# --------------------------------------------------------------------- Document Extraction
def extract_rules_from_document(
    db: Session,
    brand_id: uuid.UUID,
    document_id: uuid.UUID,
    actor_name: str,
) -> list[GuidelineRuleOut]:
    doc = db.scalar(
        select(SourceDocument).where(SourceDocument.id == document_id, SourceDocument.brand_id == brand_id)
    )
    if not doc:
        raise NotFoundError("Source document not found for this brand.", code="document_not_found")
    if doc.processing_status != "processed":
        raise ValidationFailed("Document has not been processed yet.", details=[field_error("document_id", "Must be processed.")])

    sections = list(
        db.scalars(
            select(DocumentSection)
            .where(DocumentSection.document_id == document_id)
            .order_by(DocumentSection.page_number.asc(), DocumentSection.section_index.asc())
        )
    )

    extracted_rules: list[GuidelineRuleOut] = []
    seen_texts: set[str] = set()

    # Deterministic pattern extraction based on regulatory / guideline markers
    rule_patterns = [
        (re.compile(r"([^.?!;\n]*\b(?:must not|prohibited|never|do not use|cannot be used)\b[^.?!;\n]*[.?!])", re.I), "prohibition"),
        (re.compile(r"([^.?!;\n]*\b(?:must|always|required|mandatory|shall)\b[^.?!;\n]*[.?!])", re.I), "requirement"),
        (re.compile(r"([^.?!;\n]*\b(?:comparative|comparison|competitor|better than|faster than)\b[^.?!;\n]*[.?!])", re.I), "comparative"),
        (re.compile(r"([^.?!;\n]*\b(?:terminology|spelling|capitalization|refer to|naming)\b[^.?!;\n]*[.?!])", re.I), "terminology"),
    ]

    for sec in sections:
        text = sec.text or ""
        for pattern, kind in rule_patterns:
            matches = pattern.findall(text)
            for raw_match in matches:
                clean = re.sub(r"\s+", " ", raw_match).strip()
                if len(clean) < 15 or clean.lower() in seen_texts:
                    continue
                seen_texts.add(clean.lower())

                # Categorise rule
                category = "general"
                severity = "medium"
                if "comparative" in clean.lower() or kind == "comparative":
                    category = "comparative"
                    severity = "high"
                elif "terminology" in clean.lower() or "spelling" in clean.lower() or kind == "terminology":
                    category = "terminology"
                    severity = "medium"
                elif kind == "prohibition":
                    category = "claim"
                    severity = "high"
                elif "disclosure" in clean.lower() or "disclaimer" in clean.lower():
                    category = "disclosure"
                    severity = "high"

                title = f"{category.capitalize()} rule (Page {sec.page_number})"
                if len(clean) <= 60:
                    title = clean
                else:
                    title = clean[:57].rstrip() + "..."

                # Extract potential conditions deterministically
                conditions = None
                if kind == "prohibition":
                    # Try to extract prohibited term
                    proh_match = re.search(r'(?:do not use|prohibited|never use|must not use)\s+["\']?([^"\'.,;]+)["\']?', clean, re.I)
                    if proh_match:
                        conditions = {"prohibited_terms": [proh_match.group(1).strip()]}
                elif kind == "comparative" and ("prohibited" in clean.lower() or "must not" in clean.lower()):
                    conditions = {"comparative_prohibited": True}

                rule = GuidelineRule(
                    brand_id=brand_id,
                    title=title,
                    description=f"Extracted from {doc.filename} page {sec.page_number}",
                    rule_text=clean,
                    category=category,
                    severity=severity,
                    scope="all",
                    conditions=conditions,
                    examples=None,
                    status="proposed",  # ALWAYS proposed upon extraction!
                    source_document_id=doc.id,
                    source_page=sec.page_number,
                    source_excerpt=clean,
                    owner="Extracted",
                    created_by=actor_name,
                    current_version=1,
                )
                db.add(rule)
                db.flush()

                v1 = GuidelineRuleVersion(
                    rule_id=rule.id,
                    version_number=1,
                    rule_text=rule.rule_text,
                    conditions=rule.conditions,
                    examples=None,
                    source_reference={
                        "source_document_id": str(doc.id),
                        "source_page": sec.page_number,
                        "source_excerpt": clean,
                    },
                    change_reason="Extracted from brand document",
                    created_by=actor_name,
                )
                db.add(v1)
                db.flush()
                extracted_rules.append(_rule_to_out(rule, [v1]))

    db.commit()
    return extracted_rules


# --------------------------------------------------------------------- Guideline Linting Engine
def lint_brand_rules(
    db: Session,
    brand_id: uuid.UUID,
    rule_id: uuid.UUID | None = None,
) -> GuidelineLintResponse:
    query = select(GuidelineRule).where(
        GuidelineRule.brand_id == brand_id,
        GuidelineRule.status.in_(("active", "proposed")),
    )
    if rule_id:
        query = query.where(GuidelineRule.id == rule_id)
    rules = list(db.scalars(query.order_by(GuidelineRule.created_at.asc())))

    # Clear previous lint results for these rules to keep lint idempotent
    target_rule_ids = [r.id for r in rules]
    if target_rule_ids:
        prev_lints = list(
            db.scalars(select(GuidelineLintResult).where(GuidelineLintResult.rule_id.in_(target_rule_ids)))
        )
        for pl in prev_lints:
            db.delete(pl)
        db.flush()

    issues: list[GuidelineLintIssueOut] = []

    # 1. Individual rule inspections
    for r in rules:
        text_lower = r.rule_text.lower()

        # Check A: Unclear or missing scope
        if not r.scope or r.scope.strip().lower() not in VALID_SCOPES:
            issue = GuidelineLintResult(
                brand_id=brand_id,
                rule_id=r.id,
                rule_version=r.current_version,
                issue_category="unclear_scope",
                severity="low",
                explanation=f"Rule '{r.title}' has unspecified or unrecognized scope '{r.scope}'.",
                suggested_action="Specify an explicit target scope such as 'all', 'headline', 'body', or 'disclaimer'.",
                requires_human_review=True,
            )
            db.add(issue)
            db.flush()
            issues.append(
                GuidelineLintIssueOut(
                    id=issue.id,
                    rule_id=r.id,
                    rule_title=r.title,
                    rule_version=r.current_version,
                    issue_category=issue.issue_category,
                    severity=issue.severity,
                    explanation=issue.explanation,
                    suggested_action=issue.suggested_action,
                    requires_human_review=True,
                    created_at=issue.created_at,
                )
            )

        # Check B: Vague instructions without measurable examples
        has_vague_term = next((term for term in VAGUE_TERMS if term in text_lower), None)
        has_examples = bool(r.examples and len(r.examples) > 0)
        if has_vague_term and not has_examples:
            issue = GuidelineLintResult(
                brand_id=brand_id,
                rule_id=r.id,
                rule_version=r.current_version,
                issue_category="vague_instruction",
                severity="medium",
                explanation=f"Rule '{r.title}' uses subjective term '{has_vague_term}' without measurable criteria or examples.",
                suggested_action="Add approved positive and non-compliant negative examples or measurable guidelines.",
                requires_human_review=True,
            )
            db.add(issue)
            db.flush()
            issues.append(
                GuidelineLintIssueOut(
                    id=issue.id,
                    rule_id=r.id,
                    rule_title=r.title,
                    rule_version=r.current_version,
                    issue_category=issue.issue_category,
                    severity=issue.severity,
                    explanation=issue.explanation,
                    suggested_action=issue.suggested_action,
                    requires_human_review=True,
                    created_at=issue.created_at,
                )
            )

        # Check C: Missing conditions when conditional language is present
        has_cond_trigger = next((trig for trig in CONDITIONAL_TRIGGERS if trig in text_lower), None)
        has_conditions = bool(r.conditions and len(r.conditions) > 0)
        if has_cond_trigger and not has_conditions:
            issue = GuidelineLintResult(
                brand_id=brand_id,
                rule_id=r.id,
                rule_version=r.current_version,
                issue_category="missing_conditions",
                severity="medium",
                explanation=f"Rule '{r.title}' contains conditional phrasing ('{has_cond_trigger}') but lacks executable conditions.",
                suggested_action="Add structured condition parameters (e.g. required terms, prohibited terms, or allowed qualifiers).",
                requires_human_review=True,
            )
            db.add(issue)
            db.flush()
            issues.append(
                GuidelineLintIssueOut(
                    id=issue.id,
                    rule_id=r.id,
                    rule_title=r.title,
                    rule_version=r.current_version,
                    issue_category=issue.issue_category,
                    severity=issue.severity,
                    explanation=issue.explanation,
                    suggested_action=issue.suggested_action,
                    requires_human_review=True,
                    created_at=issue.created_at,
                )
            )

        # Check D: Missing examples for terminology/claim rules
        if r.category in ("terminology", "comparative", "claim") and not has_examples:
            issue = GuidelineLintResult(
                brand_id=brand_id,
                rule_id=r.id,
                rule_version=r.current_version,
                issue_category="missing_examples",
                severity="low",
                explanation=f"Rule '{r.title}' governs {r.category} but has no concrete examples.",
                suggested_action="Provide practical positive and negative examples to help content creators understand usage.",
                requires_human_review=True,
            )
            db.add(issue)
            db.flush()
            issues.append(
                GuidelineLintIssueOut(
                    id=issue.id,
                    rule_id=r.id,
                    rule_title=r.title,
                    rule_version=r.current_version,
                    issue_category=issue.issue_category,
                    severity=issue.severity,
                    explanation=issue.explanation,
                    suggested_action=issue.suggested_action,
                    requires_human_review=True,
                    created_at=issue.created_at,
                )
            )

    # 2. Cross-rule conflict detection across the brand's rules
    for i, r1 in enumerate(rules):
        for j, r2 in enumerate(rules):
            if i >= j:
                continue

            # Check 1: Terminology conflict (One requires what another prohibits)
            cond1 = r1.conditions or {}
            cond2 = r2.conditions or {}
            req1 = set(t.lower() for t in cond1.get("required_terms", []))
            proh1 = set(t.lower() for t in cond1.get("prohibited_terms", []))
            req2 = set(t.lower() for t in cond2.get("required_terms", []))
            proh2 = set(t.lower() for t in cond2.get("prohibited_terms", []))

            conflict_terms = (req1 & proh2) | (req2 & proh1)
            if conflict_terms:
                conflict_term = list(conflict_terms)[0]
                issue = GuidelineLintResult(
                    brand_id=brand_id,
                    rule_id=r1.id,
                    rule_version=r1.current_version,
                    issue_category="potential_conflict",
                    severity="high",
                    explanation=f"Potential conflict: Rule '{r1.title}' and Rule '{r2.title}' give contradictory instructions regarding term '{conflict_term}'.",
                    related_rule_id=r2.id,
                    suggested_action="Reconcile terminology instructions between these two rules.",
                    requires_human_review=True,
                )
                db.add(issue)
                db.flush()
                issues.append(
                    GuidelineLintIssueOut(
                        id=issue.id,
                        rule_id=r1.id,
                        rule_title=r1.title,
                        rule_version=r1.current_version,
                        issue_category=issue.issue_category,
                        severity=issue.severity,
                        explanation=issue.explanation,
                        related_rule_id=r2.id,
                        related_rule_title=r2.title,
                        suggested_action=issue.suggested_action,
                        requires_human_review=True,
                        created_at=issue.created_at,
                    )
                )

            # Check 2: Comparative claims contradiction
            # e.g. One rule prohibits comparative claims, another explicitly permits them in overlapping scope
            r1_forbids_comp = (
                r1.category == "comparative" and (
                    cond1.get("comparative_prohibited") is True
                    or "must not" in r1.rule_text.lower()
                    or "prohibited" in r1.rule_text.lower()
                    or "never" in r1.rule_text.lower()
                )
            )
            r2_allows_comp = (
                r2.category == "comparative" and (
                    cond2.get("comparative_permitted") is True
                    or "may be used" in r2.rule_text.lower()
                    or "permitted" in r2.rule_text.lower()
                    or "allowed" in r2.rule_text.lower()
                )
            )
            r2_forbids_comp = (
                r2.category == "comparative" and (
                    cond2.get("comparative_prohibited") is True
                    or "must not" in r2.rule_text.lower()
                    or "prohibited" in r2.rule_text.lower()
                    or "never" in r2.rule_text.lower()
                )
            )
            r1_allows_comp = (
                r1.category == "comparative" and (
                    cond1.get("comparative_permitted") is True
                    or "may be used" in r1.rule_text.lower()
                    or "permitted" in r1.rule_text.lower()
                    or "allowed" in r1.rule_text.lower()
                )
            )

            if (r1_forbids_comp and r2_allows_comp) or (r2_forbids_comp and r1_allows_comp):
                issue = GuidelineLintResult(
                    brand_id=brand_id,
                    rule_id=r1.id,
                    rule_version=r1.current_version,
                    issue_category="potential_conflict",
                    severity="high",
                    explanation=f"Potential conflict: Rule '{r1.title}' and Rule '{r2.title}' specify contradictory comparative claim permissions.",
                    related_rule_id=r2.id,
                    suggested_action="Harmonize comparative claim policy across brand guidelines.",
                    requires_human_review=True,
                )
                db.add(issue)
                db.flush()
                issues.append(
                    GuidelineLintIssueOut(
                        id=issue.id,
                        rule_id=r1.id,
                        rule_title=r1.title,
                        rule_version=r1.current_version,
                        issue_category=issue.issue_category,
                        severity=issue.severity,
                        explanation=issue.explanation,
                        related_rule_id=r2.id,
                        related_rule_title=r2.title,
                        suggested_action=issue.suggested_action,
                        requires_human_review=True,
                        created_at=issue.created_at,
                    )
                )

    db.commit()

    summary: dict[str, int] = {}
    for iss in issues:
        summary[iss.issue_category] = summary.get(iss.issue_category, 0) + 1

    return GuidelineLintResponse(
        brand_id=brand_id,
        total_issues=len(issues),
        issues=issues,
        summary=summary,
    )
