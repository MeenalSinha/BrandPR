"""Phase 3 acceptance tests P3-01 to P3-44: Claim Ledger fact-change propagation.

Real PostgreSQL, the real review pipeline in limited (deterministic) mode, and the real fact API. No model provider is
involved: propagation is deterministic. Time is controlled by patching app.core.clock.today.
"""
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.api.deps import get_review_provider  # noqa: F401  (documented dependency; reviews here run without a provider)
from app.core import clock
from app.db.session import get_db
from app.models import ApprovedFact, FactRevision
from app.services import facts as facts_svc
from app.services import impacts
from tests.conftest import days, fact_payload, upload, make_pdf  # noqa: F401

BATTERY_EXCERPT = "Battery life: up to 18 hours under specified test conditions."
CAMPAIGN = "{name}: Battery life is up to 18 hours under specified test conditions."
TODAY = date(2026, 10, 22)


@pytest.fixture(autouse=True)
def _pinned_today(fixed_today):
    return fixed_today


def set_today(monkeypatch, day: date) -> None:
    monkeypatch.setattr(clock, "today", lambda: day)


def sql(query, **params):
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.begin() as conn:
            result = conn.execute(text(query), params)
            return result.fetchall() if result.returns_rows else []
    finally:
        engine.dispose()


# ------------------------------------------------------------------ builders (all through the real API)
def make_fact(client, brand_id, *, name="Battery life", doc=None, expires=300, status="active", **over):
    body = fact_payload(name=name, status=status, **over)
    if expires is not None:
        body["expires_at"] = days(expires)
    if doc is not None:
        body.update(source_document_id=doc["id"], source_page=2, source_excerpt=BATTERY_EXCERPT)
        body.pop("source_note", None)
    r = client.post(f"/api/brands/{brand_id}/facts", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def submit_and_review(client, brand_id, body, title="Campaign"):
    c = client.post(f"/api/brands/{brand_id}/content", json={"title": title, "content": body})
    assert c.status_code == 201, c.text
    r = client.post(f"/api/content/{c.json()['id']}/reviews", json={})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "completed_limited", r.json()
    return c.json(), r.json()


def campaign(client, brand_id, name):
    return submit_and_review(client, brand_id, CAMPAIGN.format(name=name), title=name)


def edit(client, fact_id, **fields):
    r = client.patch(f"/api/facts/{fact_id}", json=fields)
    assert r.status_code == 200, r.text
    return r.json()


def status_to(client, fact_id, status, reason="Superseded by product team."):
    r = client.patch(f"/api/facts/{fact_id}/status", json={"status": status, "reason": reason})
    assert r.status_code == 200, r.text
    return r.json()


def list_impacts(client, brand_id, **params):
    r = client.get(f"/api/brands/{brand_id}/fact-change-impacts", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def impact_content_titles(client, brand_id, **params):
    return sorted(i["content"]["title"] for i in list_impacts(client, brand_id, **params)["items"])


def impact_rows():
    return sql("SELECT count(*) FROM fact_change_impacts")[0][0]


@pytest.fixture
def world(client, brand, pdf_doc):
    """Two campaigns and one unrelated draft, all reviewed against approved facts; the battery fact is at version 1."""
    battery = make_fact(client, brand["id"], doc=pdf_doc)
    weight = make_fact(client, brand["id"], name="Weight", value="1.2", unit="kg", expires=300, source_note="Confirmed by product team")
    a, run_a = campaign(client, brand["id"], "Summer campaign")
    b, run_b = campaign(client, brand["id"], "Back to school")
    u, run_u = submit_and_review(client, brand["id"], "Our laptop weighs 1.2 kg.", title="Weight note")
    for run in (run_a, run_b):
        ev = [e for f in run["findings"] for e in f["evidence"] if e["fact_id"] == battery["id"]]
        assert ev and all(e["fact_version"] == 1 for e in ev), ev
    return dict(brand=brand, battery=battery, weight=weight, a=a, b=b, u=u, run_a=run_a, run_b=run_b, run_u=run_u)


# ================================================================== A. explicit fact-change tests
def test_p3_01_non_material_edit_creates_no_impacts(client, world):
    edit(client, world["battery"]["id"], owner="Hardware team")
    assert list_impacts(client, world["brand"]["id"])["total"] == 0 and impact_rows() == 0


def test_p3_02_material_revision_flags_content_that_relied_on_the_old_version(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours", change_reason="Test results revised.")
    page = list_impacts(client, world["brand"]["id"])
    assert page["total"] == 2
    assert impact_content_titles(client, world["brand"]["id"]) == ["Back to school", "Summer campaign"]
    for item in page["items"]:
        assert item["status"] == "needs_review" and item["trigger_type"] == "fact_revision" and item["change_type"] == "material_edit"
        assert "18 hours" in item["headline"] and "14 hours" in item["headline"]
        assert "no longer" in item["reason"] and "Another review is recommended" in item["reason"]


def test_p3_03_links_through_finding_evidence(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    item = next(i for i in list_impacts(client, world["brand"]["id"])["items"] if i["content"]["id"] == world["a"]["id"])
    detail = client.get(f"/api/fact-change-impacts/{item['id']}").json()
    original = next(e for f in world["run_a"]["findings"] for e in f["evidence"] if e["fact_id"] == world["battery"]["id"])
    link = sql("SELECT evidence_id::text, match_basis FROM fact_change_impact_findings WHERE impact_id = :i", i=item["id"])
    assert link == [(original["id"], "evidence")]
    assert detail["findings"][0]["match_basis"] == "evidence"
    assert item["affected_claim"] == world["run_a"]["findings"][0]["claim_text"]


def test_p3_04_finding_referencing_fact_only_through_matched_fact_id(client, world):
    # Remove the evidence rows so the finding names the fact only through matched_fact_id (an undecided match has this shape).
    finding_id = world["run_a"]["findings"][0]["id"]
    assert world["run_a"]["findings"][0]["matched_fact_id"] == world["battery"]["id"]
    sql("DELETE FROM finding_evidence WHERE finding_id = :f", f=finding_id)
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    items = list_impacts(client, world["brand"]["id"])["items"]
    assert sorted(i["content"]["title"] for i in items) == ["Back to school", "Summer campaign"]
    detail = client.get(f"/api/fact-change-impacts/{next(i['id'] for i in items if i['content']['id'] == world['a']['id'])}").json()
    assert detail["findings"][0]["match_basis"] == "matched_fact"
    assert detail["findings"][0]["relied_fact_version"] == 1  # inferred from the revision timeline, not from the current fact


def test_p3_04b_matched_fact_finding_from_a_run_before_the_fact_was_approved_is_not_flagged(client, world):
    # A run that started while the fact was not approved cannot have relied on it.
    sql("DELETE FROM finding_evidence WHERE finding_id = :f", f=world["run_a"]["findings"][0]["id"])
    sql("UPDATE fact_revisions SET snapshot = jsonb_set(snapshot, '{status}', '\"proposed\"') WHERE fact_id = :f AND revision_number = 1", f=world["battery"]["id"])
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    # (revision 1 now claims 'proposed'; the edit sees a fact that was not current before the change, so nothing is flagged)
    assert list_impacts(client, world["brand"]["id"])["total"] == 0


def test_p3_05_impact_records_previous_and_current_versions(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    for item in list_impacts(client, world["brand"]["id"])["items"]:
        assert (item["previous_fact_version"], item["current_fact_version"]) == (1, 2)
        assert item["previous_value"] == "Up to 18 hours"
        assert item["current_value"] == "Up to 14 hours"


def test_p3_06_review_that_already_used_the_new_version_is_not_flagged(client, world):
    fid = world["battery"]["id"]
    edit(client, fid, value="Up to 14 hours")                      # v2 (proposed): flags the two campaigns
    status_to(client, fid, "active")                               # v3: approved again
    late, run = campaign(client, world["brand"]["id"], "Autumn campaign")  # reviewed against v3 ("14 hours" fact)
    assert {e["fact_version"] for f in run["findings"] for e in f["evidence"] if e["fact_id"] == fid} == {3}
    # Replaying the v2 event must not flag the review that already used v3.
    rev2 = sql("SELECT id::text FROM fact_revisions WHERE fact_id = :f AND revision_number = 2", f=fid)[0][0]
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as s:
        assert impacts.propagate_revision_by_id(s, uuid.UUID(rev2)) == []
    engine.dispose()
    assert "Autumn campaign" not in impact_content_titles(client, world["brand"]["id"])
    # ...but a later change does flag it, and records that it relied on version 3.
    edit(client, fid, value="Up to 12 hours")
    autumn = next(i for i in list_impacts(client, world["brand"]["id"])["items"] if i["content"]["title"] == "Autumn campaign")
    assert (autumn["previous_fact_version"], autumn["current_fact_version"], autumn["previous_value"]) == (3, 4, "Up to 14 hours")


def test_p3_07_several_findings_in_one_asset_give_one_impact(client, world):
    text_ = "Battery life is up to 18 hours under specified test conditions. Enjoy a battery life of up to 18 hours under specified test conditions all day."
    c, run = submit_and_review(client, world["brand"]["id"], text_, title="Double mention")
    on_fact = [f for f in run["findings"] if any(e["fact_id"] == world["battery"]["id"] for e in f["evidence"])]
    assert len(on_fact) >= 2
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    items = [i for i in list_impacts(client, world["brand"]["id"])["items"] if i["content"]["id"] == c["id"]]
    assert len(items) == 1 and items[0]["affected_finding_count"] == len(on_fact)
    assert sql("SELECT count(*) FROM fact_change_impacts WHERE content_submission_id = :c", c=c["id"])[0][0] == 1


def test_p3_08_one_fact_used_by_five_assets_flags_all_five(client, brand, pdf_doc):
    fact = make_fact(client, brand["id"], doc=pdf_doc)
    names = [f"Campaign {n}" for n in range(1, 6)]
    for n in names:
        campaign(client, brand["id"], n)
    edit(client, fact["id"], value="Up to 14 hours")
    assert impact_content_titles(client, brand["id"]) == sorted(names)


def test_p3_09_unrelated_content_is_not_flagged(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    titles = impact_content_titles(client, world["brand"]["id"])
    assert "Weight note" not in titles and len(titles) == 2


def test_p3_10_other_brand_with_an_equivalent_fact_is_not_flagged(client, world, other_brand):
    twin = make_fact(client, other_brand["id"])
    campaign(client, other_brand["id"], "Other brand ad")
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    assert list_impacts(client, other_brand["id"])["total"] == 0
    assert "Other brand ad" not in impact_content_titles(client, world["brand"]["id"])
    edit(client, twin["id"], value="Up to 10 hours")   # and the reverse direction
    assert impact_content_titles(client, other_brand["id"]) == ["Other brand ad"]
    assert len(impact_content_titles(client, world["brand"]["id"])) == 2


# ================================================================== B. material versus metadata-only changes
@pytest.mark.parametrize("fields", [
    {"value": "Up to 14 hours"},                                  # P3-11
    {"qualifications": "Under laboratory conditions"},            # P3-12
    {"unit": "hours"},                                            # P3-13
    {"category": "approved_claim"},                               # P3-13
    {"name": "Battery runtime"},
    {"source_page": 1},                                           # P3-14
    {"source_excerpt": "Battery life: up to 18 hours."},          # P3-14
])
def test_p3_11_to_14_material_field_changes_flag_dependent_content(client, world, fields):
    r = edit(client, world["battery"]["id"], **fields)
    assert r["status"] == "proposed"
    page = list_impacts(client, world["brand"]["id"])
    assert page["total"] == 2 and {i["change_type"] for i in page["items"]} == {"material_edit"}


def test_p3_14b_changing_the_source_document_flags_content_that_relied_on_the_old_source(client, world):
    other = upload(client, world["brand"]["id"], "spec2.pdf", make_pdf(["Page one", "Battery life: up to 18 hours under specified test conditions."]), "application/pdf", title="Spec v2")
    assert other.status_code == 201, other.text
    edit(client, world["battery"]["id"], source_document_id=other.json()["id"])
    assert list_impacts(client, world["brand"]["id"])["total"] == 2
    detail = client.get(f"/api/fact-change-impacts/{list_impacts(client, world['brand']['id'])['items'][0]['id']}").json()
    assert detail["previous_snapshot"]["source_document_id"] != detail["new_snapshot"]["source_document_id"]


@pytest.mark.parametrize("target", ["retired", "proposed", "expired"])
def test_p3_15_fact_that_is_no_longer_current_approved_evidence_flags_content(client, world, target):
    status_to(client, world["battery"]["id"], target)
    page = list_impacts(client, world["brand"]["id"])
    assert page["total"] == 2 and {i["change_type"] for i in page["items"]} == {"no_longer_approved"}
    assert all(i["fact"]["effective_state"] != "current" for i in page["items"])


def test_p3_16a_extending_the_expiry_date_creates_no_impact(client, world):
    edit(client, world["battery"]["id"], expires_at=days(900))
    assert list_impacts(client, world["brand"]["id"])["total"] == 0


def test_p3_16b_expiry_date_moved_into_the_past_flags_content(client, world):
    r = edit(client, world["battery"]["id"], expires_at=days(-1))
    assert r["status"] == "active" and r["effective_state"] == "expired"
    page = list_impacts(client, world["brand"]["id"])
    assert page["total"] == 2 and {i["change_type"] for i in page["items"]} == {"validity_changed"}
    assert all("no longer valid today" in i["headline"] for i in page["items"])


def test_p3_16c_valid_from_moved_into_the_future_flags_content(client, world):
    r = edit(client, world["battery"]["id"], valid_from=days(30))
    assert r["effective_state"] == "pending"
    assert list_impacts(client, world["brand"]["id"])["total"] == 2


def test_p3_16d_shortening_to_a_date_that_is_still_valid_flags_nothing_until_it_passes(client, world, monkeypatch):
    edit(client, world["battery"]["id"], expires_at=days(5))
    assert list_impacts(client, world["brand"]["id"])["total"] == 0
    set_today(monkeypatch, date(2026, 10, 28))                      # day 6: past the new, shorter expiry
    page = list_impacts(client, world["brand"]["id"])
    assert page["total"] == 2 and {i["trigger_type"] for i in page["items"]} == {"fact_expiry"}


def test_p3_17_owner_change_creates_no_impact(client, world):
    edit(client, world["battery"]["id"], owner="Someone Else")
    assert impact_rows() == 0


def test_p3_18_review_reminder_date_change_creates_no_impact(client, world):
    edit(client, world["battery"]["id"], review_date=days(60))
    assert impact_rows() == 0


def test_p3_19_value_change_returns_fact_to_proposed_and_new_value_is_not_used_as_approved_evidence(client, world):
    r = edit(client, world["battery"]["id"], value="Up to 14 hours")
    assert r["status"] == "proposed" and r["effective_state"] == "unapproved"
    assert list_impacts(client, world["brand"]["id"])["total"] == 2
    _, run = submit_and_review(client, world["brand"]["id"], "Battery life is up to 14 hours under specified test conditions.", title="New wording")
    finding = run["findings"][0]
    assert finding["status"] != "supported"
    assert not any(e["fact_id"] == world["battery"]["id"] and e["role"] == "supports" for e in finding["evidence"])


def test_p3_19b_approval_of_the_proposed_fact_does_not_flag_anything_new(client, world):
    fid = world["battery"]["id"]
    edit(client, fid, value="Up to 14 hours")
    before = impact_rows()
    status_to(client, fid, "active")
    assert impact_rows() == before == 2


def test_dated_edit_before_any_review_creates_nothing(client, brand, pdf_doc):
    fact = make_fact(client, brand["id"], doc=pdf_doc)
    edit(client, fact["id"], value="Up to 14 hours")
    assert impact_rows() == 0


# ================================================================== C. idempotency and concurrency
def test_p3_20_propagation_invoked_twice_for_one_revision_creates_no_duplicates(client, world):
    fid = world["battery"]["id"]
    edit(client, fid, value="Up to 14 hours")
    assert impact_rows() == 2
    rev = sql("SELECT id::text FROM fact_revisions WHERE fact_id = :f AND revision_number = 2", f=fid)[0][0]
    engine = create_engine(os.environ["DATABASE_URL"])
    for _ in range(3):
        with Session(engine) as s:
            assert impacts.propagate_revision_by_id(s, uuid.UUID(rev)) == []
    engine.dispose()
    assert impact_rows() == 2
    assert sql("SELECT count(*) FROM fact_change_impact_findings")[0][0] == 2


def test_p3_21_repeated_list_requests_reuse_records_and_add_no_expiry_duplicates(client, world, monkeypatch):
    set_today(monkeypatch, date(2027, 9, 1))     # battery fact expires at day 300 = 2027-08-18
    first = list_impacts(client, world["brand"]["id"])
    ids = sorted(i["id"] for i in first["items"])
    for _ in range(4):
        again = list_impacts(client, world["brand"]["id"])
        assert sorted(i["id"] for i in again["items"]) == ids and again["total"] == first["total"]
    assert client.get(f"/api/brands/{world['brand']['id']}/fact-change-impacts/summary").status_code == 200
    assert impact_rows() == first["total"] > 0


def test_p3_22_two_concurrent_requests_for_one_revision_cannot_duplicate_impacts(client, world, monkeypatch):
    fid = world["battery"]["id"]
    original = facts_svc._propagate
    monkeypatch.setattr(facts_svc, "_propagate", lambda *a, **k: None)   # the edit commits without propagation (as after a crash)
    edit(client, fid, value="Up to 14 hours")
    monkeypatch.setattr(facts_svc, "_propagate", original)
    assert impact_rows() == 0

    barrier = threading.Barrier(2, timeout=15)
    real_find = impacts._find_dependents

    def synced(*args, **kwargs):          # both workers have computed the same candidates before either writes
        found = real_find(*args, **kwargs)
        barrier.wait()
        return found

    monkeypatch.setattr(impacts, "_find_dependents", synced)
    engine = create_engine(os.environ["DATABASE_URL"])

    def worker(_):
        with Session(engine) as s:
            revision = s.scalar(select(FactRevision).where(FactRevision.fact_id == uuid.UUID(fid), FactRevision.revision_number == 2))
            fact = s.get(ApprovedFact, uuid.UUID(fid))
            made = impacts.propagate_revision(s, fact, revision)
            s.commit()
            return len(made)

    with ThreadPoolExecutor(2) as pool:
        created = list(pool.map(worker, range(2)))
    engine.dispose()
    assert sum(created) == 2 and sorted(created) == [0, 2]
    assert impact_rows() == 2 and sql("SELECT count(*) FROM fact_change_impact_findings")[0][0] == 2


def test_p3_22b_database_rejects_a_duplicate_event_for_the_same_content(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    with pytest.raises(Exception, match="uq_fact_change_impacts_event_content"):
        sql("""INSERT INTO fact_change_impacts (brand_id, fact_id, content_submission_id, fact_revision_id, trigger_type, trigger_key,
                   change_type, previous_fact_version, current_fact_version, source_review_run_id, reason)
               SELECT brand_id, fact_id, content_submission_id, fact_revision_id, trigger_type, trigger_key, change_type,
                      previous_fact_version, current_fact_version, source_review_run_id, reason
               FROM fact_change_impacts LIMIT 1""")


def test_p3_22c_database_attributes_a_finding_to_one_event_per_fact(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    with pytest.raises(Exception, match="uq_fact_change_impact_findings_finding_fact"):
        sql("""INSERT INTO fact_change_impact_findings (brand_id, impact_id, finding_id, fact_id, review_run_id, evidence_id, match_basis, relied_fact_version)
               SELECT brand_id, impact_id, finding_id, fact_id, review_run_id, evidence_id, match_basis, relied_fact_version
               FROM fact_change_impact_findings LIMIT 1""")


def test_p3_23_failure_while_recording_impacts_rolls_the_fact_change_back(client, world, monkeypatch):
    fid = world["battery"]["id"]

    def broken(db, **kwargs):             # a real database error raised after the fact and its revision were written
        db.execute(text("INSERT INTO fact_change_impacts (id) VALUES (gen_random_uuid())"))

    monkeypatch.setattr(impacts, "_record_event", broken)
    r = client.patch(f"/api/facts/{fid}", json={"value": "Up to 14 hours"})
    assert r.status_code in (409, 500) and "error" in r.json()          # the caller is told; nothing reports success
    monkeypatch.undo()
    fact = client.get(f"/api/facts/{fid}").json()
    assert fact["value"] == "Up to 18 hours" and fact["status"] == "active" and fact["version"] == 1
    assert sql("SELECT count(*) FROM fact_revisions WHERE fact_id = :f", f=fid)[0][0] == 1
    assert impact_rows() == 0
    # and the same edit succeeds once the fault is gone, with its impacts, in one step
    edit(client, fid, value="Up to 14 hours")
    assert impact_rows() == 2


def test_p3_24_failed_review_run_is_not_proof_of_reliance(client, world):
    # Turn campaign A's run into a failed run; its findings still exist but a failed review proves nothing.
    sql("UPDATE review_runs SET status = 'failed', error_code = 'provider_unavailable' WHERE id = :r", r=world["run_a"]["id"])
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    assert impact_content_titles(client, world["brand"]["id"]) == ["Back to school"]


def test_p3_24b_a_review_that_failed_at_the_provider_is_not_flagged(client, brand, pdf_doc):
    from app.api.deps import get_review_provider as dep
    from app.services.review.providers import ProviderUnavailable
    from tests.fakes import FakeProvider

    fact = make_fact(client, brand["id"], doc=pdf_doc)
    client.app.dependency_overrides[dep] = lambda: FakeProvider(extract=ProviderUnavailable("down"))
    c = client.post(f"/api/brands/{brand['id']}/content", json={"title": "Down", "content": CAMPAIGN.format(name="Down")}).json()
    run = client.post(f"/api/content/{c['id']}/reviews", json={}).json()
    assert run["status"] == "failed"
    edit(client, fact["id"], value="Up to 14 hours")
    assert impact_rows() == 0


def test_p3_25_completed_review_without_a_relationship_to_the_fact_is_not_flagged(client, world):
    _, empty_run = submit_and_review(client, world["brand"]["id"], "Welcome to our store. We love our customers.", title="No claims")
    _, unsupported = submit_and_review(client, world["brand"]["id"], "Ships within 3 days.", title="Shipping")
    assert empty_run["findings"] == [] and unsupported["findings"][0]["status"] == "unsupported"
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    titles = impact_content_titles(client, world["brand"]["id"])
    assert "No claims" not in titles and "Shipping" not in titles and len(titles) == 2


def test_lapse_before_the_edit_is_recorded_once_as_an_expiry(client, world, monkeypatch):
    """The fact lapsed (day 300) and nobody listed impacts; then it is edited. The lapse must not be lost."""
    set_today(monkeypatch, date(2027, 9, 1))
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    page = list_impacts(client, world["brand"]["id"], fact_id=world["battery"]["id"])
    assert page["total"] == 2 and {i["trigger_type"] for i in page["items"]} == {"fact_expiry"}   # one impact per campaign, not two events
    assert list_impacts(client, world["brand"]["id"], fact_id=world["battery"]["id"])["total"] == 2
    # the (also lapsed) weight fact is swept independently and flags only its own content
    assert impact_content_titles(client, world["brand"]["id"], fact_id=world["weight"]["id"]) == ["Weight note"]
    assert impact_rows() == 3


def test_extension_saved_after_a_lapse_still_records_the_lapse(client, world, monkeypatch):
    set_today(monkeypatch, date(2027, 9, 1))
    edit(client, world["battery"]["id"], expires_at="2028-12-31")
    page = list_impacts(client, world["brand"]["id"], fact_id=world["battery"]["id"])
    assert page["total"] == 2 and {i["trigger_type"] for i in page["items"]} == {"fact_expiry"}


# ================================================================== D. expiry
def expiring_world(client, brand, pdf_doc, expires=10):
    fact = make_fact(client, brand["id"], doc=pdf_doc, expires=expires)
    campaign(client, brand["id"], "Summer campaign")
    campaign(client, brand["id"], "Back to school")
    return fact


def test_p3_26_expiry_date_is_inclusive(client, brand, pdf_doc, monkeypatch):
    fact = expiring_world(client, brand, pdf_doc)
    set_today(monkeypatch, date(2026, 11, 1))                       # day 10 == expires_at
    assert client.get(f"/api/facts/{fact['id']}").json()["effective_state"] == "current"
    assert list_impacts(client, brand["id"])["total"] == 0


def test_p3_27_28_after_the_expiry_date_dependent_content_is_flagged(client, brand, pdf_doc, monkeypatch):
    fact = expiring_world(client, brand, pdf_doc)
    set_today(monkeypatch, date(2026, 11, 2))                       # day 11
    assert client.get(f"/api/facts/{fact['id']}").json()["effective_state"] == "expired"
    page = list_impacts(client, brand["id"])
    assert page["total"] == 2
    for item in page["items"]:
        assert item["trigger_type"] == "fact_expiry" and item["change_type"] == "expired"
        assert item["fact"]["status"] == "active" and item["fact"]["effective_state"] == "expired"
        assert "2026-11-01" in item["headline"] and (item["previous_fact_version"], item["current_fact_version"]) == (1, 1)
    assert sql("SELECT count(*) FROM fact_revisions WHERE fact_id = :f", f=fact["id"])[0][0] == 1   # no explicit edit was needed


def test_p3_29_expired_fact_without_dependent_content_creates_no_rows(client, brand, pdf_doc, monkeypatch):
    make_fact(client, brand["id"], doc=pdf_doc, expires=10)
    campaign_unrelated = submit_and_review(client, brand["id"], "Ships within 3 days.", title="Shipping")
    assert campaign_unrelated
    set_today(monkeypatch, date(2026, 12, 1))
    assert list_impacts(client, brand["id"])["total"] == 0 and impact_rows() == 0


def test_p3_30_repeated_sweeps_give_one_impact_per_asset_per_expiry_event(client, brand, pdf_doc, monkeypatch):
    expiring_world(client, brand, pdf_doc)
    for day in (date(2026, 11, 2), date(2026, 11, 3), date(2027, 3, 1), date(2027, 3, 1)):
        set_today(monkeypatch, day)
        assert list_impacts(client, brand["id"])["total"] == 2
    assert impact_rows() == 2


def test_p3_31_fact_without_an_expiry_date_is_never_expired_by_the_sweep(client, brand, pdf_doc, monkeypatch):
    make_fact(client, brand["id"], doc=pdf_doc, expires=None)
    campaign(client, brand["id"], "Summer campaign")
    set_today(monkeypatch, date(2040, 1, 1))
    assert list_impacts(client, brand["id"])["total"] == 0


def test_p3_32_review_made_against_the_newer_version_is_not_attributed_to_the_old_one(client, brand, pdf_doc, monkeypatch):
    fact = expiring_world(client, brand, pdf_doc, expires=10)
    edit(client, fact["id"], value="Up to 14 hours", expires_at=days(60))     # v2 proposed: flags the two old campaigns
    status_to(client, fact["id"], "active")                                   # v3 approved, valid until day 60
    campaign(client, brand["id"], "Autumn campaign")                          # reviewed against v3
    assert impact_content_titles(client, brand["id"]) == ["Back to school", "Summer campaign"]
    set_today(monkeypatch, date(2027, 1, 1))                                  # past day 60
    page = list_impacts(client, brand["id"])
    by_title = {i["content"]["title"]: i for i in page["items"]}
    assert sorted(by_title) == ["Autumn campaign", "Back to school", "Summer campaign"] and page["total"] == 3
    assert by_title["Autumn campaign"]["trigger_type"] == "fact_expiry" and by_title["Autumn campaign"]["previous_fact_version"] == 3
    assert by_title["Summer campaign"]["trigger_type"] == "fact_revision"      # not flagged a second time by the expiry


# ================================================================== E. historical integrity
SNAPSHOT_SQL = """
SELECT (SELECT jsonb_agg(to_jsonb(f) ORDER BY f.id) FROM review_findings f),
       (SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id) FROM finding_evidence e),
       (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM review_runs r),
       (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM content_submissions c)"""


def test_p3_33_original_findings_evidence_runs_and_content_are_untouched(client, world, monkeypatch):
    before = sql(SNAPSHOT_SQL)
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    status_to(client, world["battery"]["id"], "active")
    status_to(client, world["battery"]["id"], "retired")
    set_today(monkeypatch, date(2030, 1, 1))
    list_impacts(client, world["brand"]["id"])
    assert sql(SNAPSHOT_SQL) == before and before[0][0] is not None


def test_p3_34_historical_evidence_snapshot_stays_inspectable(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    findings = client.get(f"/api/reviews/{world['run_a']['id']}/findings").json()["items"]
    ev = next(e for f in findings for e in f["evidence"] if e["fact_id"] == world["battery"]["id"])
    assert (ev["fact_value"], ev["fact_version"], ev["fact_status"], ev["fact_effective_state"]) == ("Up to 18 hours", 1, "active", "current")
    assert ev["excerpt"] == BATTERY_EXCERPT and ev["source_page"] == 2


def test_p3_35_old_and_current_wordings_are_distinct_in_the_detail(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours", qualifications="Under revised test conditions")
    item = list_impacts(client, world["brand"]["id"])["items"][0]
    d = client.get(f"/api/fact-change-impacts/{item['id']}").json()
    assert d["previous_snapshot"]["value"] == "Up to 18 hours" and d["new_snapshot"]["value"] == "Up to 14 hours"
    assert d["previous_snapshot"]["qualifications"] == "Under specified test conditions"
    assert d["current_fact"]["value"] == "Up to 14 hours" and d["current_fact"]["status"] == "proposed"
    ev = d["findings"][0]["finding"]["evidence"][0]
    assert ev["fact_value"] == "Up to 18 hours"           # what the review actually saw
    assert d["previous_snapshot"] != d["new_snapshot"]


def test_p3_36_references_of_a_recorded_impact_are_valid_and_consistent(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    rows = sql("""
        SELECT i.fact_id = r.fact_id, i.fact_revision_id IS NOT NULL, rr.content_submission_id = i.content_submission_id,
               i.brand_id = c.brand_id, i.brand_id = f.brand_id,
               (SELECT bool_and(rr2.content_submission_id = i.content_submission_id AND fl.review_run_id = rr2.id)
                  FROM fact_change_impact_findings l JOIN review_findings fl ON fl.id = l.finding_id
                  JOIN review_runs rr2 ON rr2.id = fl.review_run_id WHERE l.impact_id = i.id),
               r.revision_number
        FROM fact_change_impacts i
        JOIN fact_revisions r ON r.id = i.fact_revision_id
        JOIN review_runs rr ON rr.id = i.source_review_run_id
        JOIN content_submissions c ON c.id = i.content_submission_id
        JOIN approved_facts f ON f.id = i.fact_id""")
    assert len(rows) == 2 and all(row[:6] == (True,) * 6 and row[6] == 2 for row in rows)


def test_p3_37_archiving_the_source_does_not_invalidate_the_fact_or_create_impacts(client, world, pdf_doc):
    r = client.post(f"/api/documents/{pdf_doc['id']}/archive")
    assert r.status_code == 200
    fact = client.get(f"/api/facts/{world['battery']['id']}").json()
    assert fact["effective_state"] == "current" and "source_document_archived" in fact["warnings"] and fact["source"]["archived"] is True
    assert list_impacts(client, world["brand"]["id"])["total"] == 0           # existing policy: archived source stays citable, flagged
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    item = list_impacts(client, world["brand"]["id"])["items"][0]
    d = client.get(f"/api/fact-change-impacts/{item['id']}").json()
    assert d["current_fact"]["source"]["archived"] is True                    # the former source is not reported as live
    assert d["previous_snapshot"]["source_document_id"] == pdf_doc["id"]      # and the historical citation is preserved


# ================================================================== F. API
def test_p3_38_brand_list_with_pagination_counts_and_stable_order(client, brand, pdf_doc):
    fact = make_fact(client, brand["id"], doc=pdf_doc)
    names = [f"Campaign {n}" for n in range(1, 6)]
    for n in names:
        campaign(client, brand["id"], n)
    edit(client, fact["id"], value="Up to 14 hours")
    pages = [list_impacts(client, brand["id"], limit=2, offset=o) for o in (0, 2, 4)]
    assert [p["total"] for p in pages] == [5, 5, 5] and [len(p["items"]) for p in pages] == [2, 2, 1]
    seen = [i["id"] for p in pages for i in p["items"]]
    assert len(set(seen)) == 5
    assert seen == [i["id"] for i in list_impacts(client, brand["id"], limit=200)["items"]]   # stable ordering
    assert (pages[1]["limit"], pages[1]["offset"]) == (2, 2)
    s = client.get(f"/api/brands/{brand['id']}/fact-change-impacts/summary").json()
    assert s == {"open_impacts": 5, "resolved_impacts": 0, "dismissed_impacts": 0, "total_impacts": 5, "facts_with_changes": 1, "content_needing_review": 5, "expiry_affected_content": 0, "revision_affected_content": 5}


def test_p3_38b_filters(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    b = world["brand"]["id"]
    assert list_impacts(client, b, status="needs_review")["total"] == 2
    assert list_impacts(client, b, trigger_type="fact_expiry")["total"] == 0
    assert list_impacts(client, b, trigger_type="fact_revision")["total"] == 2
    assert list_impacts(client, b, fact_id=world["battery"]["id"])["total"] == 2
    assert list_impacts(client, b, fact_id=world["weight"]["id"])["total"] == 0
    assert list_impacts(client, b, content_id=world["a"]["id"])["total"] == 1


def test_p3_39_impacts_of_one_fact(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    edit(client, world["weight"]["id"], value="1.4")
    r = client.get(f"/api/facts/{world['battery']['id']}/impacts").json()
    assert r["total"] == 2 and {i["fact"]["id"] for i in r["items"]} == {world["battery"]["id"]}
    w = client.get(f"/api/facts/{world['weight']['id']}/impacts").json()
    assert [i["content"]["title"] for i in w["items"]] == ["Weight note"]
    assert list_impacts(client, world["brand"]["id"])["total"] == 3


def test_p3_40_impact_detail(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours", actor="Meenal", change_reason="Test results revised.")
    item = next(i for i in list_impacts(client, world["brand"]["id"])["items"] if i["content"]["id"] == world["a"]["id"])
    d = client.get(f"/api/fact-change-impacts/{item['id']}").json()
    assert d["id"] == item["id"] and d["content"]["title"] == "Summer campaign" and d["status"] == "needs_review"
    assert d["trigger_revision"]["revision_number"] == 2 and d["trigger_revision"]["changed_by"] == "Meenal"
    assert d["trigger_revision"]["change_reason"] == "Test results revised."
    assert d["trigger_revision"]["changes"]["value"] == {"old": "Up to 18 hours", "new": "Up to 14 hours"}
    assert d["change_summary"]["material_fields"] == ["value"] and d["change_summary"]["before_effective_state"] == "current"
    f = d["findings"][0]
    assert f["finding"]["claim_text"] == world["run_a"]["findings"][0]["claim_text"] and f["relied_fact_version"] == 1
    assert f["review_run"]["id"] == world["run_a"]["id"] and f["finding"]["evidence"][0]["fact_value"] == "Up to 18 hours"
    assert d["source_review_run_id"] == world["run_a"]["id"] and d["reviewed_since_detection"] is False


def test_reviewed_since_detection_is_informational_and_does_not_resolve_the_impact(client, world):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    client.post(f"/api/content/{world['a']['id']}/reviews", json={})
    item = next(i for i in list_impacts(client, world["brand"]["id"])["items"] if i["content"]["id"] == world["a"]["id"])
    assert item["reviewed_since_detection"] is True and item["status"] == "needs_review"


def test_p3_41_unknown_ids_give_structured_404(client, world):
    ghost = str(uuid.uuid4())
    for url in (f"/api/facts/{ghost}/impacts", f"/api/fact-change-impacts/{ghost}", f"/api/brands/{ghost}/fact-change-impacts", f"/api/brands/{ghost}/fact-change-impacts/summary"):
        r = client.get(url)
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found", url
    r = client.get(f"/api/brands/{world['brand']['id']}/fact-change-impacts", params={"fact_id": ghost})
    assert r.status_code == 404


@pytest.mark.parametrize("url", [
    "/api/fact-change-impacts/not-a-uuid", "/api/facts/123/impacts", "/api/brands/xyz/fact-change-impacts",
])
def test_p3_42_malformed_ids_are_validation_errors(client, url):
    r = client.get(url)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("params", [{"status": "done"}, {"trigger_type": "magic"}, {"limit": 0}, {"limit": 500}, {"offset": -1}, {"fact_id": "nope"}, {"content_id": "nope"}])
def test_p3_42b_invalid_filters_are_validation_errors(client, brand, params):
    r = client.get(f"/api/brands/{brand['id']}/fact-change-impacts", params=params)
    assert r.status_code == 422 and r.json()["error"]["details"]


def test_p3_43_cross_brand_data_is_never_exposed(client, world, other_brand):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    assert list_impacts(client, other_brand["id"])["items"] == []
    r = client.get(f"/api/brands/{other_brand['id']}/fact-change-impacts", params={"fact_id": world["battery"]["id"]})
    assert r.status_code == 404                                                # the fact is not this brand's
    assert client.get(f"/api/brands/{other_brand['id']}/fact-change-impacts/summary").json()["open_impacts"] == 0
    mine = list_impacts(client, world["brand"]["id"])["items"]
    assert all(i["brand_id"] == world["brand"]["id"] for i in mine)


def test_p3_43b_database_refuses_an_impact_that_crosses_brands(client, world, other_brand):
    edit(client, world["battery"]["id"], value="Up to 14 hours")
    with pytest.raises(Exception, match="fk_fact_change_impacts_(fact|content|run)_same_brand"):
        sql("""INSERT INTO fact_change_impacts (brand_id, fact_id, content_submission_id, fact_revision_id, trigger_type, trigger_key,
                   change_type, previous_fact_version, current_fact_version, source_review_run_id, reason)
               SELECT :b, fact_id, content_submission_id, fact_revision_id, trigger_type, 'revision:forged', change_type,
                      previous_fact_version, current_fact_version, source_review_run_id, reason
               FROM fact_change_impacts LIMIT 1""", b=other_brand["id"])


def test_p3_44_database_outage_is_an_error_not_an_empty_list(client, world):
    from sqlalchemy.orm import Session as S

    def unreachable():
        engine = create_engine("postgresql+psycopg://nobody:x@127.0.0.1:1/none", connect_args={"connect_timeout": 2})
        with S(engine) as session:
            yield session

    client.app.dependency_overrides[get_db] = unreachable
    try:
        for url in (f"/api/brands/{world['brand']['id']}/fact-change-impacts", f"/api/brands/{world['brand']['id']}/fact-change-impacts/summary",
                    f"/api/facts/{world['battery']['id']}/impacts", f"/api/fact-change-impacts/{uuid.uuid4()}"):
            r = client.get(url)
            assert r.status_code == 503 and r.json()["error"]["code"] == "database_unavailable", url
            assert "items" not in r.json() and "nobody" not in r.text and "127.0.0.1" not in r.text
    finally:
        client.app.dependency_overrides.pop(get_db, None)


def test_p3_44b_a_failing_expiry_sweep_fails_the_request(client, world, monkeypatch):
    def broken(db, brand_id):
        raise RuntimeError("sweep failed")

    monkeypatch.setattr(impacts, "detect_expired", broken)
    r = client.get(f"/api/brands/{world['brand']['id']}/fact-change-impacts")
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error" and "sweep failed" not in r.text


# ================================================================== rules (pure) and schema
def snap(**over):
    base = dict(name="Battery life", value="Up to 18 hours", category="product_spec", qualifications=None, unit=None, status="active",
                source_document_id=None, source_page=None, source_excerpt=None, source_note="x", owner="A", valid_from=None,
                review_date=None, expires_at="2027-01-01")
    return base | over


@pytest.mark.parametrize("after,expected", [
    (dict(owner="B"), None),
    (dict(review_date="2026-12-01"), None),
    (dict(expires_at="2028-01-01"), None),
    (dict(valid_from="2020-01-01"), None),
    (dict(value="Up to 14 hours", status="proposed"), "material_edit"),
    (dict(qualifications="Lab"), "material_edit"),
    (dict(status="retired"), "no_longer_approved"),
    (dict(expires_at="2026-10-21"), "validity_changed"),
    (dict(valid_from="2026-11-01"), "validity_changed"),
])
def test_assess_revision_rules(after, expected):
    result = impacts.assess_revision(snap(), snap(**after), TODAY)
    assert (result.change_type if result else None) == expected


def test_assess_revision_ignores_changes_to_a_fact_that_was_not_current_evidence():
    assert impacts.assess_revision(snap(status="proposed"), snap(status="proposed", value="x"), TODAY) is None
    assert impacts.assess_revision(snap(status="retired"), snap(status="retired", value="x"), TODAY) is None
    assert impacts.assess_revision(snap(expires_at="2026-10-01"), snap(expires_at="2026-10-01", value="x"), TODAY) is None


def test_expiry_boundary_in_the_pure_rule():
    assert impacts.state_of_snapshot(snap(expires_at="2026-10-22"), TODAY) == "current"
    assert impacts.state_of_snapshot(snap(expires_at="2026-10-21"), TODAY) == "expired"
    assert impacts.state_of_snapshot(snap(expires_at=None), date(2099, 1, 1)) == "current"


def test_schema_has_the_required_constraints_and_indexes(client):
    from sqlalchemy import inspect

    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        insp = inspect(engine)
        uniques = {u["name"] for u in insp.get_unique_constraints("fact_change_impacts")}
        assert {"uq_fact_change_impacts_event_content", "uq_fact_change_impacts_id_brand_id"} <= uniques
        assert "uq_fact_change_impact_findings_finding_fact" in {u["name"] for u in insp.get_unique_constraints("fact_change_impact_findings")}
        ix = {i["name"] for i in insp.get_indexes("fact_change_impacts")}
        assert {"ix_fact_change_impacts_fact", "ix_fact_change_impacts_content", "ix_fact_change_impacts_brand_status", "ix_fact_change_impacts_revision"} <= ix
        fks = {fk["name"]: fk for fk in insp.get_foreign_keys("fact_change_impacts")}
        assert fks["fk_fact_change_impacts_fact_same_brand"]["constrained_columns"] == ["fact_id", "brand_id"]
        assert fks["fk_fact_change_impacts_revision_same_fact"]["constrained_columns"] == ["fact_revision_id", "fact_id"]
        assert all(fk["options"].get("ondelete") == "RESTRICT" for n, fk in fks.items())
    finally:
        engine.dispose()


def test_models_and_migration_agree(client):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    import app.models  # noqa: F401
    from app.db.base import Base

    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.connect() as conn:
            assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
    finally:
        engine.dispose()


def test_migration_0003_upgrades_downgrades_and_preserves_phase_1_and_2_data(client, world):
    from alembic import command

    from tests.conftest import alembic_config

    before = {t: sql(f"SELECT count(*) FROM {t}")[0][0] for t in ("brands", "approved_facts", "fact_revisions", "content_submissions", "review_runs", "review_findings", "finding_evidence")}
    assert all(n > 0 for n in before.values())
    try:
        command.downgrade(alembic_config(), "0002")
        assert sql("SELECT to_regclass('fact_change_impacts')")[0][0] is None
        assert {t: sql(f"SELECT count(*) FROM {t}")[0][0] for t in before} == before        # Phase 1 and 2 data intact
        command.upgrade(alembic_config(), "head")
    finally:
        command.upgrade(alembic_config(), "head")
    assert sql("SELECT to_regclass('fact_change_impacts')")[0][0] is not None
    assert {t: sql(f"SELECT count(*) FROM {t}")[0][0] for t in before} == before
    edit(client, world["battery"]["id"], value="Up to 14 hours")                              # the feature works after re-upgrade
    assert list_impacts(client, world["brand"]["id"])["total"] == 2


def test_openapi_documents_the_phase_3_endpoints(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    for p in ("/api/brands/{brand_id}/fact-change-impacts", "/api/brands/{brand_id}/fact-change-impacts/summary",
              "/api/facts/{fact_id}/impacts", "/api/fact-change-impacts/{impact_id}"):
        assert p in paths and "get" in paths[p]
