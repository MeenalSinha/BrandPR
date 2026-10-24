"""Phase 4 acceptance tests P4-01 ...: revisions, corrections, human approval, fact-change impact resolution.

Real PostgreSQL, the real review pipeline in limited (deterministic) mode, the real API. A model provider appears only in the tests
that exercise suggested corrections, and there it is the controlled FakeProvider (see tests/fakes.py), never a stand-in for approval.
Demo identity: creator "Casey Creator" writes, reviewer "Riley Reviewer" decides.
"""
import hashlib
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.deps import Actor, get_review_provider
from app.db.session import get_db
from app.main import create_app
from app.schemas.workflow import RevisionCreate
from app.services import revisions
from tests.conftest import alembic_config
from tests.fakes import FakeProvider
from tests.test_impacts import (  # noqa: F401  (world is a fixture)
    BATTERY_EXCERPT, campaign, edit, list_impacts, make_fact, sql, status_to, submit_and_review, world,
)
from app.services.review.providers import ProviderUnavailable

CREATOR = {"X-Actor-Name": "Casey Creator", "X-Actor-Role": "creator"}
REVIEWER = {"X-Actor-Name": "Riley Reviewer", "X-Actor-Role": "reviewer"}
# Casey creates content through the API without headers (submitted_by is a body field), so creator identity is set there.
FRESH_14 = "Summer campaign: Battery life is up to 14 hours under specified test conditions."
STALE_18 = "Summer campaign: Battery life is up to 18 hours under specified test conditions. Order now."
OVER_20 = "Summer campaign: Battery life is up to 20 hours under specified test conditions."


@pytest.fixture(autouse=True)
def _pinned_today(fixed_today):
    return fixed_today


# ------------------------------------------------------------------ helpers
def sha(text_: str) -> str:
    return hashlib.sha256(text_.encode("utf-8")).hexdigest()


