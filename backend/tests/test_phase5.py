import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text

from app.models.guideline import GuidelineLintResult, GuidelineRule, GuidelineRuleVersion, PolicySimulation, PolicySimulationResult
from app.models.review import ContentSubmission, FindingEvidence, ReviewFinding, ReviewRun
from app.models.source_document import DocumentSection, SourceDocument
from tests.conftest import upload


# Helper headers
CREATOR_HEADERS = {"X-Actor-Name": "Alice Creator", "X-Actor-Role": "creator"}
REVIEWER_HEADERS = {"X-Actor-Name": "Bob Reviewer", "X-Actor-Role": "reviewer"}


# =====================================================================
# P5-02 to P5-04: Rule Creation, Approval, and Versioning
# =====================================================================
def test_p5_02_rule_creation_with_source_provenance(client, brand, pdf_bytes):
    up = upload(client, brand["id"], "specs.pdf", pdf_bytes, "application/pdf")
    assert up.status_code == 201
    doc_id = up.json()["id"]

    res = client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={
            "title": "Battery life guideline",
            "rule_text": "Battery life must be stated as up to 18 hours.",
            "category": "specification",
            "severity": "high",
            "scope": "all",
            "source_document_id": doc_id,
            "source_page": 2,
            "source_excerpt": "Battery life: up to 18 hours under specified test conditions.",
        },
        headers=CREATOR_HEADERS,
    )
    assert res.status_code == 201, res.text
    rule = res.json()
    assert rule["id"]
    assert rule["title"] == "Battery life guideline"
    assert rule["status"] == "proposed"  # Created by creator -> starts as proposed
    assert rule["current_version"] == 1
    assert rule["source_document_id"] == doc_id
    assert rule["source_page"] == 2
    assert "Battery life" in rule["source_excerpt"]
    assert len(rule["versions"]) == 1
    assert rule["versions"][0]["version_number"] == 1


def test_p5_03_rule_approval_and_access_control(client, brand):
    # Creator creates proposed rule
    res = client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={
            "title": "Nova terminology",
            "rule_text": "Always write Nova with a capital N.",
            "category": "terminology",
            "status": "proposed",
        },
        headers=CREATOR_HEADERS,
    )
    assert res.status_code == 201
    rule_id = res.json()["id"]
    assert res.json()["status"] == "proposed"

    # Creator attempts to activate rule -> 403 Forbidden
    res_creator_activate = client.patch(
        f"/api/guidelines/{rule_id}",
        json={"status": "active"},
        headers=CREATOR_HEADERS,
    )
    assert res_creator_activate.status_code == 403

    # Reviewer activates rule -> Success
    res_reviewer_activate = client.patch(
        f"/api/guidelines/{rule_id}",
        json={"status": "active"},
        headers=REVIEWER_HEADERS,
    )
    assert res_reviewer_activate.status_code == 200
    assert res_reviewer_activate.json()["status"] == "active"


def test_p5_04_rule_versioning_preserves_history(client, brand):
    # 1. Create and activate rule
    res = client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={
            "title": "Speed claim rule",
            "rule_text": "Comparative claims must not be used.",
            "category": "comparative",
            "status": "proposed",
        },
        headers=REVIEWER_HEADERS,
    )
    rule_id = res.json()["id"]
    client.patch(f"/api/guidelines/{rule_id}", json={"status": "active"}, headers=REVIEWER_HEADERS)

    # 2. Update rule text with a new version
    update_res = client.patch(
        f"/api/guidelines/{rule_id}",
        json={
            "rule_text": "Comparative claims may be used when supported by approved comparative evidence.",
            "change_reason": "Allow comparative claims with explicit evidence",
        },
        headers=REVIEWER_HEADERS,
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["current_version"] == 2
    assert "Comparative claims may be used" in updated["rule_text"]

    # 3. Check version history retains version 1 and version 2
    versions_res = client.get(f"/api/guidelines/{rule_id}/versions")
    assert versions_res.status_code == 200
    vers = versions_res.json()
    assert len(vers) == 2
    assert vers[0]["version_number"] == 2
    assert vers[1]["version_number"] == 1
    assert "must not be used" in vers[1]["rule_text"]
    assert "may be used when supported" in vers[0]["rule_text"]


def test_p5_cross_brand_source_document_rejected(client, brand, other_brand, pdf_bytes):
    # Upload doc to other_brand
    up = upload(client, other_brand["id"], "other.pdf", pdf_bytes, "application/pdf")
    other_doc_id = up.json()["id"]

    # Attempt to link brand's rule to other_brand's document -> 422
    res = client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={
            "title": "Cross brand attempt",
            "rule_text": "This should fail cross-brand validation.",
            "source_document_id": other_doc_id,
        },
        headers=CREATOR_HEADERS,
    )
    assert res.status_code == 422


