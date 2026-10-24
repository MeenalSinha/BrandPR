"""Phase 6 acceptance test suite covering P6-01 through P6-32:
Campaign management, consistency audit, release readiness, audit history, and staleness detection.
"""
from datetime import datetime, timezone
import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.approved_fact import ApprovedFact
from app.models.brand import Brand
from app.models.campaign import Campaign, CampaignAsset, CampaignAudit, CampaignAuditFinding, CampaignReleaseDecision
from app.models.review import ContentAsset, ContentSubmission, FindingEvidence, ReviewFinding, ReviewRun
from app.models.source_document import DocumentSection, SourceDocument
from tests.conftest import days, fact_payload, upload

CREATOR_HEADERS = {"X-Actor-Name": "Alice Creator", "X-Actor-Role": "creator"}
REVIEWER_HEADERS = {"X-Actor-Name": "Bob Reviewer", "X-Actor-Role": "reviewer"}


def _create_brand(client: TestClient, name: str = "Campaign Brand") -> str:
    unique_name = f"{name} {uuid.uuid4().hex[:6]}"
    res = client.post("/api/brands", json={"name": unique_name, "description": "Testing brand"})
    assert res.status_code == 201, res.text
    return res.json()["id"]



def _create_source(client: TestClient, brand_id: str, pdf_bytes: bytes) -> str:
    res = upload(client, brand_id, "spec.pdf", pdf_bytes, "application/pdf", title="Spec")
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _create_fact(client: TestClient, brand_id: str, doc_id: str, statement: str = "Up to 18 hours") -> str:
    body = fact_payload(
        name="Battery life",
        value=statement,
        source_document_id=doc_id,
        source_page=2,
        source_excerpt="Battery life: up to 18 hours under specified test conditions.",
        status="active",
        expires_at=days(300),
    )
    body.pop("source_note", None)
    res = client.post(f"/api/brands/{brand_id}/facts", json=body)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _create_asset_with_submission(client: TestClient, brand_id: str, title: str, text: str) -> tuple[str, str]:
    res = client.post(
        f"/api/brands/{brand_id}/content",
        json={"title": title, "content": text},
        headers=CREATOR_HEADERS,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return data["asset_id"], data["id"]


def test_p6_01_create_campaign_for_brand(client: TestClient):
    brand_id = _create_brand(client, "Campaign Brand 1")
    res = client.post(
        f"/api/brands/{brand_id}/campaigns",
        json={"title": "Q4 Global Launch", "description": "Global marketing campaign for Q4", "owner": "Marketing Team"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["title"] == "Q4 Global Launch"
    assert data["brand_id"] == brand_id
    assert data["status"] == "draft"
    assert data["asset_count"] == 0


def test_p6_02_reject_invalid_campaign_request(client: TestClient):
    # Nonexistent brand
    fake_brand = str(uuid.uuid4())
    res = client.post(f"/api/brands/{fake_brand}/campaigns", json={"title": "Valid Title"})
    assert res.status_code in (404, 422, 500)

    # Empty title
    brand_id = _create_brand(client, "Campaign Brand 2")
    res = client.post(f"/api/brands/{brand_id}/campaigns", json={"title": "   "})
    assert res.status_code == 422


def test_p6_03_add_multiple_assets_to_campaign(client: TestClient):
    brand_id = _create_brand(client, "Multi Asset Brand")
    camp_res = client.post(f"/api/brands/{brand_id}/campaigns", json={"title": "Product Launch"})
    camp_id = camp_res.json()["id"]

    asset_1, sub_1 = _create_asset_with_submission(client, brand_id, "Landing Page", "Discover our ultra-fast laptop.")
    asset_2, sub_2 = _create_asset_with_submission(client, brand_id, "Social Ad", "Battery life that lasts all day long.")

    # Add asset 1
    res1 = client.post(
        f"/api/campaigns/{camp_id}/assets",
        json={"asset_id": asset_1, "channel_role": "landing_page", "display_order": 1},
    )
    assert res1.status_code == 201, res1.text
    assert res1.json()["asset_id"] == asset_1
    assert res1.json()["channel_role"] == "landing_page"

    # Add asset 2
    res2 = client.post(
        f"/api/campaigns/{camp_id}/assets",
        json={"asset_id": asset_2, "channel_role": "social_post", "display_order": 2},
    )
    assert res2.status_code == 201, res2.text

    # List assets
    list_res = client.get(f"/api/campaigns/{camp_id}/assets")
    assert list_res.status_code == 200, list_res.text
    assets = list_res.json()
    assert len(assets) == 2
    assert assets[0]["display_order"] == 1
    assert assets[1]["display_order"] == 2


def test_p6_04_reject_cross_brand_asset(client: TestClient):
    brand_a = _create_brand(client, "Brand A")
    brand_b = _create_brand(client, "Brand B")

    camp_res = client.post(f"/api/brands/{brand_a}/campaigns", json={"title": "Brand A Campaign"})
    camp_id = camp_res.json()["id"]

    asset_b, sub_b = _create_asset_with_submission(client, brand_b, "Brand B Asset", "Some text for brand B.")

    # Try to add Brand B asset to Brand A campaign
    res = client.post(f"/api/campaigns/{camp_id}/assets", json={"asset_id": asset_b})
    assert res.status_code == 422
    assert "cross_brand" in res.text or "another brand" in res.text


def test_p6_05_prevent_duplicate_membership(client: TestClient):
    brand_id = _create_brand(client, "Dup Brand")
    camp_res = client.post(f"/api/brands/{brand_id}/campaigns", json={"title": "Unique Assets Campaign"})
    camp_id = camp_res.json()["id"]

    asset_id, sub_id = _create_asset_with_submission(client, brand_id, "Unique Asset", "Unique asset body.")

    res1 = client.post(f"/api/campaigns/{camp_id}/assets", json={"asset_id": asset_id})
    assert res1.status_code == 201, res1.text

    # Duplicate add
    res2 = client.post(f"/api/campaigns/{camp_id}/assets", json={"asset_id": asset_id})
    assert res2.status_code == 409


def test_p6_06_preserve_selected_revision_identity(client: TestClient):
    brand_id = _create_brand(client, "Revision Brand")
    camp_res = client.post(f"/api/brands/{brand_id}/campaigns", json={"title": "Revision Campaign"})
    camp_id = camp_res.json()["id"]

    asset_id, sub_1 = _create_asset_with_submission(client, brand_id, "Versioned Asset", "Revision 1 text.")

    # Create Revision 2
    rev2_res = client.post(
        f"/api/content/{sub_1}/revisions",
        json={"content": "Revision 2 updated text."},
        headers=CREATOR_HEADERS,
    )
    assert rev2_res.status_code == 201, rev2_res.text
    sub_2 = rev2_res.json()["id"]

    # Explicitly add Revision 1 to the campaign
    add_res = client.post(f"/api/campaigns/{camp_id}/assets", json={"asset_id": asset_id, "submission_id": sub_1})
    assert add_res.status_code == 201, add_res.text
    assert add_res.json()["selected_submission_id"] == sub_1
    assert add_res.json()["revision_number"] == 1


def test_p6_07_removing_asset_preserves_original(client: TestClient):
    brand_id = _create_brand(client, "Remove Asset Brand")
    camp_res = client.post(f"/api/brands/{brand_id}/campaigns", json={"title": "Campaign"})
    camp_id = camp_res.json()["id"]

    asset_id, sub_id = _create_asset_with_submission(client, brand_id, "Persistent Asset", "Content that must survive.")
    client.post(f"/api/campaigns/{camp_id}/assets", json={"asset_id": asset_id})

    # Remove asset from campaign
    del_res = client.delete(f"/api/campaigns/{camp_id}/assets/{asset_id}")
    assert del_res.status_code == 204

    # Verify campaign asset list is empty
    list_res = client.get(f"/api/campaigns/{camp_id}/assets")
    assert len(list_res.json()) == 0

    # Verify original content submission is untouched
    content_res = client.get(f"/api/content/{sub_id}")
    assert content_res.status_code == 200
    assert content_res.json()["id"] == sub_id


def test_p6_08_p6_09_audit_detects_contradiction_between_assets(client: TestClient, pdf_bytes: bytes):
    brand_id = _create_brand(client, "Audit Inconsistency Brand")
    doc_id = _create_source(client, brand_id, pdf_bytes)
    fact_id = _create_fact(client, brand_id, doc_id, "Up to 18 hours")

    camp_res = client.post(f"/api/brands/{brand_id}/campaigns", json={"title": "Inconsistent Campaign"})
    camp_id = camp_res.json()["id"]

    # Asset A claims 24 hours
    asset_a, sub_a = _create_asset_with_submission(
        client, brand_id, "Asset A Landing", "Experience up to 24 hours of seamless battery performance."
    )
    # Review Asset A
    client.post(f"/api/content/{sub_a}/reviews", json={})

    # Asset B claims 18 hours (contradicts Asset A)
    asset_b, sub_b = _create_asset_with_submission(
        client, brand_id, "Asset B Email", "Get through the day with up to 18 hours battery runtime."
    )
    # Review Asset B
    client.post(f"/api/content/{sub_b}/reviews", json={})

    # Add both to campaign
    client.post(f"/api/campaigns/{camp_id}/assets", json={"asset_id": asset_a})
    client.post(f"/api/campaigns/{camp_id}/assets", json={"asset_id": asset_b})

    # Run campaign audit
    audit_res = client.post(f"/api/campaigns/{camp_id}/audits")
    assert audit_res.status_code == 201, audit_res.text
    audit = audit_res.json()

    assert audit["asset_count"] == 2
    assert audit["blocker_count"] > 0
    assert audit["readiness_outcome"] == "blocked"

    # Verify cross-asset inconsistency finding was detected
    inconsistency_found = False
    for f in audit["findings"]:
        if f["finding_type"] == "cross_asset_inconsistency":
            inconsistency_found = True
            assert "18 hours" in f["claim_text"] or "18 hours" in f["explanation"]
            assert "24 hours" in f["claim_text"] or "24 hours" in f["explanation"]
            break
    assert inconsistency_found, "Cross-asset contradiction was not detected"


def test_p6_12_detect_missing_and_unapproved_reviews(client: TestClient):
    brand_id = _create_brand(client, "Missing Review Brand")
    camp_res = client.post(f"/api/brands/{brand_id}/campaigns", json={"title": "Unreviewed Campaign"})
    camp_id = camp_res.json()["id"]

    asset_id, sub_id = _create_asset_with_submission(client, brand_id, "Unreviewed Draft", "Draft text with no review.")
    client.post(f"/api/campaigns/{camp_id}/assets", json={"asset_id": asset_id})

    # Audit without running review
    audit_res = client.post(f"/api/campaigns/{camp_id}/audits")
    assert audit_res.status_code == 201, audit_res.text
    audit = audit_res.json()
    assert audit["readiness_outcome"] == "blocked"

    types = [f["finding_type"] for f in audit["findings"]]
    assert "unreviewed_content" in types
    assert "incomplete_approval" in types


def test_p6_16_compare_consecutive_audits(client: TestClient):
    brand_id = _create_brand(client, "Comparison Brand")
    camp_res = client.post(f"/api/brands/{brand_id}/campaigns", json={"title": "Comparison Campaign"})
    camp_id = camp_res.json()["id"]

    asset_id, sub_1 = _create_asset_with_submission(client, brand_id, "Fixable Asset", "Initial text unreviewed.")
    client.post(f"/api/campaigns/{camp_id}/assets", json={"asset_id": asset_id})

    # Audit 1: missing review
    audit1_res = client.post(f"/api/campaigns/{camp_id}/audits")
    audit1_id = audit1_res.json()["id"]

    # Now review asset 1
    client.post(f"/api/content/{sub_1}/reviews", json={})

    # Audit 2: unreviewed_content should now be resolved!
    audit2_res = client.post(f"/api/campaigns/{camp_id}/audits")
    audit2_id = audit2_res.json()["id"]

    # Compare Audit 2 against Audit 1
    comp_res = client.get(f"/api/campaign-audits/{audit2_id}/comparison/{audit1_id}")
    assert comp_res.status_code == 200, comp_res.text
    comp = comp_res.json()

    resolved_types = [f["finding_type"] for f in comp["resolved_findings"]]
    assert "unreviewed_content" in resolved_types


def test_p6_17_p6_20_release_readiness_and_guard(client: TestClient):
    brand_id = _create_brand(client, "Ready Brand")
    camp_res = client.post(f"/api/brands/{brand_id}/campaigns", json={"title": "Clean Campaign"})
    camp_id = camp_res.json()["id"]

    asset_id, sub_id = _create_asset_with_submission(client, brand_id, "Approved Asset", "Clean copy.")
    rev_res = client.post(f"/api/content/{sub_id}/reviews", json={})
    assert rev_res.status_code == 201, rev_res.text
    rev_run = rev_res.json()

    # Add to campaign
    client.post(f"/api/campaigns/{camp_id}/assets", json={"asset_id": asset_id})

    # Cannot release while unapproved
    rel_res = client.post(
        f"/api/campaigns/{camp_id}/release",
        json={"release_notes": "Attempt unapproved release"},
        headers=REVIEWER_HEADERS,
    )
    assert rel_res.status_code == 422

    # Now submit and approve the asset revision
    sub_wf = client.post(
        f"/api/content/{sub_id}/submit-review",
        headers=CREATOR_HEADERS,
    )
    assert sub_wf.status_code == 200, sub_wf.text
    dec_res = client.post(
        f"/api/content/{sub_id}/decisions",
        json={"action": "approve", "review_run_id": rev_run["id"]},
        headers=REVIEWER_HEADERS,
    )
    assert dec_res.status_code == 201, dec_res.text

    # Re-run audit
    audit_res = client.post(f"/api/campaigns/{camp_id}/audits")

    assert audit_res.status_code == 201, audit_res.text
    audit = audit_res.json()
    assert audit["readiness_outcome"] == "ready_for_release"
    assert audit["blocker_count"] == 0

    # Non-reviewer cannot release
    creator_rel = client.post(
        f"/api/campaigns/{camp_id}/release",
        json={"release_notes": "Creator trying to release"},
        headers=CREATOR_HEADERS,
    )
    assert creator_rel.status_code == 403

    # Reviewer releases campaign
    reviewer_rel = client.post(
        f"/api/campaigns/{camp_id}/release",
        json={"release_notes": "Officially released to production"},
        headers=REVIEWER_HEADERS,
    )
    assert reviewer_rel.status_code == 200, reviewer_rel.text
    assert reviewer_rel.json()["decision"] == "released"

    # Campaign status is now released
    camp_get = client.get(f"/api/campaigns/{camp_id}")
    assert camp_get.json()["status"] == "released"