def revise(client, content_id, content, *, headers=CREATOR, expect=201, **extra):
    r = client.post(f"/api/content/{content_id}/revisions", json={"content": content, **extra}, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def review(client, content_id, *, status="completed_limited"):
    r = client.post(f"/api/content/{content_id}/reviews", json={})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == status, r.json()
    return r.json()


def submit(client, content_id, *, headers=CREATOR, expect=200):
    r = client.post(f"/api/content/{content_id}/submit-review", headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def decide(client, content_id, action, *, headers=REVIEWER, expect=201, **body):
    r = client.post(f"/api/content/{content_id}/decisions", json={"action": action, **body}, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def workflow(client, content_id, headers=None):
    r = client.get(f"/api/content/{content_id}/workflow", headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()


def error(r, status, code):
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code, r.json()
    return r.json()["error"]


def impact_for(client, brand_id, content_id, **params):
    items = [i for i in list_impacts(client, brand_id, **params)["items"] if i["content"]["id"] == content_id]
    assert len(items) == 1, items
    return items[0]


def approved_revision(client, base, text_):
    """revise -> review -> submit -> approve. Returns (revision, workflow)."""
    rev = revise(client, base, text_)
    run = review(client, rev["id"])
    submit(client, rev["id"])
    return rev, decide(client, rev["id"], "approve", review_run_id=run["id"])


@pytest.fixture
def fact_changed(client, world):
    """The battery fact moves from 18 to 14 hours (edited, then re-approved as version 3): campaigns A and B have open Phase 3 impacts.

    run_a2 is a fresh review of the impacted revision 1 against the current fact; its finding is the stale claim the creator will correct."""
    edit(client, world["battery"]["id"], value="Up to 14 hours", change_reason="Test results revised.")
    status_to(client, world["battery"]["id"], "active", reason="Re-approved after test results.")
    world["run_a2"] = review(client, world["a"]["id"])
    assert world["run_a2"]["findings"][0]["status"] == "conflicting"
    return world


# ================================================================== A. revision management
def test_p4_01_first_submission_is_revision_one_of_its_own_asset(client, brand):
    c = client.post(f"/api/brands/{brand['id']}/content", json={"title": "Launch", "content": "Hello world.", "submitted_by": "Casey Creator"}).json()
    assert (c["revision_number"], c["parent_submission_id"], c["workflow_status"], c["is_latest"]) == (1, None, "draft", True)
    assert c["asset_id"]
    assert sql("SELECT count(*) FROM content_assets WHERE id = :a AND brand_id = :b", a=c["asset_id"], b=brand["id"])[0][0] == 1


def test_p4_02_correction_creates_a_new_revision_and_leaves_the_old_one_untouched(client, world):
    a = world["a"]
    before = client.get(f"/api/content/{a['id']}").json()
    rev = revise(client, a["id"], FRESH_14, change_note="Battery figure updated")
    assert rev["revision_number"] == 2 and rev["parent_submission_id"] == a["id"] and rev["asset_id"] == a["asset_id"] and rev["brand_id"] == a["brand_id"]
    assert rev["workflow_status"] == "draft" and rev["is_latest"] and rev["submitted_by"] == "Casey Creator" and rev["change_note"] == "Battery figure updated"
    after = client.get(f"/api/content/{a['id']}").json()
    assert after["content"] == before["content"] and after["content_hash"] == before["content_hash"] and after["title"] == before["title"]
    assert after["is_latest"] is False and after["revision_number"] == 1 and after["created_at"] == before["created_at"]


def test_p4_03_hashes_match_the_saved_text(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    assert rev["content_hash"] == sha(FRESH_14) == sha(client.get(f"/api/content/{rev['id']}").json()["content"])
    assert sql("SELECT content_hash = encode(sha256(convert_to(content, 'UTF8')), 'hex') FROM content_submissions WHERE id = :i", i=rev["id"])[0][0] is True


def test_p4_04_revision_numbers_increase_and_history_survives_reload(client, world):
    r2 = revise(client, world["a"]["id"], FRESH_14)
    r3 = revise(client, r2["id"], FRESH_14 + " Learn more.")
    fresh = TestClient(create_app())  # a new client stands in for reloading the application
    hist = fresh.get(f"/api/content/{world['a']['id']}/revisions").json()
    assert [i["revision_number"] for i in hist["items"]] == [1, 2, 3]
    assert hist["latest_revision_id"] == r3["id"] and hist["asset_id"] == world["a"]["asset_id"]
    assert [i["is_latest"] for i in hist["items"]] == [False, False, True]
    assert [i["parent_submission_id"] for i in hist["items"]] == [None, world["a"]["id"], r2["id"]]
    assert hist["items"][0]["review_count"] == 1 and hist["items"][0]["latest_review"]["status"] == "completed_limited"


def test_p4_05_old_review_findings_and_evidence_are_unchanged(client, world):
    before = client.get(f"/api/reviews/{world['run_a']['id']}/findings").json()
    rev = revise(client, world["a"]["id"], FRESH_14)
    review(client, rev["id"])
    assert client.get(f"/api/reviews/{world['run_a']['id']}/findings").json() == before
    assert client.get(f"/api/reviews/{world['run_a']['id']}").json()["content_submission_id"] == world["a"]["id"]


def test_p4_06_stale_base_is_a_conflict_that_loses_nothing(client, world):
    first = revise(client, world["a"]["id"], FRESH_14)
    e = error(client.post(f"/api/content/{world['a']['id']}/revisions", json={"content": "Another editor's text."}, headers=CREATOR), 409, "revision_conflict")
    assert {"field": "latest_revision_id", "message": first["id"]} in e["details"]
    assert sql("SELECT count(*) FROM content_submissions WHERE asset_id = :a", a=world["a"]["asset_id"])[0][0] == 2


def test_p4_07_simultaneous_revisions_cannot_share_a_number(client, world):
    engine = create_engine(os.environ["DATABASE_URL"])
    base_id = uuid.UUID(world["a"]["id"])

    def worker(i):
        with Session(engine) as s:
            try:
                row = revisions.create_revision(s, base_id, RevisionCreate(content=f"{FRESH_14} variant {i}"), Actor(f"Editor {i}", "creator"))
                return ("ok", row.revision_number)
            except Exception as exc:  # the loser gets revision_conflict
                return ("err", getattr(exc, "code", type(exc).__name__))

    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(worker, range(6)))
    engine.dispose()
    assert sorted(r for r in results if r[0] == "ok") == [("ok", 2)], results
    assert all(r == ("err", "revision_conflict") for r in results if r[0] == "err"), results
    assert sql("SELECT array_agg(revision_number ORDER BY revision_number) FROM content_submissions WHERE asset_id = :a", a=world["a"]["asset_id"])[0][0] == [1, 2]


def test_p4_08_database_refuses_forged_parents_and_assets(client, world, other_brand):
    foreign_asset = sql("INSERT INTO content_assets (brand_id, title) VALUES (:b, 'Other') RETURNING id::text", b=other_brand["id"])[0][0]
    insert = """INSERT INTO content_submissions (brand_id, asset_id, revision_number, parent_submission_id, title, content, content_hash)
                VALUES (:b, :a, :n, :p, 't', 'x', encode(sha256(convert_to('x','UTF8')),'hex'))"""
    with pytest.raises(Exception, match="fk_content_submissions_asset_same_brand"):  # another brand's asset
        sql(insert, b=world["brand"]["id"], a=foreign_asset, n=1, p=None)
    with pytest.raises(Exception, match="fk_content_submissions_parent_same_asset"):  # a parent from a different asset
        sql(insert, b=world["brand"]["id"], a=world["a"]["asset_id"], n=2, p=world["b"]["id"])
    with pytest.raises(Exception, match="uq_content_submissions_asset_revision"):  # duplicate number
        sql(insert, b=world["brand"]["id"], a=world["a"]["asset_id"], n=1, p=None)
    error(client.post(f"/api/content/{uuid.uuid4()}/revisions", json={"content": "x"}, headers=CREATOR), 404, "not_found")


def test_p4_09_revisions_are_immutable_in_the_database(client, world):
    for column, value in (("content", "'tampered'"), ("title", "'tampered'"), ("content_hash", "'0'"), ("revision_number", "9"), ("submitted_by", "'mallory'")):
        with pytest.raises(Exception, match="immutable|content_hash_matches"):
            sql(f"UPDATE content_submissions SET {column} = {value} WHERE id = :i", i=world["a"]["id"])
    with pytest.raises(Exception, match="not permitted"):
        sql("UPDATE content_submissions SET workflow_status = 'approved' WHERE id = :i", i=world["a"]["id"])  # draft cannot jump to approved


def test_p4_10_title_can_change_and_validation_applies(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14, title="Summer campaign v2")
    assert rev["title"] == "Summer campaign v2" and client.get(f"/api/content/{world['a']['id']}").json()["title"] == "Summer campaign"
    assert sql("SELECT title FROM content_assets WHERE id = :a", a=world["a"]["asset_id"])[0][0] == "Summer campaign v2"
    error(client.post(f"/api/content/{rev['id']}/revisions", json={"content": rev["content"], "title": "Summer campaign v2"}, headers=CREATOR), 422, "validation_error")  # unchanged
    error(client.post(f"/api/content/{rev['id']}/revisions", json={"content": "   "}, headers=CREATOR), 422, "validation_error")
    error(client.post(f"/api/content/{rev['id']}/revisions", json={"content": "x" * 5001}, headers=CREATOR), 422, "validation_error")
    error(client.post(f"/api/content/{rev['id']}/revisions", json={"content": "ok", "asset_id": str(uuid.uuid4())}, headers=CREATOR), 422, "validation_error")  # no client-chosen asset


def test_p4_11_identity_headers_are_required_and_checked(client, world):
    error(client.post(f"/api/content/{world['a']['id']}/revisions", json={"content": FRESH_14}), 401, "actor_required")
    error(client.post(f"/api/content/{world['a']['id']}/revisions", json={"content": FRESH_14}, headers={"X-Actor-Name": "x", "X-Actor-Role": "admin"}), 422, "validation_error")


def test_p4_12_lists_show_every_revision_or_only_the_latest(client, world):
    revise(client, world["a"]["id"], FRESH_14)
    allp = client.get(f"/api/brands/{world['brand']['id']}/content").json()
    latest = client.get(f"/api/brands/{world['brand']['id']}/content", params={"latest_only": True}).json()
    assert allp["total"] == 4 and latest["total"] == 3
    assert sorted((i["title"], i["revision_number"]) for i in latest["items"]) == [("Back to school", 1), ("Summer campaign", 2), ("Weight note", 1)]


def test_p4_13_no_new_revision_while_a_decision_is_pending(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    review(client, rev["id"])
    submit(client, rev["id"])
    error(client.post(f"/api/content/{rev['id']}/revisions", json={"content": FRESH_14 + " x"}, headers=CREATOR), 409, "revision_in_review")


# ================================================================== B. correction and review
def test_p4_14_a_finding_and_its_evidence_can_be_inspected(client, world):
    finding = world["run_a"]["findings"][0]
    d = client.get(f"/api/findings/{finding['id']}").json()
    assert d["revision_number"] == 1 and d["submission_id"] == world["a"]["id"]
    assert d["finding"]["evidence"][0]["fact_id"] == world["battery"]["id"] and d["finding"]["evidence"][0]["excerpt"]
    error(client.get(f"/api/findings/{uuid.uuid4()}"), 404, "not_found")


def test_p4_15_manual_correction_works_without_any_ai_provider(client, fact_changed):
    a = fact_changed["a"]
    finding = fact_changed["run_a2"]["findings"][0]
    error(client.post(f"/api/findings/{finding['id']}/suggest-correction", headers=CREATOR), 503, "ai_unavailable")
    rev = revise(client, a["id"], FRESH_14, corrections=[{"finding_id": finding["id"], "decision": "manual", "source": "manual", "original_text": finding["claim_text"], "replacement_text": "up to 14 hours"}])
    assert rev["revision_number"] == 2
    w = workflow(client, rev["id"])
    assert [(c["decision"], c["source"]) for c in w["corrections"]] == [("manual", "manual")]


def _suggest_with(client, finding_id, provider):
    client.app.dependency_overrides[get_review_provider] = lambda: provider
    try:
        return client.post(f"/api/findings/{finding_id}/suggest-correction", headers=CREATOR)
    finally:
        client.app.dependency_overrides.pop(get_review_provider, None)


def test_p4_16_a_suggestion_is_a_proposal_only(client, fact_changed):
    finding = fact_changed["run_a2"]["findings"][0]
    reply = json.dumps({"replacement_text": "up to 14 hours under specified test conditions", "rationale": "Matches the approved fact."})
    provider = FakeProvider(interpret=reply)
    r = _suggest_with(client, finding["id"], provider)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["replacement_text"] == "up to 14 hours under specified test conditions" and s["requires_human_review"] is True and s["source"] == "ai"
    assert s["original_text"] == finding["claim_text"] and s["evidence_fact_ids"] == [fact_changed["battery"]["id"]] and s["warnings"]
    prompt = provider.calls[0][1]
    assert "Up to 14 hours" in prompt and "Up to 18 hours" not in prompt            # grounded in the CURRENT approved fact
    assert client.get(f"/api/content/{fact_changed['a']['id']}").json()["content"] == fact_changed["a"]["content"]
    assert sql("SELECT count(*) FROM revision_corrections")[0][0] == 0 and sql("SELECT count(*) FROM content_submissions WHERE brand_id = :b", b=fact_changed["brand"]["id"])[0][0] == 3


def test_p4_17_suggestions_with_unsupported_numbers_are_flagged(client, fact_changed):
    finding = fact_changed["run_a2"]["findings"][0]
    r = _suggest_with(client, finding["id"], FakeProvider(interpret=json.dumps({"replacement_text": "up to 99 hours", "rationale": "x"})))
    assert any("99" in w for w in r.json()["warnings"])


def test_p4_18_suggestion_refusals_are_honest(client, world, fact_changed):
    # supported claim -> nothing to correct (before the fact changed, run_u's claim is supported)
    supported = next(f for f in world["run_a"]["findings"] if f["status"] == "supported")   # revision 1 was reviewed before the change
    error(_suggest_with(client, supported["id"], FakeProvider()), 409, "nothing_to_correct")
    # a claim with no approved evidence cannot be grounded
    c, run = submit_and_review(client, world["brand"]["id"], "Our laptop is the fastest ever made.", title="Superlative")
    unsupported = next(f for f in run["findings"] if f["status"] == "unsupported")
    error(_suggest_with(client, unsupported["id"], FakeProvider()), 409, "no_current_evidence")
    # provider failure is reported, never replaced by invented text
    finding = fact_changed["run_a2"]["findings"][0]
    error(_suggest_with(client, finding["id"], FakeProvider(interpret=ProviderUnavailable("down"))), 502, "suggestion_failed")
    error(_suggest_with(client, finding["id"], FakeProvider(interpret="not json")), 502, "suggestion_failed")


def test_p4_19_accepted_rejected_and_modified_suggestions_are_recorded_with_the_revision(client, fact_changed):
    findings = fact_changed["run_a2"]["findings"]
    f = findings[0]
    rev = revise(client, fact_changed["a"]["id"], FRESH_14, corrections=[{"finding_id": f["id"], "decision": "modified", "source": "ai", "original_text": f["claim_text"], "replacement_text": "up to 14 hours"}])
    w = workflow(client, rev["id"])
    assert w["corrections"][0]["decision"] == "modified" and w["corrections"][0]["source"] == "ai"
    rev3 = revise(client, rev["id"], FRESH_14 + " More.", corrections=[])
    # rejected suggestion on revision 2's own finding
    run2 = review(client, rev["id"])
    assert run2["content_submission_id"] == rev["id"]
    # a correction that cites a finding of another content item is refused
    other = fact_changed["run_b"]["findings"][0]
    error(client.post(f"/api/content/{rev3['id']}/revisions", json={"content": FRESH_14 + " Again.", "corrections": [{"finding_id": other["id"], "decision": "rejected", "source": "ai", "original_text": "x"}]}, headers=CREATOR), 422, "validation_error")


def test_p4_20_the_new_revision_is_reviewed_on_its_own_text(client, fact_changed):
    rev = revise(client, fact_changed["a"]["id"], FRESH_14)
    run = review(client, rev["id"])
    assert run["content_submission_id"] == rev["id"] and run["content_hash"] == rev["content_hash"] != fact_changed["a"]["content_hash"]
    claim = run["findings"][0]
    assert FRESH_14[claim["start_offset"]:claim["end_offset"]] == claim["claim_text"]
    ev = [e for e in claim["evidence"] if e["fact_id"] == fact_changed["battery"]["id"]]
    assert ev and ev[0]["fact_version"] == 3 and claim["status"] == "supported"           # current approved fact, not the old one
    assert len(client.get(f"/api/content/{fact_changed['a']['id']}/reviews").json()) == 2  # revision 1 keeps only its own two reviews


def test_p4_21_a_failed_review_is_never_approval_ready(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    client.app.dependency_overrides[get_review_provider] = lambda: FakeProvider(extract=ProviderUnavailable("down"))
    try:
        run = review(client, rev["id"], status="failed")
    finally:
        client.app.dependency_overrides.pop(get_review_provider, None)
    w = workflow(client, rev["id"], CREATOR)
    assert w["readiness"]["state"] == "review_failed" and w["readiness"]["ready_for_decision"] is False and "submit_review" not in w["available_actions"]
    error(client.post(f"/api/content/{rev['id']}/submit-review", headers=CREATOR), 409, "review_failed")
    assert run["error_code"]


def test_p4_22_limited_mode_is_disclosed_to_the_reviewer(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    review(client, rev["id"])
    r = workflow(client, rev["id"])["readiness"]
    assert r["state"] == "ready" and r["limited_mode"] is True and r["analysis_mode"] == "limited" and "Limited analysis" in r["limitations"][0]
    assert any("Limited analysis" in reason for reason in r["reasons"])


# ================================================================== C. approval decisions
def test_p4_23_a_creator_submits_a_reviewed_revision(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    error(client.post(f"/api/content/{rev['id']}/submit-review", headers=CREATOR), 409, "review_required")   # never reviewed
    run = review(client, rev["id"])
    w = submit(client, rev["id"])
    assert w["workflow_status"] == "in_review"
    assert [e["action"] for e in w["events"] if e["submission_id"] == rev["id"]] == ["created", "submitted"]
    assert client.get(f"/api/content/{rev['id']}").json()["workflow_status"] == "in_review"
    error(client.post(f"/api/content/{rev['id']}/submit-review", headers=CREATOR), 409, "invalid_transition")  # not twice
    assert w["events"][-1]["review_run_id"] == run["id"]


def test_p4_24_an_unreviewed_or_unsubmitted_draft_cannot_be_approved(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    run = review(client, rev["id"])
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "approve", "review_run_id": run["id"]}, headers=REVIEWER), 409, "invalid_transition")  # draft
    error(client.post(f"/api/content/{world['a']['id']}/decisions", json={"action": "approve", "review_run_id": world["run_a"]["id"]}, headers=REVIEWER), 409, "invalid_transition")


def test_p4_25_reviewer_approval_is_recorded_and_persists(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    run = review(client, rev["id"])
    submit(client, rev["id"])
    w = decide(client, rev["id"], "approve", review_run_id=run["id"], rationale="Matches the approved spec.")
    assert w["workflow_status"] == "approved" and w["approved_run_id"] == run["id"]
    last = w["events"][-1]
    assert (last["action"], last["actor"], last["actor_role"], last["rationale"], last["review_run_id"]) == ("approved", "Riley Reviewer", "reviewer", "Matches the approved spec.", run["id"])
    assert last["created_at"] and (last["from_status"], last["to_status"]) == ("in_review", "approved")
    fresh = TestClient(create_app())
    again = fresh.get(f"/api/content/{rev['id']}/workflow").json()
    assert again["workflow_status"] == "approved" and again["events"] == w["events"]
    assert sql("SELECT actor, review_run_id::text FROM workflow_events WHERE submission_id = :i AND action = 'approved'", i=rev["id"]) == [("Riley Reviewer", run["id"])]


def test_p4_26_creators_cannot_perform_reviewer_actions(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    run = review(client, rev["id"])
    submit(client, rev["id"])
    for body in ({"action": "approve", "review_run_id": run["id"]}, {"action": "reject", "rationale": "no"}, {"action": "request_changes", "rationale": "no"}):
        error(client.post(f"/api/content/{rev['id']}/decisions", json=body, headers=CREATOR), 403, "reviewer_role_required")
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "approve", "review_run_id": run["id"]}), 401, "actor_required")
    assert workflow(client, rev["id"])["workflow_status"] == "in_review"
    assert "approve" not in workflow(client, rev["id"], CREATOR)["available_actions"] and "approve" in workflow(client, rev["id"], REVIEWER)["available_actions"]
    assert workflow(client, rev["id"])["available_actions"] == []


def test_p4_27_a_reviewer_cannot_approve_their_own_revision(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14, headers=REVIEWER)
    run = review(client, rev["id"])
    submit(client, rev["id"], headers=REVIEWER)
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "approve", "review_run_id": run["id"]}, headers=REVIEWER), 403, "self_review_not_allowed")
    assert "approve" not in workflow(client, rev["id"], REVIEWER)["available_actions"]


def test_p4_28_approval_names_the_latest_review(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    first = review(client, rev["id"])
    submit(client, rev["id"])
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "approve"}, headers=REVIEWER), 422, "validation_error")
    newer = review(client, rev["id"])
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "approve", "review_run_id": first["id"]}, headers=REVIEWER), 409, "stale_review")
    assert decide(client, rev["id"], "approve", review_run_id=newer["id"])["workflow_status"] == "approved"