# =====================================================================
# P5-05 to P5-07: Document Extraction & Guideline Lint
# =====================================================================
def test_p5_document_rule_extraction_creates_proposed_rules(client, brand):
    # Upload guide text
    guide_text = (
        "Nova Style Guide. The product name must always be written as Nova. "
        "Comparative claims are prohibited without legal approval. "
        "Never use outdated battery metrics."
    ).encode("utf-8")
    up = upload(client, brand["id"], "guide.txt", guide_text, "text/plain")
    assert up.status_code == 201
    doc_id = up.json()["id"]

    ext_res = client.post(
        f"/api/brands/{brand['id']}/guidelines/extract",
        json={"document_id": doc_id},
        headers=CREATOR_HEADERS,
    )
    assert ext_res.status_code == 201
    extracted = ext_res.json()["extracted_rules"]
    assert len(extracted) >= 2
    for r in extracted:
        assert r["status"] == "proposed"  # All extracted rules MUST be proposed
        assert r["source_document_id"] == doc_id
        assert r["source_page"] in (None, 1)


def test_p5_05_guideline_lint_identifies_deterministic_issues(client, brand):
    # Rule 1: Vague word without examples
    client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={
            "title": "Vague quality rule",
            "rule_text": "Marketing copy must always reflect best-in-class quality.",
            "scope": "all",
            "category": "tone",
        },
        headers=CREATOR_HEADERS,
    )
    # Rule 2: Unclear scope
    client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={
            "title": "Missing scope rule",
            "rule_text": "Do not mention competitor pricing.",
            "scope": "invalid_scope",
            "category": "claim",
        },
        headers=CREATOR_HEADERS,
    )
    # Rule 3: Missing conditions
    client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={
            "title": "Conditional rule missing conditions",
            "rule_text": "Comparative statements may be used when approved by marketing.",
            "scope": "body",
            "category": "comparative",
        },
        headers=CREATOR_HEADERS,
    )

    lint_res = client.post(f"/api/brands/{brand['id']}/guideline-lint")
    assert lint_res.status_code == 200
    data = lint_res.json()
    assert data["total_issues"] >= 3

    categories = [issue["issue_category"] for issue in data["issues"]]
    assert "vague_instruction" in categories
    assert "unclear_scope" in categories
    assert "missing_conditions" in categories

    for issue in data["issues"]:
        assert issue["requires_human_review"] is True
        assert issue["suggested_action"]


def test_p5_06_conflict_detection_between_rules(client, brand):
    # Rule A: requires 'SuperNova'
    client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={
            "title": "Use SuperNova",
            "rule_text": "Content must contain term SuperNova.",
            "category": "terminology",
            "conditions": {"required_terms": ["SuperNova"]},
        },
        headers=CREATOR_HEADERS,
    )
    # Rule B: prohibits 'SuperNova'
    client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={
            "title": "Forbid SuperNova",
            "rule_text": "Content must not use term SuperNova.",
            "category": "terminology",
            "conditions": {"prohibited_terms": ["SuperNova"]},
        },
        headers=CREATOR_HEADERS,
    )

    lint_res = client.post(f"/api/brands/{brand['id']}/guideline-lint")
    assert lint_res.status_code == 200
    issues = lint_res.json()["issues"]

    conflicts = [i for i in issues if i["issue_category"] == "potential_conflict"]
    assert len(conflicts) >= 1
    c = conflicts[0]
    assert c["related_rule_id"] is not None
    assert "SuperNova" in c["explanation"]
    assert c["severity"] == "high"
    assert c["requires_human_review"] is True


