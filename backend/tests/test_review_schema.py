"""Database-level guarantees for the Phase 2 tables, and migration from a populated Phase 1 schema."""
import os
import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import alembic_config, days, fact_payload
from tests.test_review import make_fact, review, submit


@pytest.fixture
def run_with_evidence(client, brand):
    make_fact(client, brand["id"])
    run = review(client, submit(client, brand["id"], "Battery life is 24 hours under specified test conditions.")["id"])
    return run, run["findings"][0]


def _exec(query, **params):
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.begin() as conn:
            conn.execute(text(query), params)
    finally:
        engine.dispose()


def test_evidence_cannot_point_at_another_brands_fact(client, brand, other_brand, run_with_evidence):
    run, finding = run_with_evidence
    foreign = make_fact(client, other_brand["id"])
    with pytest.raises(IntegrityError):
        _exec("INSERT INTO finding_evidence (brand_id, finding_id, role, fact_id) VALUES (:b, :f, 'supports', :x)", b=brand["id"], f=finding["id"], x=foreign["id"])


def test_evidence_must_reference_a_real_record(run_with_evidence, brand):
    _, finding = run_with_evidence
    with pytest.raises(IntegrityError):  # neither a fact nor a section
        _exec("INSERT INTO finding_evidence (brand_id, finding_id, role) VALUES (:b, :f, 'related_source')", b=brand["id"], f=finding["id"])
    with pytest.raises(IntegrityError):  # nonexistent fact
        _exec("INSERT INTO finding_evidence (brand_id, finding_id, role, fact_id) VALUES (:b, :f, 'supports', :x)", b=brand["id"], f=finding["id"], x=str(uuid.uuid4()))


def test_finding_must_belong_to_a_run_of_the_same_brand(client, brand, other_brand, run_with_evidence):
    run, _ = run_with_evidence
    with pytest.raises(IntegrityError):
        _exec("INSERT INTO review_findings (brand_id, review_run_id, claim_index, claim_text, claim_category, start_offset, end_offset, status, severity, explanation)"
              " VALUES (:b, :r, 99, 'x', 'general', 0, 1, 'supported', 'low', 'e')", b=other_brand["id"], r=run["id"])


def test_run_must_belong_to_content_of_the_same_brand(client, brand, other_brand):
    draft = submit(client, brand["id"], "Battery life is up to 18 hours.")
    with pytest.raises(IntegrityError):
        _exec("INSERT INTO review_runs (brand_id, content_submission_id, status, analysis_mode, content_hash) VALUES (:b, :c, 'running', 'limited', 'h')", b=other_brand["id"], c=draft["id"])


@pytest.mark.parametrize("sql_values", [
    "'bogus','low',0,5", "'supported','extreme',0,5", "'supported','low',5,5", "'supported','low',-1,5",
])
def test_finding_status_severity_and_offsets_are_constrained(run_with_evidence, brand, sql_values):
    run, _ = run_with_evidence
    with pytest.raises(IntegrityError):
        _exec(f"INSERT INTO review_findings (brand_id, review_run_id, claim_index, claim_text, claim_category, status, severity, start_offset, end_offset, explanation)"
              f" VALUES (:b, :r, 50, 'x', 'general', {sql_values}, 'e')", b=brand["id"], r=run["id"])


@pytest.mark.parametrize("values", ["'bogus','limited',NULL,NULL", "'completed','limited',now(),NULL", "'completed','full',NULL,NULL", "'failed','limited',now(),NULL"])
def test_run_status_rules(client, brand, values):
    draft = submit(client, brand["id"], "Battery life is up to 18 hours.")
    with pytest.raises(IntegrityError):
        _exec(f"INSERT INTO review_runs (brand_id, content_submission_id, content_hash, status, analysis_mode, completed_at, error_code) VALUES (:b, :c, 'h', {values})", b=brand["id"], c=draft["id"])


def test_facts_cited_by_findings_cannot_be_deleted(client, brand, run_with_evidence):
    fact_id = run_with_evidence[1]["evidence"][0]["fact_id"]
    with pytest.raises(IntegrityError):
        _exec("DELETE FROM approved_facts WHERE id = :i", i=fact_id)


def test_expected_review_indexes_exist():
    insp = inspect(create_engine(os.environ["DATABASE_URL"]))
    assert {"ix_review_runs_content_started", "ix_review_runs_brand_status"} <= {i["name"] for i in insp.get_indexes("review_runs")}
    assert {"ix_review_findings_run_status", "ix_review_findings_matched_fact"} <= {i["name"] for i in insp.get_indexes("review_findings")}
    assert "ix_finding_evidence_fact" in {i["name"] for i in insp.get_indexes("finding_evidence")}


def test_migration_0002_preserves_phase_1_data_and_is_reversible():
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        command.upgrade(alembic_config(), "0001")  # a genuine Phase 1 installation
        with engine.begin() as conn:
            brand_id = conn.execute(text("INSERT INTO brands (name) VALUES ('Phase1 Brand') RETURNING id")).scalar()
            conn.execute(text("INSERT INTO approved_facts (brand_id, name, value, status, source_note, approved_at) VALUES (:b, 'Battery life', 'Up to 18 hours', 'active', 'manual', now())"), {"b": brand_id})
        command.upgrade(alembic_config(), "head")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM approved_facts WHERE name='Battery life'")).scalar() == 1
            assert {"content_submissions", "review_runs", "review_findings", "finding_evidence"} <= set(inspect(conn).get_table_names())
        command.downgrade(alembic_config(), "0001")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM approved_facts WHERE name='Battery life'")).scalar() == 1
            assert "review_runs" not in inspect(conn).get_table_names()
        command.upgrade(alembic_config(), "head")
    finally:
        engine.dispose()


def test_seed_reset_removes_review_data_before_facts(client, brand):
    """Regression: `seed --reset` deleted facts while review evidence still referenced them (foreign-key failure)."""
    from app.db.session import get_db
    from app.scripts import seed

    make_fact(client, brand["id"])  # brand fixture is named "Nova Systems", the seeded demo brand
    review(client, submit(client, brand["id"], "Battery life is 24 hours under specified test conditions.")["id"])
    db = next(get_db())
    try:
        seed.reset(db)
    finally:
        db.close()
    assert client.get(f"/api/brands/{brand['id']}").status_code == 404