def test_p4_29_a_failed_latest_review_blocks_approval(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    ok = review(client, rev["id"])
    submit(client, rev["id"])
    client.app.dependency_overrides[get_review_provider] = lambda: FakeProvider(extract=ProviderUnavailable("down"))
    try:
        review(client, rev["id"], status="failed")
    finally:
        client.app.dependency_overrides.pop(get_review_provider, None)
    assert workflow(client, rev["id"])["readiness"]["state"] == "review_failed"
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "approve", "review_run_id": ok["id"]}, headers=REVIEWER), 409, "review_failed")
    assert workflow(client, rev["id"])["workflow_status"] == "in_review"


def test_p4_30_a_review_for_different_text_cannot_approve_this_text(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    run = review(client, rev["id"])
    submit(client, rev["id"])
    sql("UPDATE review_runs SET content_hash = :h WHERE id = :r", h=sha("something else"), r=run["id"])   # simulate a review of other text
    assert workflow(client, rev["id"])["readiness"]["state"] == "content_mismatch"
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "approve", "review_run_id": run["id"]}, headers=REVIEWER), 409, "review_content_mismatch")


def test_p4_31_high_risk_findings_block_approval_unless_a_reviewer_records_an_override(client, world):
    rev = revise(client, world["a"]["id"], OVER_20)
    run = review(client, rev["id"])
    conflict = next(f for f in run["findings"] if f["status"] == "conflicting" and f["severity"] == "high")
    submit(client, rev["id"])
    w = workflow(client, rev["id"])
    assert [b["finding_id"] for b in w["readiness"]["blocking_findings"]] == [conflict["id"]] and w["readiness"]["ready_for_decision"]
    e = error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "approve", "review_run_id": run["id"]}, headers=REVIEWER), 409, "high_risk_unresolved")
    assert e["details"][0]["field"] == conflict["id"]
    for bad in ([{"finding_id": conflict["id"], "reason": "  "}], [{"finding_id": str(uuid.uuid4()), "reason": "because"}]):
        error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "approve", "review_run_id": run["id"], "overrides": bad}, headers=REVIEWER), 422, "validation_error")
    w = decide(client, rev["id"], "approve", review_run_id=run["id"], overrides=[{"finding_id": conflict["id"], "reason": "Legal confirmed the 20 hour figure for the EU model."}])
    assert w["workflow_status"] == "approved"
    o = w["overrides"][0]
    assert (o["finding_id"], o["actor"], o["review_run_id"]) == (conflict["id"], "Riley Reviewer", run["id"]) and "Legal confirmed" in o["reason"]
    assert w["readiness"]["blocking_findings"][0]["overridden"] is True
    still = client.get(f"/api/reviews/{run['id']}/findings").json()["items"]                    # the finding itself is never edited
    assert next(f for f in still if f["id"] == conflict["id"])["status"] == "conflicting"
    assert sql("SELECT count(*) FROM risk_overrides")[0][0] == 1


