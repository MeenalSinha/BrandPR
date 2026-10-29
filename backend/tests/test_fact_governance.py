import pytest
from app.core.auth import create_access_token
from tests.conftest import fact_payload


def test_fact_governance_lifecycle_proposal_comparison_approval(client, brand):
    # 1. Create and approve initial fact (Version 1)
    creator_token = create_access_token({"sub": "c1", "name": "Morgan Creator", "role": "creator", "brand_ids": ["*"]})
    reviewer_token = create_access_token({"sub": "r1", "name": "Alex Reviewer", "role": "reviewer", "brand_ids": ["*"]})

    body = fact_payload(name="Display Resolution", value="4K UHD (3840x2160)", status="active", source_note="Hardware spec sheet v1")
    r = client.post(
        f"/api/brands/{brand['id']}/facts",
        json=body,
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert r.status_code == 201
    fact = r.json()
    fact_id = fact["id"]
    assert fact["version"] == 1
    assert fact["status"] == "active"

    # 2. Material edit by Creator -> Status automatically returns to "proposed", version 2
    r_edit = client.patch(
        f"/api/facts/{fact_id}",
        json={
            "value": "5K Retina (5120x2880)",
            "change_reason": "Upgraded display panel in Q4",
            "qualifications": "Available on Pro models only",
        },
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert r_edit.status_code == 200
    proposed_fact = r_edit.json()
    assert proposed_fact["version"] == 2
    assert proposed_fact["status"] == "proposed"
    assert proposed_fact["value"] == "5K Retina (5120x2880)"

    # 3. Side-by-side comparison endpoint (/facts/{id}/comparison)
    r_comp = client.get(
        f"/api/facts/{fact_id}/comparison",
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert r_comp.status_code == 200
    comp = r_comp.json()
    assert comp["is_material_change"] is True
    assert comp["current_snapshot"]["value"] == "5K Retina (5120x2880)"
    assert comp["previous_approved_snapshot"]["value"] == "4K UHD (3840x2160)"
    assert "value" in comp["diff"]
    assert "qualifications" in comp["diff"]

    # 4. Reviewer Approval endpoint (/facts/{id}/approve)
    r_appr = client.post(
        f"/api/facts/{fact_id}/approve",
        json={"approval_notes": "Verified display panel upgrade with Engineering director."},
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert r_appr.status_code == 200
    approved_fact = r_appr.json()
    assert approved_fact["status"] == "active"
    assert approved_fact["version"] == 3

    # Check approval decision history (/facts/{id}/decisions)
    r_dec = client.get(
        f"/api/facts/{fact_id}/decisions",
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert r_dec.status_code == 200
    decisions = r_dec.json()
    assert len(decisions) >= 1
    latest_decision = decisions[-1]
    assert latest_decision["decision"] == "approved"
    assert "Engineering director" in latest_decision["notes"]


def test_fact_governance_rejection_and_concurrent_conflict(client, brand):
    creator_token = create_access_token({"sub": "c1", "name": "Morgan Creator", "role": "creator", "brand_ids": ["*"]})
    reviewer_token = create_access_token({"sub": "r1", "name": "Alex Reviewer", "role": "reviewer", "brand_ids": ["*"]})

    # Create active fact
    r = client.post(
        f"/api/brands/{brand['id']}/facts",
        json=fact_payload(name="Processor", value="M3 Max", status="active", source_note="SoC Spec v1"),
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    fact_id = r.json()["id"]

    # Propose change
    client.patch(
        f"/api/facts/{fact_id}",
        json={"value": "M4 Ultra", "change_reason": "Speculative roadmap leak"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )

    # Reviewer rejects proposal (/facts/{id}/reject)
    r_rej = client.post(
        f"/api/facts/{fact_id}/reject",
        json={"rejection_reason": "M4 Ultra is unannounced and strictly NDA until next quarter."},
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert r_rej.status_code == 200
    rejected = r_rej.json()
    assert rejected["status"] == "rejected"

    # Verify audit decision was recorded
    decisions = client.get(
        f"/api/facts/{fact_id}/decisions",
        headers={"Authorization": f"Bearer {reviewer_token}"},
    ).json()
    assert decisions[-1]["decision"] == "rejected"
    assert "NDA" in decisions[-1]["notes"]

    # Test concurrent conflict detection with expected_version
    r_conflict = client.patch(
        f"/api/facts/{fact_id}",
        json={
            "value": "M3 Pro",
            "expected_version": 1,  # Fact is already at version 3
            "change_reason": "Concurrent conflict attempt",
        },
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert r_conflict.status_code == 409
    assert r_conflict.json()["error"]["code"] == "version_conflict"