# =====================================================================
# P5-08 to P5-12: Policy Sandbox
# =====================================================================
def test_p5_08_to_09_policy_simulation_persists_results_and_leaves_history_intact(client, brand):
    # 1. Create a content submission and run a review
    sub_res = client.post(
        f"/api/brands/{brand['id']}/content",
        json={"title": "Ad Draft", "content": "Our Nova device is faster than all competitors and lasts 18 hours."},
        headers=CREATOR_HEADERS,
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["id"]

    rev_res = client.post(f"/api/content/{sub_id}/reviews")
    assert rev_res.status_code == 201
    run_id = rev_res.json()["id"]

    # Verify review findings exist
    orig_findings = client.get(f"/api/reviews/{run_id}/findings").json()["items"]
    orig_findings_count = len(orig_findings)

    # 2. Create active rule: comparative prohibited
    rule_res = client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={
            "title": "Strict comparative prohibition",
            "rule_text": "Comparative claims are strictly prohibited.",
            "category": "comparative",
            "conditions": {"comparative_prohibited": True},
            "status": "proposed",
        },
        headers=REVIEWER_HEADERS,
    )
    rule_id = rule_res.json()["id"]
    client.patch(f"/api/guidelines/{rule_id}", json={"status": "active"}, headers=REVIEWER_HEADERS)

    # 3. Run Policy Simulation with proposed rule relaxing comparative claims
    sim_res = client.post(
        f"/api/brands/{brand['id']}/policy-simulations",
        json={
            "rule_id": rule_id,
            "proposed_rule": {
                "rule_text": "Comparative claims may be used when permitted.",
                "category": "comparative",
                "conditions": {"comparative_permitted": True},
            },
            "content_submission_ids": [sub_id],
        },
        headers=REVIEWER_HEADERS,
    )
    assert sim_res.status_code == 201
    sim = sim_res.json()
    assert sim["id"]
    assert sim["base_rule_version"] == 1
    assert sim["summary"]["total_evaluated"] == 1
    assert sim["summary"]["changed"] == 1  # baseline was flagged, simulated is pass!

    result = sim["results"][0]
    assert result["content_submission_id"] == sub_id
    assert result["baseline_outcome"] == "flagged"
    assert result["simulated_outcome"] == "pass"

    # 4. Critical verification of historical integrity (P5-09):
    # Review run, original findings, and rule status MUST be completely untouched!
    rechecked_findings = client.get(f"/api/reviews/{run_id}/findings").json()["items"]
    assert len(rechecked_findings) == orig_findings_count
    rechecked_review = client.get(f"/api/reviews/{run_id}").json()
    assert rechecked_review["status"] in ("completed", "completed_limited")

    # The active rule MUST NOT have changed to the proposed version (P5-12)
    rechecked_rule = client.get(f"/api/guidelines/{rule_id}").json()
    assert rechecked_rule["status"] == "active"
    assert rechecked_rule["current_version"] == 1
    assert "strictly prohibited" in rechecked_rule["rule_text"]


def test_p5_10_simulation_scope_rejects_cross_brand(client, brand, other_brand):
    # Content submission in other_brand
    sub_other = client.post(
        f"/api/brands/{other_brand['id']}/content",
        json={"title": "Other Ad", "content": "Text for other brand."},
        headers=CREATOR_HEADERS,
    ).json()

    # Rule in brand
    rule = client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={"title": "Brand rule", "rule_text": "Brand rule text.", "category": "general"},
        headers=REVIEWER_HEADERS,
    ).json()

    # Attempt to simulate with cross-brand content -> 422
    sim_res = client.post(
        f"/api/brands/{brand['id']}/policy-simulations",
        json={
            "rule_id": rule["id"],
            "proposed_rule": {"rule_text": "Updated text."},
            "content_submission_ids": [sub_other["id"]],
        },
        headers=REVIEWER_HEADERS,
    )
    assert sim_res.status_code == 422