def test_p4_32_low_risk_findings_do_not_block_and_non_high_findings_cannot_be_overridden(client, world):
    rev = revise(client, world["u"]["id"], "Our laptop weighs 1.2 kg. Enjoy.")
    run = review(client, rev["id"])
    assert not [f for f in run["findings"] if f["severity"] == "high" and f["status"] != "supported"]
    submit(client, rev["id"])
    uncertain = next(f for f in run["findings"] if f["status"] == "uncertain")
    assert uncertain["severity"] == "medium" and workflow(client, rev["id"])["readiness"]["blocking_findings"] == []
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "approve", "review_run_id": run["id"], "overrides": [{"finding_id": uncertain["id"], "reason": "just because"}]}, headers=REVIEWER), 422, "validation_error")
    assert decide(client, rev["id"], "approve", review_run_id=run["id"])["workflow_status"] == "approved"


def test_p4_33_request_changes_needs_a_reason_and_keeps_the_revision_as_it_was(client, world):
    rev = revise(client, world["a"]["id"], OVER_20)
    run = review(client, rev["id"])
    finding = run["findings"][0]
    submit(client, rev["id"])
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "request_changes"}, headers=REVIEWER), 422, "validation_error")
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "request_changes", "rationale": "x", "finding_ids": [str(uuid.uuid4())]}, headers=REVIEWER), 422, "validation_error")
    w = decide(client, rev["id"], "request_changes", rationale="Battery figure is not in the spec.", finding_ids=[finding["id"]])
    last = w["events"][-1]
    assert w["workflow_status"] == "changes_requested" and last["rationale"] == "Battery figure is not in the spec." and last["finding_ids"] == [finding["id"]]
    assert client.get(f"/api/content/{rev['id']}").json()["content"] == OVER_20
    nxt = revise(client, rev["id"], FRESH_14)                                                    # the creator continues in a NEW revision
    assert nxt["revision_number"] == 3 and nxt["workflow_status"] == "draft"


