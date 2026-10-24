"""Phase 2 acceptance tests P2-01 to P2-32: content submission, claim extraction, evidence and classification,
persistence and error handling. Backend only; real PostgreSQL; model output is injected with FakeProvider."""
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.api.deps import get_review_provider
from app.main import create_app
from app.services.review import pipeline
from app.services.review.providers import ProviderInvalidOutput, ProviderUnavailable
from tests.conftest import days, fact_payload, upload
from tests.fakes import FakeProvider, assessments_for, claims_json

BATTERY_EXCERPT = "Battery life: up to 18 hours under specified test conditions."
QUALIFIED = "Battery life is up to 18 hours under specified test conditions."


@pytest.fixture(autouse=True)
def _pinned_today(fixed_today):
    return fixed_today


@pytest.fixture
def use_provider(client):
    def install(provider):
        client.app.dependency_overrides[get_review_provider] = lambda: provider
        return provider

    return install


def make_fact(client, brand_id, *, status="active", doc=None, **over):
    body = fact_payload(status=status, expires_at=days(300), **over)
    if doc is not None:
        body.update(source_document_id=doc["id"], source_page=2, source_excerpt=BATTERY_EXCERPT)
        body.pop("source_note", None)
    r = client.post(f"/api/brands/{brand_id}/facts", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def set_status(client, fact_id, status, reason="Superseded."):
    r = client.patch(f"/api/facts/{fact_id}/status", json={"status": status, "reason": reason})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def battery(client, brand, pdf_doc):
    return make_fact(client, brand["id"], doc=pdf_doc)


def submit(client, brand_id, body, title="Spring campaign"):
    r = client.post(f"/api/brands/{brand_id}/content", json={"title": title, "content": body})
    assert r.status_code == 201, r.text
    return r.json()


def review(client, content_id):
    r = client.post(f"/api/content/{content_id}/reviews", json={})
    assert r.status_code == 201, r.text
    return r.json()


def run_on(client, brand_id, body):
    return review(client, submit(client, brand_id, body)["id"])


def one(run, fragment):
    hits = [f for f in run["findings"] if fragment in f["claim_text"]]
    assert len(hits) == 1, [f["claim_text"] for f in run["findings"]]
    return hits[0]


def sql(query, **params):
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.begin() as conn:
            result = conn.execute(text(query), params)
            return result.fetchall() if result.returns_rows else []
    finally:
        engine.dispose()


# ================================================================== A. content submission
def test_p2_01_submit_valid_draft(client, brand):
    r = client.post(f"/api/brands/{brand['id']}/content", json={"title": " Launch email ", "content": "Battery life is up to 18 hours.", "submitted_by": "Meenal"})
    assert r.status_code == 201
    body = r.json()
    uuid.UUID(body["id"])
    assert body["title"] == "Launch email" and body["brand_id"] == brand["id"] and body["submitted_by"] == "Meenal"
    assert len(body["content_hash"]) == 64 and body["review_count"] == 0 and body["latest_review"] is None


@pytest.mark.parametrize("payload,field", [
    ({"title": "", "content": "Some text."}, "title"), ({"title": "   ", "content": "Some text."}, "title"),
    ({"title": "T", "content": ""}, "content"), ({"title": "T", "content": "  \n "}, "content"),
    ({"content": "x"}, "title"), ({"title": "T"}, "content"), ({"title": "T", "content": "x", "extra": 1}, "extra"),
])
def test_p2_02_invalid_input_rejected_and_not_saved(client, brand, payload, field):
    r = client.post(f"/api/brands/{brand['id']}/content", json=payload)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert any(d["field"] == field for d in r.json()["error"]["details"])
    assert client.get(f"/api/brands/{brand['id']}/content").json()["total"] == 0


def test_p2_03_content_length_limit(client, brand):
    assert client.post(f"/api/brands/{brand['id']}/content", json={"title": "T", "content": "a" * 5000}).status_code == 201
    r = client.post(f"/api/brands/{brand['id']}/content", json={"title": "T", "content": "a" * 5001})
    assert r.status_code == 422
    assert "5,000" in r.json()["error"]["details"][0]["message"]
    assert client.get(f"/api/brands/{brand['id']}/content").json()["total"] == 1


def test_p2_04_nonexistent_brand_is_structured_404(client):
    r = client.post(f"/api/brands/{uuid.uuid4()}/content", json={"title": "T", "content": "x"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.get(f"/api/brands/{uuid.uuid4()}/content").status_code == 404


def test_p2_05_retrieve_saved_content_exactly(client, brand):
    text_ = "  Line one.\n\nLine  two with  spacing.  "
    created = submit(client, brand["id"], text_)
    got = client.get(f"/api/content/{created['id']}").json()
    assert got["content"] == text_  # stored exactly as submitted so offsets stay valid
    listing = client.get(f"/api/brands/{brand['id']}/content").json()
    assert listing["total"] == 1 and listing["items"][0]["char_count"] == len(text_) and "content" not in listing["items"][0]


def test_p2_06_content_survives_application_restart(client, brand):
    created = submit(client, brand["id"], "Battery life is up to 18 hours.")
    from app.db import session

    session._engine = None
    with TestClient(create_app()) as fresh:
        assert fresh.get(f"/api/content/{created['id']}").json()["content"] == "Battery life is up to 18 hours."
        assert fresh.get(f"/api/brands/{brand['id']}/content").json()["total"] == 1


def test_content_is_scoped_to_its_brand(client, brand, other_brand):
    submit(client, brand["id"], "Battery life is up to 18 hours.")
    assert client.get(f"/api/brands/{other_brand['id']}/content").json()["total"] == 0


# ================================================================== B. claim extraction
def test_p2_07_one_quantitative_claim(client, brand, battery):
    run = run_on(client, brand["id"], QUALIFIED)
    assert run["total_findings"] == 1
    assert run["findings"][0]["claim_category"] == "quantitative"


def test_p2_08_multiple_distinct_claims_no_duplicates(client, brand, battery, use_provider):
    body = "Battery life is up to 18 hours under specified test conditions. Nova weighs 1.24 kg. Our laptop is the fastest."
    plain = run_on(client, brand["id"], body)
    assert [f["claim_text"] for f in plain["findings"] if f["claim_category"] != "terminology"] == [
        "Battery life is up to 18 hours under specified test conditions.", "Nova weighs 1.24 kg.", "Our laptop is the fastest.",
    ]
    # A model that repeats claims the rules already found must not create duplicates.
    use_provider(FakeProvider(extract=claims_json("Nova weighs 1.24 kg.", "Our laptop is the fastest.")))
    with_ai = run_on(client, brand["id"], body)
    assert [f["claim_text"] for f in with_ai["findings"]] == [f["claim_text"] for f in plain["findings"]]
    assert all(f["extraction_method"] == "deterministic" for f in with_ai["findings"])


def test_p2_09_no_claims_is_distinguished_from_failure(client, brand, battery, use_provider):
    draft = submit(client, brand["id"], "We are delighted to welcome everyone to the event.")
    limited = review(client, draft["id"])
    assert limited["status"] == "completed_limited" and limited["total_findings"] == 0
    assert any("No candidate claims" in n for n in limited["notes"])
    assert limited["limitations"] and "does not mean the content has no claims" in limited["limitations"][0]
    use_provider(FakeProvider(extract='{"claims":[]}'))
    full = review(client, draft["id"])
    assert full["status"] == "completed" and full["analysis_mode"] == "full" and full["total_findings"] == 0 and full["limitations"] == []
    use_provider(FakeProvider(extract=ProviderUnavailable("down")))
    failed = review(client, draft["id"])
    assert failed["status"] == "failed" and failed["total_findings"] == 0


def test_p2_10_offsets_point_at_the_claim_text(client, brand, battery, use_provider):
    body = "Intro line.\n  Battery life is 24 hours.   Weighs 1.24 kg!\nNova is the fastest laptop."
    use_provider(FakeProvider(extract=claims_json("Intro line.")))
    run = run_on(client, brand["id"], body)
    assert run["total_findings"] >= 4
    for f in run["findings"]:
        assert body[f["start_offset"]:f["end_offset"]] == f["claim_text"], f
    assert one(run, "Intro line")["extraction_method"] == "ai"


@pytest.mark.parametrize("bad", [
    "this is not json", '{"claims": "nope"}', '{"claims": [{"category": "general"}]}', '{"claims": [{"text": "x", "category": "bogus"}]}', "[]",
])
def test_p2_11_malformed_model_output_fails_the_review(client, brand, battery, use_provider, bad):
    use_provider(FakeProvider(extract=bad))
    run = run_on(client, brand["id"], QUALIFIED)
    assert run["status"] == "failed" and run["error_code"] == "provider_invalid_output"
    assert run["total_findings"] == 0 and run["findings"] == []
    assert sql("SELECT count(*) FROM review_findings")[0][0] == 0


def test_p2_11b_invented_claim_text_is_discarded(client, brand, battery, use_provider):
    use_provider(FakeProvider(extract=claims_json("This sentence is not in the draft.")))
    run = run_on(client, brand["id"], QUALIFIED)
    assert run["status"] == "completed" and run["total_findings"] == 1
    assert any("not found in the submitted content" in n for n in run["notes"])


def test_p2_12_repeat_review_is_consistent(client, brand, battery):
    draft = submit(client, brand["id"], f"{QUALIFIED} Battery life is 24 hours. Nova is the fastest.")
    a, b = review(client, draft["id"]), review(client, draft["id"])
    key = lambda run: [(f["claim_text"], f["start_offset"], f["status"], f["severity"], [e["fact_id"] for e in f["evidence"]]) for f in run["findings"]]
    assert key(a) == key(b) and a["id"] != b["id"]


# ================================================================== C. evidence and classification
def test_p2_13_and_21_supported_with_real_evidence(client, brand, pdf_doc, battery):
    f = one(run_on(client, brand["id"], QUALIFIED), "Battery")
    assert f["status"] == "supported" and f["severity"] == "low" and f["requires_human_review"] is False
    assert f["matched_fact_id"] == battery["id"]
    (ev,) = f["evidence"]
    assert ev["role"] == "supports" and ev["fact_id"] == battery["id"] and ev["source_document_id"] == pdf_doc["id"]
    assert ev["source_title"] == "Spec" and ev["source_page"] == 2 and ev["excerpt"] == BATTERY_EXCERPT and ev["excerpt_verified"] is True
    # The cited page really contains the excerpt in the stored text, and the section row is the one referenced.
    page2 = client.get(f"/api/documents/{pdf_doc['id']}/sections", params={"page_number": 2}).json()["items"][0]
    assert ev["document_section_id"] == page2["id"] and BATTERY_EXCERPT in " ".join(page2["text"].split())
    fact = client.get(f"/api/facts/{battery['id']}").json()
    assert (ev["fact_name"], ev["fact_value"], ev["fact_version"], ev["fact_effective_state"]) == (fact["name"], fact["value"], fact["version"], "current")


def test_p2_14_conflicting_number_cites_the_approved_fact(client, brand, pdf_doc, battery):
    f = one(run_on(client, brand["id"], "Battery life is 24 hours under specified test conditions."), "24 hours")
    assert f["status"] == "conflicting" and f["severity"] == "high" and f["requires_human_review"] is True
    (ev,) = f["evidence"]
    assert ev["role"] == "conflicts" and ev["fact_id"] == battery["id"] and ev["source_page"] == 2 and ev["source_document_id"] == pdf_doc["id"]
    assert "24 hours" in f["explanation"] and "18 hours" in f["explanation"]


def test_p2_15_and_22_unsupported_comparative_has_no_citation(client, brand, battery):
    f = one(run_on(client, brand["id"], "Nova is the fastest laptop on the market."), "fastest")
    assert f["status"] == "unsupported" and f["severity"] == "high" and f["evidence"] == [] and f["matched_fact_id"] is None
    assert "No suitable approved evidence" in f["explanation"] and "does not mean the claim is false" in f["explanation"]
    assert sql("SELECT count(*) FROM finding_evidence WHERE finding_id = :i", i=f["id"])[0][0] == 0


def test_p2_16_expired_fact_is_outdated_not_current_evidence(client, brand):
    legacy = make_fact(client, brand["id"], name="Legacy battery claim", value="Up to 14 hours", category="approved_claim", qualifications=None)
    assert one(run_on(client, brand["id"], "Battery life is up to 14 hours."), "14 hours")["status"] == "supported"
    set_status(client, legacy["id"], "expired")
    f = one(run_on(client, brand["id"], "Battery life is up to 14 hours."), "14 hours")
    assert f["status"] == "outdated" and f["evidence"][0]["role"] == "outdated"
    assert f["evidence"][0]["fact_id"] == legacy["id"] and f["evidence"][0]["fact_effective_state"] == "expired"


def test_p2_16b_fact_expired_by_date_is_outdated(client, brand, monkeypatch):
    make_fact(client, brand["id"], name="Launch price", value="From 999 USD", category="pricing", qualifications=None)
    from app.core import clock

    monkeypatch.setattr(clock, "today", lambda: __import__("datetime").date(2027, 11, 1))  # past the fact's expiry
    f = one(run_on(client, brand["id"], "The launch price is 999 USD."), "999")
    assert f["status"] == "outdated" and f["evidence"][0]["fact_effective_state"] == "expired"


def test_p2_16c_outdated_claim_points_to_the_current_fact(client, brand, battery):
    legacy = make_fact(client, brand["id"], name="Legacy battery claim", value="Up to 14 hours", category="approved_claim", qualifications=None)
    set_status(client, legacy["id"], "expired")
    f = one(run_on(client, brand["id"], "Battery life is up to 14 hours under specified test conditions."), "14 hours")
    assert f["status"] == "outdated"
    assert {(e["role"], e["fact_id"]) for e in f["evidence"]} == {("outdated", legacy["id"]), ("context", battery["id"])}


def test_p2_17_proposed_fact_is_not_current_evidence(client, brand):
    make_fact(client, brand["id"], status="proposed")
    f = one(run_on(client, brand["id"], QUALIFIED), "Battery")
    assert f["status"] == "unsupported" and f["evidence"] == []
    assert "has not been approved" in f["explanation"]


def test_p2_17b_rejected_and_retired_facts_do_not_support(client, brand):
    rejected = make_fact(client, brand["id"], status="proposed")
    set_status(client, rejected["id"], "rejected")
    assert one(run_on(client, brand["id"], QUALIFIED), "Battery")["status"] == "unsupported"
    live = make_fact(client, brand["id"], name="Battery life ", value="Up to 18 hours")
    assert one(run_on(client, brand["id"], QUALIFIED), "Battery")["status"] == "supported"
    set_status(client, live["id"], "retired")
    assert one(run_on(client, brand["id"], QUALIFIED), "Battery")["status"] == "outdated"


def test_p2_18_other_brands_fact_is_never_used(client, brand, other_brand):
    make_fact(client, other_brand["id"])
    f = one(run_on(client, brand["id"], QUALIFIED), "Battery")
    assert f["status"] == "unsupported" and f["evidence"] == []
    # ...and the other brand's own review does use it.
    assert one(run_on(client, other_brand["id"], QUALIFIED), "Battery")["status"] == "supported"


def test_p2_19_omitted_qualification_is_not_automatically_supported(client, brand, battery):
    f = one(run_on(client, brand["id"], "Battery life is up to 18 hours."), "Battery")
    assert f["status"] == "uncertain" and f["requires_human_review"] is True
    assert "specified test conditions" in f["explanation"] and f["evidence"][0]["role"] == "context"
    assert "specified test conditions" in f["recommended_action"]


def test_p2_19b_broader_than_approved_wording(client, brand, battery):
    always = one(run_on(client, brand["id"], "Battery life is always 18 hours under specified test conditions."), "always")
    assert always["status"] == "conflicting" and "maximum" in always["explanation"]
    dropped = one(run_on(client, brand["id"], "Battery life is 18 hours under specified test conditions."), "18 hours")
    assert dropped["status"] == "uncertain" and "up to" in dropped["explanation"].lower()


def test_p2_20_ambiguous_evidence_is_uncertain_and_needs_review(client, brand, battery):
    lower = one(run_on(client, brand["id"], "Battery life is up to 16 hours under specified test conditions."), "16 hours")
    assert lower["status"] == "uncertain" and lower["requires_human_review"] is True
    units = one(run_on(client, brand["id"], "Battery life is 18 percent better under specified test conditions."), "percent")
    assert units["status"] == "uncertain" and "same unit" in units["explanation"]
    real_world = one(run_on(client, brand["id"], "Battery life is up to 18 hours in real-world use under specified test conditions."), "real-world")
    assert real_world["status"] == "uncertain" and "real-world" in real_world["explanation"]


CARRY = "Nova is easy to carry anywhere."


def portability(client, brand_id):
    return make_fact(client, brand_id, name="Portability", value="Easy to carry", category="approved_claim", qualifications=None)


@pytest.mark.parametrize("which", ["nonexistent", "other_brand", "malformed"])
def test_p2_23_model_cannot_cite_records_that_do_not_exist_or_belong_elsewhere(client, brand, other_brand, use_provider, which):
    portability(client, brand["id"])
    foreign = make_fact(client, other_brand["id"], name="Portability", value="Easy to carry", category="approved_claim", qualifications=None)
    fake_id = {"nonexistent": str(uuid.uuid4()), "other_brand": foreign["id"], "malformed": "not-a-uuid"}[which]
    provider = use_provider(FakeProvider(
        extract=claims_json(CARRY),
        interpret=lambda user: '{"assessments":[{"fact_id":"%s","relation":"supports","reason":"x"}]}' % fake_id,
    ))
    run = run_on(client, brand["id"], CARRY)
    f = one(run, "carry")
    assert any("fact_id=" in c[1] for c in provider.calls), "the model was asked about the claim"
    assert run["status"] == "completed" and f["extraction_method"] == "ai"
    assert f["status"] == "unsupported" and f["evidence"] == [] and f["matched_fact_id"] is None
    assert any("Discarded 1 model assessment" in n for n in run["notes"])
    assert sql("SELECT count(*) FROM finding_evidence")[0][0] == 0


def test_p2_23b_valid_model_support_is_accepted_but_flagged_for_a_person(client, brand, use_provider):
    fact = portability(client, brand["id"])
    use_provider(FakeProvider(extract=claims_json(CARRY), interpret=assessments_for("supports")))
    f = one(run_on(client, brand["id"], CARRY), "carry")
    assert f["status"] == "supported" and f["method"] == "ai_assisted" and f["requires_human_review"] is True
    assert f["evidence"][0]["fact_id"] == fact["id"] and f["evidence"][0]["role"] == "supports"


def test_p2_23c_model_support_cannot_override_a_numeric_conflict(client, brand, battery, use_provider):
    use_provider(FakeProvider(interpret=assessments_for("supports")))
    f = one(run_on(client, brand["id"], "Battery life is 24 hours under specified test conditions."), "24 hours")
    assert f["status"] == "conflicting" and f["method"] == "deterministic"


def test_p2_24_several_claims_each_keep_their_own_evidence(client, brand, pdf_doc, battery):
    perf = make_fact(client, brand["id"], name="Performance improvement", value="25", unit="%", category="approved_claim",
                     qualifications="Under the approved comparison methodology", source_note="Performance team")
    body = f"{QUALIFIED}\nBattery life is 24 hours under specified test conditions.\nNova is the fastest laptop.\nPerformance improves by 25% under the approved comparison methodology."
    run = run_on(client, brand["id"], body)
    got = {f["claim_text"][:20]: (f["status"], [e["fact_id"] for e in f["evidence"]]) for f in run["findings"]}
    assert got["Battery life is up t"] == ("supported", [battery["id"]])
    assert got["Battery life is 24 h"] == ("conflicting", [battery["id"]])
    assert got["Nova is the fastest "] == ("unsupported", [])
    assert got["Performance improves"] == ("supported", [perf["id"]])
    assert run["counts"] == {"supported": 2, "unsupported": 1, "conflicting": 1, "outdated": 0, "uncertain": 0}
    for f in run["findings"]:
        assert body[f["start_offset"]:f["end_offset"]] == f["claim_text"]


def test_terminology_rules_from_approved_facts(client, brand):
    make_fact(client, brand["id"], name="Avoided words", value="fastest, unbeatable", category="terminology", qualifications="Never use these words in claims.")
    make_fact(client, brand["id"], name="Product name", value="Nova", category="terminology", qualifications="Exact approved name.")
    run = run_on(client, brand["id"], "Nova is unbeatable. Our nova is fine.")
    term = {f["claim_text"]: f for f in run["findings"] if f["claim_category"] == "terminology"}
    assert term["unbeatable"]["status"] == "conflicting" and term["unbeatable"]["severity"] == "medium" and term["unbeatable"]["requires_human_review"]
    assert term["nova"]["severity"] == "low" and term["nova"]["requires_human_review"] is False
    assert term["unbeatable"]["evidence"][0]["role"] == "conflicts"


def test_related_source_text_is_labelled_and_never_counts_as_support(client, brand, pdf_doc):
    f = one(run_on(client, brand["id"], "Battery life is up to 18 hours under specified test conditions."), "Battery")
    assert f["status"] == "unsupported"  # the document says it, but nothing was approved as a fact
    (ev,) = f["evidence"]
    assert ev["role"] == "related_source" and ev["fact_id"] is None and ev["source_page"] == 2 and ev["excerpt_verified"] is True
    assert "not an approved fact" in ev["relation_note"]


# ================================================================== D. persistence and error handling
def test_p2_25_run_exists_and_is_running_before_analysis(client, brand, battery, monkeypatch):
    seen = {}
    original = pipeline.analyse

    def spy(db, content, provider):
        seen["rows"] = sql("SELECT status FROM review_runs WHERE content_submission_id = :c", c=str(content.id))
        return original(db, content, provider)

    monkeypatch.setattr(pipeline, "analyse", spy)
    run = run_on(client, brand["id"], QUALIFIED)
    assert seen["rows"] == [("running",)] and run["status"] == "completed_limited"


def test_p2_26_findings_are_persisted_against_the_right_run(client, brand, battery):
    draft = submit(client, brand["id"], f"{QUALIFIED} Battery life is 24 hours.")
    run = review(client, draft["id"])
    rows = sql("SELECT review_run_id, brand_id, status FROM review_findings ORDER BY claim_index")
    assert len(rows) == 2 and {str(r[0]) for r in rows} == {run["id"]} and {str(r[1]) for r in rows} == {brand["id"]}
    assert [r[2] for r in rows] == ["supported", "conflicting"]
    assert run["brand_id"] == brand["id"] and run["content_submission_id"] == draft["id"]


def test_p2_27_retrieved_review_matches_what_was_persisted(client, brand, battery):
    draft = submit(client, brand["id"], f"{QUALIFIED} Battery life is 24 hours. Nova is the fastest.")
    created = review(client, draft["id"])
    got = client.get(f"/api/reviews/{created['id']}").json()
    assert got["status"] == created["status"] and got["counts"] == created["counts"] and got["findings"] is None
    paged = client.get(f"/api/reviews/{created['id']}/findings").json()
    assert paged["total"] == len(created["findings"])
    assert [(f["id"], f["status"], f["claim_text"], f["evidence"]) for f in paged["items"]] == [(f["id"], f["status"], f["claim_text"], f["evidence"]) for f in created["findings"]]
    only = client.get(f"/api/reviews/{created['id']}/findings", params={"status": "conflicting"}).json()
    assert [f["status"] for f in only["items"]] == ["conflicting"]
    assert client.get(f"/api/reviews/{created['id']}/findings", params={"status": "bogus"}).status_code == 422
    assert client.get(f"/api/content/{draft['id']}").json()["latest_review"]["counts"]["conflicting"] == 1


def test_p2_28_a_second_review_is_a_separate_run(client, brand, battery):
    draft = submit(client, brand["id"], QUALIFIED)
    first = review(client, draft["id"])
    set_status(client, battery["id"], "retired")  # the world changes between reviews
    second = review(client, draft["id"])
    assert first["id"] != second["id"]
    assert client.get(f"/api/reviews/{first['id']}/findings").json()["items"][0]["status"] == "supported"  # old result untouched
    assert client.get(f"/api/reviews/{second['id']}/findings").json()["items"][0]["status"] == "outdated"
    runs = client.get(f"/api/content/{draft['id']}/reviews").json()
    assert [r["id"] for r in runs] == [second["id"], first["id"]]
    assert client.get(f"/api/content/{draft['id']}").json()["review_count"] == 2


def test_p2_29_provider_unavailable_is_a_failed_review_not_a_pass(client, brand, battery, use_provider):
    use_provider(FakeProvider(extract=ProviderUnavailable("The AI provider could not be reached.")))
    run = run_on(client, brand["id"], QUALIFIED)
    assert run["status"] == "failed" and run["error_code"] == "provider_unavailable" and run["completed_at"]
    assert run["findings"] == [] and run["counts"] == {s: 0 for s in run["counts"]}
    assert "could not be reached" in run["error_message"]
    assert sql("SELECT status FROM review_runs") == [("failed",)]


def test_p2_29b_failure_while_interpreting_also_fails_the_whole_review(client, brand, battery, use_provider):
    portability(client, brand["id"])
    use_provider(FakeProvider(interpret=ProviderInvalidOutput("bad"), extract=claims_json(CARRY)))
    run = run_on(client, brand["id"], CARRY)
    assert run["status"] == "failed" and run["total_findings"] == 0


def test_p2_29c_no_provider_runs_in_labelled_limited_mode(client, brand, battery):
    run = run_on(client, brand["id"], QUALIFIED)
    assert run["status"] == "completed_limited" and run["analysis_mode"] == "limited" and run["provider_name"] is None
    assert run["limitations"] and "LLM_API_KEY" in run["limitations"][0]


def test_p2_30_database_failure_during_persistence_is_not_reported_as_complete(client, brand, battery, monkeypatch):
    def boom(*args, **kwargs):
        raise OperationalError("INSERT", {}, Exception("connection lost"))

    monkeypatch.setattr(pipeline, "_persist", boom)
    r = client.post(f"/api/content/{submit(client, brand['id'], QUALIFIED)['id']}/reviews", json={})
    assert r.status_code == 503 and r.json()["error"]["code"] == "review_persistence_failed"
    assert "connection lost" not in r.text
    assert sql("SELECT status, error_code FROM review_runs") == [("failed", "persistence_failed")]
    assert sql("SELECT count(*) FROM review_findings")[0][0] == 0


def test_p2_30b_findings_and_status_are_saved_atomically(client, brand, battery, monkeypatch):
    from app.services.review import evidence

    def explode(*args, **kwargs):
        raise OperationalError("INSERT", {}, Exception("disk full"))

    monkeypatch.setattr(evidence, "build", explode)
    r = client.post(f"/api/content/{submit(client, brand['id'], QUALIFIED)['id']}/reviews", json={})
    assert r.status_code == 503
    assert sql("SELECT count(*) FROM review_findings")[0][0] == 0 and sql("SELECT status FROM review_runs") == [("failed",)]


def test_p2_31_invalid_identifiers(client, brand):
    bad = uuid.uuid4()
    for method, url in [
        ("get", "/api/content/not-a-uuid"), ("get", "/api/reviews/not-a-uuid"), ("get", "/api/reviews/not-a-uuid/findings"),
        ("post", "/api/content/not-a-uuid/reviews"), ("get", "/api/brands/not-a-uuid/content"),
    ]:
        r = getattr(client, method)(url)
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error", url
    for method, url in [
        ("get", f"/api/content/{bad}"), ("get", f"/api/reviews/{bad}"), ("get", f"/api/reviews/{bad}/findings"),
        ("post", f"/api/content/{bad}/reviews"), ("get", f"/api/content/{bad}/reviews"),
    ]:
        r = getattr(client, method)(url)
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found", url


def test_p2_32_saved_findings_survive_a_backend_restart(client, brand, battery):
    created = review(client, submit(client, brand["id"], f"{QUALIFIED} Battery life is 24 hours.")["id"])
    from app.db import session

    session._engine = None
    with TestClient(create_app()) as fresh:
        got = fresh.get(f"/api/reviews/{created['id']}/findings").json()
        assert [(f["id"], f["status"], f["evidence"]) for f in got["items"]] == [(f["id"], f["status"], f["evidence"]) for f in created["findings"]]


def test_interrupted_runs_are_marked_failed_at_startup(client, brand):
    draft = submit(client, brand["id"], QUALIFIED)
    sql("INSERT INTO review_runs (brand_id, content_submission_id, status, analysis_mode, content_hash) VALUES (:b, :c, 'running', 'limited', :h)",
        b=brand["id"], c=draft["id"], h=draft["content_hash"])
    with TestClient(create_app()):
        pass
    assert sql("SELECT status, error_code FROM review_runs") == [("failed", "interrupted")]


def test_review_does_not_modify_phase_1_data(client, brand, battery):
    before = sql("SELECT id, version, status, updated_at FROM approved_facts")
    run_on(client, brand["id"], f"{QUALIFIED} Battery life is 24 hours.")
    assert sql("SELECT id, version, status, updated_at FROM approved_facts") == before


def test_openapi_documents_the_new_endpoints(client):
    spec = client.get("/api/openapi.json").json()
    for path in ("/api/brands/{brand_id}/content", "/api/content/{content_id}", "/api/content/{content_id}/reviews", "/api/reviews/{review_id}", "/api/reviews/{review_id}/findings"):
        assert path in spec["paths"], path
    status_enum = spec["components"]["schemas"]["FindingRead"]["properties"]["status"]["enum"]
    assert set(status_enum) == {"supported", "unsupported", "conflicting", "outdated", "uncertain"}