def test_p5_11_unsupported_rule_types_marked_not_evaluable(client, brand):
    sub = client.post(
        f"/api/brands/{brand['id']}/content",
        json={"title": "Draft", "content": "Simple marketing message."},
        headers=CREATOR_HEADERS,
    ).json()

    # Natural language rule without conditions or evaluable keywords
    rule = client.post(
        f"/api/brands/{brand['id']}/guidelines",
        json={
            "title": "Abstract philosophical guideline",
            "rule_text": "Brand storytelling should resonate with authentic human warmth.",
            "category": "general",
            "conditions": None,
        },
        headers=REVIEWER_HEADERS,
    ).json()

    sim_res = client.post(
        f"/api/brands/{brand['id']}/policy-simulations",
        json={
            "rule_id": rule["id"],
            "proposed_rule": {
                "rule_text": "Brand storytelling should evoke genuine empathy and resonance.",
                "conditions": None,
            },
            "content_submission_ids": [sub["id"]],
        },
        headers=REVIEWER_HEADERS,
    )
    assert sim_res.status_code == 201, sim_res.text
    sim = sim_res.json()
    assert sim["summary"]["not_evaluable"] == 1
    assert sim["results"][0]["evaluation_status"] == "not_evaluable"
    assert sim["results"][0]["baseline_outcome"] == "not_evaluable"


# =====================================================================
# P5-13 to P5-18: Governance Intelligence
# =====================================================================
def test_p5_13_to_18_governance_intelligence_metrics_and_recommendations(client, brand, pdf_bytes):
    # 1. Setup brand knowledge & review content with a deliberate conflict
    up = upload(client, brand["id"], "specs.pdf", pdf_bytes, "application/pdf")
    doc_id = up.json()["id"]

    fact = client.post(
        f"/api/brands/{brand['id']}/facts",
        json={
            "name": "Battery life",
            "value": "18 hours",
            "category": "product_spec",
            "source_document_id": doc_id,
            "source_page": 2,
            "source_excerpt": "Battery life: up to 18 hours under specified test conditions.",
            "status": "active",
        },
    ).json()

    # Content with 24 hours (conflicts with 18 hours)
    sub = client.post(
        f"/api/brands/{brand['id']}/content",
        json={"title": "Battery Ad", "content": "The Nova battery runs for 24 hours continuously."},
        headers=CREATOR_HEADERS,
    ).json()

    rev = client.post(f"/api/content/{sub['id']}/reviews").json()
    assert rev["status"] in ("completed", "completed_limited")

    # 2. Fetch Governance Insights
    insights_res = client.get(f"/api/brands/{brand['id']}/insights?period=all")
    assert insights_res.status_code == 200
    insights = insights_res.json()

    assert insights["brand_id"] == brand["id"]
    assert insights["overview"]["completed_reviews"] >= 1
    assert insights["overview"]["total_findings"] >= 1
    assert "conflicting" in insights["finding_patterns"]["by_status"]

    # 3. Test empty state for a new clean brand (P5-17)
    clean_brand = client.post("/api/brands", json={"name": f"Clean Brand {uuid.uuid4()}"}).json()
    clean_insights = client.get(f"/api/brands/{clean_brand['id']}/insights").json()
    assert clean_insights["overview"]["completed_reviews"] == 0
    assert clean_insights["overview"]["total_findings"] == 0
    assert clean_insights["overview"]["open_impacts"] == 0
    assert clean_insights["governance_recommendations"] == []

    # 4. Period filtering (P5-15)
    insights_7d = client.get(f"/api/brands/{brand['id']}/insights?period=7d")
    assert insights_7d.status_code == 200
    assert insights_7d.json()["period"] == "7d"