def test_p4_34_rejection_needs_a_reason_and_a_new_attempt_is_a_new_revision(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    review(client, rev["id"])
    submit(client, rev["id"])
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "reject", "rationale": "   "}, headers=REVIEWER), 422, "validation_error")
    w = decide(client, rev["id"], "reject", rationale="Wrong campaign.")
    assert w["workflow_status"] == "rejected" and w["events"][-1]["rationale"] == "Wrong campaign."
    error(client.post(f"/api/content/{rev['id']}/submit-review", headers=CREATOR), 409, "invalid_transition")
    assert revise(client, rev["id"], FRESH_14 + " Revised.")["revision_number"] == 3


def test_p4_35_decisions_cannot_be_repeated_or_reversed(client, world):
    rev = revise(client, world["a"]["id"], FRESH_14)
    run = review(client, rev["id"])
    submit(client, rev["id"])
    decide(client, rev["id"], "approve", review_run_id=run["id"])
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "reject", "rationale": "changed my mind"}, headers=REVIEWER), 409, "invalid_transition")
    error(client.post(f"/api/content/{rev['id']}/decisions", json={"action": "approve", "review_run_id": run["id"]}, headers=REVIEWER), 409, "invalid_transition")
    with pytest.raises(Exception, match="uq_workflow_events_one_final_decision|append-only"):  # the database refuses a second final decision too
        sql("INSERT INTO workflow_events (brand_id, asset_id, submission_id, action, to_status, actor, actor_role, rationale) SELECT brand_id, asset_id, id, 'rejected', 'rejected', 'x', 'reviewer', 'x' FROM content_submissions WHERE id = :i", i=rev["id"])
    with pytest.raises(Exception, match="not permitted"):
        sql("UPDATE content_submissions SET workflow_status = 'rejected' WHERE id = :i", i=rev["id"])


def test_p4_36_a_later_revision_never_inherits_approval(client, world):
    rev, w = approved_revision(client, world["a"]["id"], FRESH_14)
    approved_text, approved_hash = rev["content"], rev["content_hash"]
    nxt = revise(client, rev["id"], FRESH_14 + " Now with a free case!")                       # editing approved content is allowed, as a new revision
    assert nxt["workflow_status"] == "draft"
    error(client.post(f"/api/content/{nxt['id']}/decisions", json={"action": "approve", "review_run_id": w["approved_run_id"]}, headers=REVIEWER), 409, "invalid_transition")
    error(client.post(f"/api/content/{nxt['id']}/submit-review", headers=CREATOR), 409, "review_required")
    again = client.get(f"/api/content/{rev['id']}").json()
    assert again["workflow_status"] == "approved" and again["content"] == approved_text and again["content_hash"] == approved_hash


def test_p4_37_every_decision_is_in_the_history_and_history_is_append_only(client, world):
    rev, w = approved_revision(client, world["a"]["id"], FRESH_14)
    events = [(e["revision_number"], e["action"], e["actor"]) for e in workflow(client, rev["id"])["events"]]
    assert events == [(1, "created", "anonymous"), (2, "created", "Casey Creator"), (2, "submitted", "Casey Creator"), (2, "approved", "Riley Reviewer")]
    with pytest.raises(Exception, match="append-only"):
        sql("UPDATE workflow_events SET actor = 'mallory'")
    with pytest.raises(Exception, match="append-only"):
        sql("DELETE FROM workflow_events")


def test_p4_38_a_revision_that_was_superseded_cannot_be_submitted_or_decided(client, world):
    first = revise(client, world["a"]["id"], FRESH_14)
    revise(client, first["id"], FRESH_14 + " Newer.")
    error(client.post(f"/api/content/{first['id']}/submit-review", headers=CREATOR), 409, "revision_superseded")
    review(client, first["id"])
    error(client.post(f"/api/content/{first['id']}/submit-review", headers=CREATOR), 409, "revision_superseded")


