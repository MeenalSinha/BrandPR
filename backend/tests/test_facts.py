"""Phase 1 tests: brands and approved facts (P1-01 .. P1-10, P1-19 .. P1-24 and lifecycle rules)."""
import uuid

from sqlalchemy import create_engine, text

from tests.conftest import days, fact_payload, upload

NIL = "00000000-0000-0000-0000-000000000000"


def make_fact(client, brand_id, **kw):
    r = client.post(f"/api/brands/{brand_id}/facts", json=fact_payload(**kw))
    assert r.status_code == 201, r.text
    return r.json()


def test_p1_01_create_brand_persists_with_id(client):
    r = client.post("/api/brands", json={"name": "  Nova Systems  ", "description": "  Fictional  "})
    assert r.status_code == 201
    b = r.json()
    uuid.UUID(b["id"])
    assert b["name"] == "Nova Systems" and b["description"] == "Fictional" and b["created_at"]
    assert client.get(f"/api/brands/{b['id']}").json()["id"] == b["id"]
    dup = client.post("/api/brands", json={"name": "nova systems"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate_brand"


def test_p1_02_create_fact_and_retrieve(client, brand):
    f = make_fact(client, brand["id"], unit="hours", valid_from="2026-09-01", review_date="2026-12-01", expires_at="2027-01-01")
    got = client.get(f"/api/facts/{f['id']}").json()
    for key in ("name", "value", "category", "qualifications", "unit", "owner", "valid_from", "review_date", "expires_at"):
        assert got[key] == f[key]
    assert got["name"] == "Battery life" and got["status"] == "proposed" and got["version"] == 1
    assert got["provenance"] == "manual" and got["source"] is None and got["created_at"] and got["updated_at"]


def test_p1_03_edit_fact_persists_after_reload(client, brand):
    f = make_fact(client, brand["id"])
    r = client.patch(f"/api/facts/{f['id']}", json={"value": "Up to 20 hours", "change_reason": "Spec revision"})
    assert r.status_code == 200 and r.json()["value"] == "Up to 20 hours" and r.json()["version"] == 2
    # A brand-new application instance (fresh engine and app) must see the same data.
    from fastapi.testclient import TestClient
    from app.db import session
    from app.main import create_app

    session._engine = None
    with TestClient(create_app()) as fresh:
        assert fresh.get(f"/api/facts/{f['id']}").json()["value"] == "Up to 20 hours"
        assert fresh.get(f"/api/brands/{brand['id']}/facts").json()["total"] == 1


def test_p1_04_list_only_returns_selected_brand(client, brand, other_brand):
    make_fact(client, brand["id"], name="A")
    make_fact(client, brand["id"], name="B")
    make_fact(client, other_brand["id"], name="C")
    r = client.get(f"/api/brands/{brand['id']}/facts").json()
    assert r["total"] == 2 and {i["name"] for i in r["items"]} == {"A", "B"}
    assert all(i["brand_id"] == brand["id"] for i in r["items"])
    assert client.get(f"/api/brands/{NIL}/facts").status_code == 404
    page = client.get(f"/api/brands/{brand['id']}/facts?limit=1&offset=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1 and page["limit"] == 1 and page["offset"] == 1


def test_p1_05_nonexistent_source_rejected_without_orphan(client, brand):
    r = client.post(f"/api/brands/{brand['id']}/facts", json=fact_payload(source_document_id=NIL))
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["field"] == "source_document_id"
    assert client.get(f"/api/brands/{brand['id']}/facts").json()["total"] == 0


def test_p1_06_cross_brand_source_rejected_by_api_and_database(client, brand, other_brand, pdf_doc):
    r = client.post(f"/api/brands/{other_brand['id']}/facts", json=fact_payload(source_document_id=pdf_doc["id"], source_note=None))
    assert r.status_code == 422 and "different brand" in r.json()["error"]["details"][0]["message"]
    assert client.get(f"/api/brands/{other_brand['id']}/facts").json()["total"] == 0
    # Defence in depth: bypass the API and the composite foreign key still refuses it.
    import os
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.begin() as conn:
            try:
                conn.execute(text(
                    "INSERT INTO approved_facts (brand_id, name, value, source_document_id) "
                    "VALUES (:b, 'x', 'y', :d)"), {"b": other_brand["id"], "d": pdf_doc["id"]})
                raised = False
            except Exception:
                raised = True
        assert raised
    finally:
        engine.dispose()


def test_p1_07_mark_fact_expired_and_persist(client, brand):
    f = make_fact(client, brand["id"], expires_at="2999-01-01")
    client.patch(f"/api/facts/{f['id']}/status", json={"status": "active", "actor": "alice"})
    r = client.patch(f"/api/facts/{f['id']}/status", json={"status": "expired", "actor": "alice", "reason": "Superseded"})
    assert r.status_code == 200 and r.json()["status"] == "expired" and r.json()["effective_state"] == "expired"
    assert client.get(f"/api/facts/{f['id']}").json()["status"] == "expired"
    no_reason = client.patch(f"/api/facts/{f['id']}/status", json={"status": "retired"})
    assert no_reason.status_code == 422 and no_reason.json()["error"]["details"][0]["field"] == "reason"


def test_p1_08_filter_by_status_category_and_search(client, brand):
    a = make_fact(client, brand["id"], name="Alpha", value="One", category="product_spec")
    b = make_fact(client, brand["id"], name="Beta", value="Two", category="terminology")
    client.patch(f"/api/facts/{a['id']}/status", json={"status": "active", "actor": "alice"})
    base = f"/api/brands/{brand['id']}/facts"
    assert [i["name"] for i in client.get(base + "?status=active").json()["items"]] == ["Alpha"]
    assert [i["name"] for i in client.get(base + "?status=proposed").json()["items"]] == ["Beta"]
    assert [i["name"] for i in client.get(base + "?category=terminology").json()["items"]] == ["Beta"]
    assert [i["name"] for i in client.get(base + "?q=alph").json()["items"]] == ["Alpha"]
    assert client.get(base + "?q=%25").json()["total"] == 0  # wildcard characters are escaped
    assert client.get(base + "?status=bogus").status_code == 422
    assert b["status"] == "proposed"


def test_p1_09_review_date_rules(client, brand, fixed_today):
    for name, review in (("overdue", days(-5)), ("today", days(0)), ("soon", days(30)), ("later", days(31)), ("none", None)):
        make_fact(client, brand["id"], name=name, review_date=review)
    base = f"/api/brands/{brand['id']}/facts"
    names = lambda qs: sorted(i["name"] for i in client.get(base + qs).json()["items"])  # noqa: E731
    assert names("?review_state=overdue") == ["overdue"]
    assert names("?review_state=due_soon") == ["soon", "today"]
    assert names("?review_state=scheduled") == ["later"]
    assert names("?review_state=unscheduled") == ["none"]
    assert names("?review_within_days=30") == ["overdue", "soon", "today"]
    summary = client.get(base + "/summary").json()
    assert summary["by_review_state"] == {"overdue": 1, "due_soon": 2, "scheduled": 1, "unscheduled": 1, "not_applicable": 0}
    states = {i["name"]: i["review_state"] for i in client.get(base + "?limit=50").json()["items"]}
    assert states["overdue"] == "overdue" and states["soon"] == "due_soon"


def test_p1_10_referenced_document_policy(client, brand, pdf_doc):
    f = make_fact(client, brand["id"], source_note=None, source_document_id=pdf_doc["id"], source_page=2,
                  source_excerpt="Battery life: up to 18 hours")
    delete = client.delete(f"/api/documents/{pdf_doc['id']}")
    assert delete.status_code == 409 and delete.json()["error"]["code"] == "document_in_use"
    assert client.get(f"/api/documents/{pdf_doc['id']}").status_code == 200
    archived = client.post(f"/api/documents/{pdf_doc['id']}/archive").json()
    assert archived["archived_at"] and archived["fact_count"] == 1
    got = client.get(f"/api/facts/{f['id']}").json()
    assert got["source"]["archived"] is True and "source_document_archived" in got["warnings"]
    again = client.post(f"/api/brands/{brand['id']}/facts", json=fact_payload(source_note=None, source_document_id=pdf_doc["id"]))
    assert again.status_code == 422 and "archived" in again.json()["error"]["details"][0]["message"]
    hidden = client.get(f"/api/brands/{brand['id']}/documents").json()
    assert hidden["total"] == 0
    assert client.get(f"/api/brands/{brand['id']}/documents?include_archived=true").json()["total"] == 1


def test_p1_19_associate_fact_with_uploaded_source(client, brand, pdf_doc):
    f = make_fact(client, brand["id"], source_note=None, source_document_id=pdf_doc["id"], source_page=2,
                  source_excerpt="Battery life: up to 18 hours")
    assert f["source_document_id"] == pdf_doc["id"] and f["provenance"] == "document"
    # Associate an existing manual fact afterwards.
    m = make_fact(client, brand["id"], name="Manual")
    r = client.patch(f"/api/facts/{m['id']}", json={"source_document_id": pdf_doc["id"], "source_page": 1})
    assert r.status_code == 200 and r.json()["source_document_id"] == pdf_doc["id"]


def test_p1_20_inspect_fact_source(client, brand, pdf_doc):
    f = make_fact(client, brand["id"], source_note=None, source_document_id=pdf_doc["id"], source_page=2,
                  source_excerpt="Battery life: up to 18 hours")
    src = client.get(f"/api/facts/{f['id']}").json()
    assert src["source"]["title"] == "Spec" and src["source"]["filename"] == "spec.pdf" and src["source"]["page_count"] == 3
    assert src["source_excerpt"] == "Battery life: up to 18 hours" and src["source_excerpt_verified"] is True
    wrong = make_fact(client, brand["id"], name="Wrong", source_note=None, source_document_id=pdf_doc["id"], source_page=1,
                      source_excerpt="Battery life: up to 99 hours")
    assert wrong["source_excerpt_verified"] is False and "excerpt_not_found_in_source" in wrong["warnings"]


def test_p1_21_pdf_source_page_must_exist(client, brand, pdf_doc):
    r = client.post(f"/api/brands/{brand['id']}/facts", json=fact_payload(source_note=None, source_document_id=pdf_doc["id"], source_page=9))
    assert r.status_code == 422 and "does not exist" in r.json()["error"]["details"][0]["message"]
    pages = client.get(f"/api/documents/{pdf_doc['id']}/sections?page_number=2").json()
    assert pages["total"] == 1 and "Battery life" in pages["items"][0]["text"]


def test_p1_22_manual_fact_requires_explicit_provenance(client, brand):
    bad = client.post(f"/api/brands/{brand['id']}/facts", json=fact_payload(source_note=None))
    assert bad.status_code == 422 and bad.json()["error"]["details"][0]["field"] == "source_note"
    ok = make_fact(client, brand["id"])
    assert ok["provenance"] == "manual" and ok["source_note"] == "Confirmed by the product team"
    page_without_doc = client.post(f"/api/brands/{brand['id']}/facts", json=fact_payload(source_page=3))
    assert page_without_doc.status_code == 422


def test_p1_23_invalid_fact_data_rejected_and_not_persisted(client, brand):
    base = f"/api/brands/{brand['id']}/facts"
    cases = [
        {"name": "", "value": "x"}, {"name": "x", "value": "   "}, fact_payload(category="nonsense"),
        fact_payload(status="expired"), fact_payload(valid_from="2026-12-01", expires_at="2026-11-01"),
        fact_payload(review_date="2027-02-01", expires_at="2027-01-01"), fact_payload(source_page=0),
        fact_payload(expires_at="not-a-date"), fact_payload(unknown_field=1),
    ]
    for body in cases:
        r = client.post(base, json=body)
        assert r.status_code == 422, (body, r.text)
        assert r.json()["error"]["code"] == "validation_error"
    assert client.get(base).json()["total"] == 0


def test_p1_24_statuses_persist_across_listing(client, brand):
    f = make_fact(client, brand["id"], expires_at="2999-01-01")
    client.patch(f"/api/facts/{f['id']}/status", json={"status": "active", "actor": "alice"})
    items = client.get(f"/api/brands/{brand['id']}/facts").json()["items"]
    assert items[0]["status"] == "active" and items[0]["approved_by"] == "alice" and items[0]["approved_at"]


# ---- lifecycle, honesty of approval, history, dates --------------------------------------------
def test_new_facts_are_proposed_and_not_current(client, brand):
    f = make_fact(client, brand["id"])
    assert f["status"] == "proposed" and f["effective_state"] == "unapproved" and f["approved_at"] is None


def test_creating_as_active_is_an_explicit_approval(client, brand):
    f = make_fact(client, brand["id"], status="active", actor="bob", expires_at="2999-01-01")
    assert f["status"] == "active" and f["approved_by"] == "bob" and f["approved_at"] and f["effective_state"] == "current"


def test_editing_material_field_of_active_fact_requires_reapproval(client, brand):
    f = make_fact(client, brand["id"], status="active", actor="bob", expires_at="2999-01-01")
    owner = client.patch(f"/api/facts/{f['id']}", json={"owner": "New owner"}).json()
    assert owner["status"] == "active"
    changed = client.patch(f"/api/facts/{f['id']}", json={"value": "Up to 19 hours"}).json()
    assert changed["status"] == "proposed" and changed["approved_at"] is None and changed["effective_state"] == "unapproved"
    revs = client.get(f"/api/facts/{f['id']}/revisions").json()
    assert [r["action"] for r in revs] == ["created", "updated", "updated"]
    assert revs[-1]["changes"]["value"] == {"old": "Up to 18 hours", "new": "Up to 19 hours"}
    assert revs[-1]["changes"]["status"] == {"old": "active", "new": "proposed"}
    assert revs[0]["snapshot"]["value"] == "Up to 18 hours"  # history is never overwritten


def test_status_transitions_are_enforced(client, brand):
    f = make_fact(client, brand["id"], expires_at="2999-01-01")
    bad = client.patch(f"/api/facts/{f['id']}/status", json={"status": "expired", "reason": "x"})
    assert bad.status_code == 422
    client.patch(f"/api/facts/{f['id']}/status", json={"status": "rejected", "reason": "Wrong value"})
    assert client.patch(f"/api/facts/{f['id']}/status", json={"status": "active"}).status_code == 422
    back = client.patch(f"/api/facts/{f['id']}/status", json={"status": "proposed"})
    assert back.status_code == 200 and back.json()["status"] == "proposed"


def test_expired_by_date_is_never_current(client, brand, fixed_today):
    f = make_fact(client, brand["id"], expires_at=days(-1))
    r = client.patch(f"/api/facts/{f['id']}/status", json={"status": "active"})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "expires_at"
    ok = make_fact(client, brand["id"], name="Lapsing", expires_at=days(2), status="active", actor="a")
    assert ok["effective_state"] == "current"
    lapsed = client.patch(f"/api/facts/{ok['id']}", json={"expires_at": days(-1)}).json()
    assert lapsed["status"] == "active" and lapsed["effective_state"] == "expired" and "expired_by_date" in lapsed["warnings"]
    base = f"/api/brands/{brand['id']}/facts"
    assert [i["name"] for i in client.get(base + "?effective_state=expired").json()["items"]] == ["Lapsing"]
    assert client.get(base + "?effective_state=current").json()["total"] == 0


def test_expiry_boundary_is_inclusive(client, brand, fixed_today):
    f = make_fact(client, brand["id"], expires_at=days(0), status="active", actor="a")
    assert f["effective_state"] == "current"


def test_missing_expiry_is_flagged_not_assumed_forever(client, brand):
    f = make_fact(client, brand["id"], status="active", actor="a")
    assert "no_expiry_date" in f["warnings"] and f["review_state"] == "unscheduled"


def test_future_valid_from_is_pending(client, brand, fixed_today):
    f = make_fact(client, brand["id"], status="active", actor="a", valid_from=days(10))
    assert f["effective_state"] == "pending"
    assert client.get(f"/api/brands/{brand['id']}/facts?effective_state=current").json()["total"] == 0


def test_optimistic_concurrency(client, brand):
    f = make_fact(client, brand["id"])
    ok = client.patch(f"/api/facts/{f['id']}", json={"owner": "A", "expected_version": 1})
    assert ok.status_code == 200
    stale = client.patch(f"/api/facts/{f['id']}", json={"owner": "B", "expected_version": 1})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "version_conflict"


def test_noop_edit_creates_no_revision(client, brand):
    f = make_fact(client, brand["id"])
    client.patch(f"/api/facts/{f['id']}", json={"value": f["value"]})
    assert len(client.get(f"/api/facts/{f['id']}/revisions").json()) == 1


def test_failed_validation_rolls_back_atomically(client, brand):
    f = make_fact(client, brand["id"])
    r = client.patch(f"/api/facts/{f['id']}", json={"value": "Changed", "source_document_id": NIL})
    assert r.status_code == 422
    unchanged = client.get(f"/api/facts/{f['id']}").json()
    assert unchanged["value"] == "Up to 18 hours" and unchanged["version"] == 1
    assert len(client.get(f"/api/facts/{f['id']}/revisions").json()) == 1


def test_database_check_constraints_back_up_the_api(client, brand):
    import os
    engine = create_engine(os.environ["DATABASE_URL"])
    stmts = [
        "INSERT INTO approved_facts (brand_id, name, value) VALUES (:b, 'x', 'y')",  # no provenance
        "INSERT INTO approved_facts (brand_id, name, value, source_note, status) VALUES (:b, 'x', 'y', 'n', 'weird')",
        "INSERT INTO approved_facts (brand_id, name, value, source_note, status) VALUES (:b, 'x', 'y', 'n', 'active')",
        "INSERT INTO approved_facts (brand_id, name, value, source_note, valid_from, expires_at) VALUES (:b, 'x', 'y', 'n', '2026-02-01', '2026-01-01')",
    ]
    try:
        for stmt in stmts:
            with engine.connect() as conn:
                try:
                    conn.execute(text(stmt), {"b": brand["id"]})
                    conn.commit()
                    raise AssertionError(f"database accepted: {stmt}")
                except AssertionError:
                    raise
                except Exception:
                    conn.rollback()
    finally:
        engine.dispose()


def test_summary_counts(client, brand, fixed_today):
    make_fact(client, brand["id"], name="a", status="active", actor="x", expires_at=days(40), review_date=days(10))
    make_fact(client, brand["id"], name="b")
    s = client.get(f"/api/brands/{brand['id']}/facts/summary").json()
    assert s["total"] == 2 and s["by_effective_state"]["current"] == 1 and s["by_effective_state"]["unapproved"] == 1
    assert s["review_warning_days"] == 30


def test_unrelated_edit_still_works_after_source_is_archived(client, brand, pdf_doc):
    f = make_fact(client, brand["id"], source_note=None, source_document_id=pdf_doc["id"], source_page=2,
                  source_excerpt="Battery life: up to 18 hours")
    client.post(f"/api/documents/{pdf_doc['id']}/archive")
    r = client.patch(f"/api/facts/{f['id']}", json={"owner": "Someone else"})
    assert r.status_code == 200 and r.json()["owner"] == "Someone else" and r.json()["source_excerpt_verified"] is True
    swap = client.patch(f"/api/facts/{f['id']}", json={"source_page": 3})
    assert swap.status_code == 422  # changing the citation re-validates against the archived document