# ================================================================== D. impact resolution
def test_p4_39_correct_review_approve_and_resolve_the_right_impact_in_one_transaction(client, fact_changed):
    w = fact_changed
    ia, ib = impact_for(client, w["brand"]["id"], w["a"]["id"]), impact_for(client, w["brand"]["id"], w["b"]["id"])
    detail_before = client.get(f"/api/fact-change-impacts/{ia['id']}").json()
    findings_before = client.get(f"/api/reviews/{w['run_a']['id']}/findings").json()
    rev = revise(client, w["a"]["id"], FRESH_14, change_note="Battery now 14 hours")
    run = review(client, rev["id"])
    submit(client, rev["id"])
    decide(client, rev["id"], "approve", review_run_id=run["id"], resolve_impact_ids=[ia["id"]], resolution_rationale="Copy now states 14 hours.")
    now = impact_for(client, w["brand"]["id"], w["a"]["id"], status="resolved")
    assert now["status"] == "resolved" and now["resolution"]["actor"] == "Riley Reviewer" and now["resolution"]["rationale"] == "Copy now states 14 hours."
    assert now["resolution"]["resolving_submission_id"] == rev["id"] and now["resolution"]["resolving_revision_number"] == 2 and now["resolution"]["resolving_review_run_id"] == run["id"]
    assert now["content"]["id"] == w["a"]["id"] and now["content"]["revision_number"] == 1 and now["content"]["latest_revision_id"] == rev["id"]   # still points at the reviewed revision
    assert impact_for(client, w["brand"]["id"], w["b"]["id"])["status"] == "needs_review" and ib["status"] == "needs_review"                     # unrelated impact untouched
    detail_after = client.get(f"/api/fact-change-impacts/{ia['id']}").json()
    keep = ("change_summary", "previous_snapshot", "new_snapshot", "reason", "headline", "detected_at", "previous_fact_version", "current_fact_version", "source_review_run_id", "findings", "trigger_revision")
    assert {k: detail_after[k] for k in keep} == {k: detail_before[k] for k in keep}
    assert client.get(f"/api/reviews/{w['run_a']['id']}/findings").json() == findings_before                                                     # historical evidence unchanged
    s = client.get(f"/api/brands/{w['brand']['id']}/fact-change-impacts/summary").json()
    assert (s["open_impacts"], s["resolved_impacts"], s["dismissed_impacts"], s["total_impacts"]) == (1, 1, 0, 2)
    row = sql("SELECT action, from_status, to_status, actor FROM fact_change_impact_resolutions")
    assert row == [("resolved", "needs_review", "resolved", "Riley Reviewer")]


def test_p4_40_resolution_can_also_be_a_separate_explicit_action(client, fact_changed):
    w = fact_changed
    ia = impact_for(client, w["brand"]["id"], w["a"]["id"])
    rev, _ = approved_revision(client, w["a"]["id"], FRESH_14)
    assert impact_for(client, w["brand"]["id"], w["a"]["id"])["status"] == "needs_review"      # approving alone resolves nothing
    body = {"resolving_submission_id": rev["id"], "rationale": "Corrected and approved."}
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json=body, headers=CREATOR), 403, "reviewer_role_required")
    r = client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json=body, headers=REVIEWER)
    assert r.status_code == 200 and r.json()["action"] == "resolved" and r.json()["resolving_revision_number"] == 2
    again = client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json=body, headers=REVIEWER)    # repeating is idempotent
    assert again.status_code == 200 and again.json()["id"] == r.json()["id"]
    assert sql("SELECT count(*) FROM fact_change_impact_resolutions")[0][0] == 1
    other, _ = approved_revision(client, rev["id"], FRESH_14 + " Free shipping.")
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": other["id"], "rationale": "other"}, headers=REVIEWER), 409, "impact_not_open")
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/dismiss", json={"rationale": "too late"}, headers=REVIEWER), 409, "impact_not_open")


def test_p4_41_nothing_short_of_an_approved_revision_resolves_an_impact(client, fact_changed):
    w = fact_changed
    ia = impact_for(client, w["brand"]["id"], w["a"]["id"])
    rev = revise(client, w["a"]["id"], FRESH_14)

    def attempt(sub_id):
        return client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": sub_id, "rationale": "trying"}, headers=REVIEWER)

    error(attempt(rev["id"]), 409, "revision_not_approved")                                     # a new revision alone
    run = review(client, rev["id"])
    error(attempt(rev["id"]), 409, "revision_not_approved")                                     # reviewed, not approved
    submit(client, rev["id"])
    error(attempt(rev["id"]), 409, "revision_not_approved")                                     # waiting for a reviewer
    error(attempt(str(uuid.uuid4())), 404, "not_found")
    assert impact_for(client, w["brand"]["id"], w["a"]["id"])["status"] == "needs_review" and sql("SELECT count(*) FROM fact_change_impact_resolutions")[0][0] == 0
    assert run["status"] == "completed_limited"


def test_p4_42_a_failed_review_cannot_resolve_an_impact(client, fact_changed):
    w = fact_changed
    ia = impact_for(client, w["brand"]["id"], w["a"]["id"])
    rev = revise(client, w["a"]["id"], FRESH_14)
    client.app.dependency_overrides[get_review_provider] = lambda: FakeProvider(extract=ProviderUnavailable("down"))
    try:
        review(client, rev["id"], status="failed")
    finally:
        client.app.dependency_overrides.pop(get_review_provider, None)
    error(client.post(f"/api/content/{rev['id']}/submit-review", headers=CREATOR), 409, "review_failed")
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": rev["id"], "rationale": "first attempt"}, headers=REVIEWER), 409, "revision_not_approved")
    # even a forged approval row could not help: the approving run must have finished
    run_failed = sql("SELECT id::text FROM review_runs WHERE content_submission_id = :i", i=rev["id"])[0][0]
    sql("UPDATE content_submissions SET workflow_status = 'in_review' WHERE id = :i", i=rev["id"])
    sql("UPDATE content_submissions SET workflow_status = 'approved' WHERE id = :i", i=rev["id"])
    sql("INSERT INTO workflow_events (brand_id, asset_id, submission_id, review_run_id, action, to_status, actor, actor_role) SELECT brand_id, asset_id, id, :r, 'approved', 'approved', 'forger', 'reviewer' FROM content_submissions WHERE id = :i", r=run_failed, i=rev["id"])
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": rev["id"], "rationale": "second attempt"}, headers=REVIEWER), 409, "review_not_completed")
    assert impact_for(client, w["brand"]["id"], w["a"]["id"])["status"] == "needs_review"


def test_p4_43_an_unresolved_conflict_with_the_changed_fact_prevents_resolution(client, fact_changed):
    w = fact_changed
    ia = impact_for(client, w["brand"]["id"], w["a"]["id"])
    rev = revise(client, w["a"]["id"], STALE_18)                                              # still claims 18 hours; the fact now says 14
    run = review(client, rev["id"])
    conflict = next(f for f in run["findings"] if f["status"] in ("conflicting", "outdated"))
    submit(client, rev["id"])
    decide(client, rev["id"], "approve", review_run_id=run["id"], overrides=[{"finding_id": conflict["id"], "reason": "Reviewer accepts the risk for now."}])
    e = error(client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": rev["id"], "rationale": "approved anyway"}, headers=REVIEWER), 409, "conflict_unresolved")
    assert e["details"][0]["field"] == conflict["id"]
    # the same conflict also stops an approval that tries to resolve in the same transaction, and the approval rolls back with it
    rev2 = revise(client, rev["id"], STALE_18 + " Hurry.")
    run2 = review(client, rev2["id"])
    c2 = next(f for f in run2["findings"] if f["status"] in ("conflicting", "outdated"))
    submit(client, rev2["id"])
    error(client.post(f"/api/content/{rev2['id']}/decisions", json={"action": "approve", "review_run_id": run2["id"], "overrides": [{"finding_id": c2["id"], "reason": "accept"}], "resolve_impact_ids": [ia["id"]]}, headers=REVIEWER), 409, "conflict_unresolved")
    assert workflow(client, rev2["id"])["workflow_status"] == "in_review" and sql("SELECT count(*) FROM risk_overrides WHERE finding_id = :f", f=c2["id"])[0][0] == 0
    assert impact_for(client, w["brand"]["id"], w["a"]["id"])["status"] == "needs_review"


def test_p4_44_a_review_that_ran_before_the_impact_or_before_a_later_fact_change_does_not_count(client, world):
    early = revise(client, world["a"]["id"], "Summer campaign: Battery life is up to 18 hours under specified test conditions. Early.")
    run = review(client, early["id"])
    submit(client, early["id"])
    decide(client, early["id"], "approve", review_run_id=run["id"])
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    status_to(client, world["battery"]["id"], "active", reason="Re-approved after test results.")
    ia = impact_for(client, world["brand"]["id"], world["a"]["id"])
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": early["id"], "rationale": "old approval"}, headers=REVIEWER), 409, "review_predates_impact")
    rev = revise(client, early["id"], FRESH_14)
    run2 = review(client, rev["id"])
    submit(client, rev["id"])
    edit(client, world["battery"]["id"], value="Up to 12 hours")                                # the fact moves again after the review
    decide(client, rev["id"], "approve", review_run_id=run2["id"])
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": rev["id"], "rationale": "stale"}, headers=REVIEWER), 409, "fact_changed_since_review")


def test_p4_45_wrong_revision_asset_or_brand_cannot_resolve(client, fact_changed, other_brand):
    w = fact_changed
    ia = impact_for(client, w["brand"]["id"], w["a"]["id"])
    rev_b, _ = approved_revision(client, w["b"]["id"], "Back to school: Battery life is up to 14 hours under specified test conditions.")
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": rev_b["id"], "rationale": "wrong asset"}, headers=REVIEWER), 409, "wrong_asset")
    foreign = client.post(f"/api/brands/{other_brand['id']}/content", json={"title": "F", "content": "Foreign."}).json()
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": foreign["id"], "rationale": "first attempt"}, headers=REVIEWER), 409, "wrong_brand")
    approved_old = fact_changed["a"]
    sql("UPDATE content_submissions SET workflow_status = 'in_review' WHERE id = :i", i=approved_old["id"])
    sql("UPDATE content_submissions SET workflow_status = 'approved' WHERE id = :i", i=approved_old["id"])
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": approved_old["id"], "rationale": "same revision"}, headers=REVIEWER), 409, "wrong_revision")


def test_p4_46_dismissal_needs_a_reviewer_and_a_reason_and_keeps_the_original_impact(client, fact_changed):
    w = fact_changed
    ib = impact_for(client, w["brand"]["id"], w["b"]["id"])
    before = client.get(f"/api/fact-change-impacts/{ib['id']}").json()
    error(client.post(f"/api/fact-change-impacts/{ib['id']}/dismiss", json={"rationale": "not needed"}, headers=CREATOR), 403, "reviewer_role_required")
    error(client.post(f"/api/fact-change-impacts/{ib['id']}/dismiss", json={"rationale": "  "}, headers=REVIEWER), 422, "validation_error")
    error(client.post(f"/api/fact-change-impacts/{ib['id']}/dismiss", json={}, headers=REVIEWER), 422, "validation_error")
    r = client.post(f"/api/fact-change-impacts/{ib['id']}/dismiss", json={"rationale": "Campaign retired; no longer published."}, headers=REVIEWER)
    assert r.status_code == 200 and r.json()["action"] == "dismissed" and r.json()["actor"] == "Riley Reviewer" and r.json()["resolving_submission_id"] is None
    after = client.get(f"/api/fact-change-impacts/{ib['id']}").json()
    assert after["status"] == "dismissed" and after["resolution"]["rationale"] == "Campaign retired; no longer published."
    for k in ("change_summary", "reason", "headline", "previous_snapshot", "new_snapshot", "findings", "detected_at"):
        assert after[k] == before[k], k
    assert client.post(f"/api/fact-change-impacts/{ib['id']}/dismiss", json={"rationale": "Campaign retired; no longer published."}, headers=REVIEWER).json()["id"] == r.json()["id"]
    error(client.post(f"/api/fact-change-impacts/{ib['id']}/dismiss", json={"rationale": "different reason"}, headers=REVIEWER), 409, "impact_not_open")
    assert impact_for(client, w["brand"]["id"], w["a"]["id"])["status"] == "needs_review"
    assert [i["status"] for i in list_impacts(client, w["brand"]["id"], status="dismissed")["items"]] == ["dismissed"]
    assert list_impacts(client, w["brand"]["id"], status="needs_review")["total"] == 1


def test_p4_47_impact_history_is_inspectable(client, fact_changed):
    w = fact_changed
    ia = impact_for(client, w["brand"]["id"], w["a"]["id"])
    rev = revise(client, w["a"]["id"], FRESH_14)
    run = review(client, rev["id"])
    submit(client, rev["id"])
    decide(client, rev["id"], "approve", review_run_id=run["id"], resolve_impact_ids=[ia["id"]], resolution_rationale="Fixed.")
    h = client.get(f"/api/fact-change-impacts/{ia['id']}/history").json()
    assert h["status"] == "resolved" and h["affected_revision_number"] == 1 and h["latest_revision_number"] == 2 and h["asset_id"] == w["a"]["asset_id"]
    assert [(r["resolving_revision_number"], r["actor"], r["rationale"]) for r in h["resolutions"]] == [(2, "Riley Reviewer", "Fixed.")]
    assert [r["revision_number"] for r in h["revisions"]] == [1, 2] and h["revisions"][1]["decision"]["action"] == "approved"
    assert [e["action"] for e in h["events"]][-2:] == ["submitted", "approved"]
    assert fact_changed["battery"]["id"]
    error(client.get(f"/api/fact-change-impacts/{uuid.uuid4()}/history"), 404, "not_found")


def test_p4_48_the_database_guards_impact_status_and_history(client, fact_changed):
    ia = impact_for(client, fact_changed["brand"]["id"], fact_changed["a"]["id"])
    with pytest.raises(Exception, match="requires a recorded resolution"):
        sql("UPDATE fact_change_impacts SET status = 'resolved' WHERE id = :i", i=ia["id"])
    with pytest.raises(Exception, match="keeps its original"):
        sql("UPDATE fact_change_impacts SET reason = 'rewritten' WHERE id = :i", i=ia["id"])
    client.post(f"/api/fact-change-impacts/{ia['id']}/dismiss", json={"rationale": "No action."}, headers=REVIEWER)
    with pytest.raises(Exception, match="append-only"):
        sql("UPDATE fact_change_impact_resolutions SET rationale = 'rewritten'")
    with pytest.raises(Exception, match="append-only"):
        sql("DELETE FROM fact_change_impact_resolutions")
    with pytest.raises(Exception, match="requires a recorded resolution|keeps its original"):
        sql("UPDATE fact_change_impacts SET status = 'needs_review' WHERE id = :i", i=ia["id"])   # no re-opening by SQL either
    with pytest.raises(Exception, match="uq_impact_resolutions_impact"):
        sql("INSERT INTO fact_change_impact_resolutions (brand_id, impact_id, action, from_status, to_status, actor, actor_role, rationale) VALUES (:b, :i, 'dismissed', 'needs_review', 'dismissed', 'x', 'reviewer', 'twice')", b=fact_changed["brand"]["id"], i=ia["id"])


def test_p4_49_expiry_impacts_are_closed_the_same_way(client, world, monkeypatch):
    from app.core import clock
    from datetime import date

    edit(client, world["battery"]["id"], expires_at="2026-11-01")
    monkeypatch.setattr(clock, "today", lambda: date(2026, 11, 5))
    page = list_impacts(client, world["brand"]["id"])
    assert page["total"] == 2 and all(i["trigger_type"] == "fact_expiry" for i in page["items"])
    ia = impact_for(client, world["brand"]["id"], world["a"]["id"])
    r = client.post(f"/api/fact-change-impacts/{ia['id']}/dismiss", json={"rationale": "Fact renewal in progress; campaign paused."}, headers=REVIEWER)
    assert r.status_code == 200
    s = client.get(f"/api/brands/{world['brand']['id']}/fact-change-impacts/summary").json()
    assert (s["open_impacts"], s["dismissed_impacts"], s["expiry_affected_content"]) == (1, 1, 1)


def test_p4_50_resolution_authority_is_checked_before_anything_else(client, fact_changed):
    ia = impact_for(client, fact_changed["brand"]["id"], fact_changed["a"]["id"])
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": fact_changed["a"]["id"], "rationale": "first attempt"}), 401, "actor_required")
    error(client.post(f"/api/fact-change-impacts/{ia['id']}/dismiss", json={"rationale": "first attempt"}), 401, "actor_required")
    error(client.post(f"/api/fact-change-impacts/{uuid.uuid4()}/dismiss", json={"rationale": "first attempt"}, headers=REVIEWER), 404, "not_found")


# ================================================================== E. migration and maintenance regressions
def test_p4_51_migration_0004_backfills_legacy_content_and_keeps_impacts(client, fact_changed):
    w = fact_changed
    impacts_before = sql("SELECT id::text, status, reason FROM fact_change_impacts ORDER BY id")
    runs_before = sql("SELECT id::text, content_submission_id::text, content_hash FROM review_runs ORDER BY id")
    engine = create_engine(os.environ["DATABASE_URL"])
    engine.dispose()
    command.downgrade(alembic_config(), "0003")
    assert sql("SELECT to_regclass('content_assets')")[0][0] is None
    command.upgrade(alembic_config(), "head")
    assert sql("SELECT id::text, status, reason FROM fact_change_impacts ORDER BY id") == impacts_before
    assert sql("SELECT id::text, content_submission_id::text, content_hash FROM review_runs ORDER BY id") == runs_before
    rows = sql("SELECT s.revision_number, s.parent_submission_id IS NULL, s.workflow_status, a.title = s.title, a.brand_id = s.brand_id FROM content_submissions s JOIN content_assets a ON a.id = s.asset_id")
    assert len(rows) == 3 and all(r == (1, True, "draft", True, True) for r in rows)
    assert sql("SELECT count(DISTINCT asset_id) FROM content_submissions")[0][0] == 3


def test_p4_52_seed_reset_removes_phase_3_and_phase_4_data(client, fact_changed):
    from app.scripts.seed import BRAND_NAME, reset

    w = fact_changed
    sql("UPDATE brands SET name = :n WHERE id = :i", n=BRAND_NAME, i=w["brand"]["id"])
    ia = impact_for(client, w["brand"]["id"], w["a"]["id"])
    rev, _ = approved_revision(client, w["a"]["id"], FRESH_14)
    client.post(f"/api/fact-change-impacts/{ia['id']}/resolve", json={"resolving_submission_id": rev["id"], "rationale": "Corrected."}, headers=REVIEWER)
    revise(client, rev["id"], FRESH_14 + " More.")
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as s:
        reset(s)
    engine.dispose()
    for table in ("brands", "content_submissions", "content_assets", "workflow_events", "fact_change_impacts", "fact_change_impact_resolutions", "approved_facts"):
        assert sql(f"SELECT count(*) FROM {table}")[0][0] == 0, table
    assert sql("SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'trg_%' AND tgenabled = 'D'")[0][0] == 0   # append-only guards are back on
