"""Migrations from a clean database, model/migration parity, and frontend/backend type agreement."""
import os
import re
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

import app.models  # noqa: F401
from app.db.base import Base
from app.main import app
from tests.conftest import BACKEND_DIR, alembic_config

REPO = Path(BACKEND_DIR).parent


def test_migrations_apply_to_clean_database_and_match_models():
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        command.upgrade(alembic_config(), "head")
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
            tables = set(inspect(conn).get_table_names())
        assert diff == [], diff
        assert {"brands", "source_documents", "document_sections", "approved_facts", "fact_revisions", "alembic_version",
                "content_submissions", "review_runs", "review_findings", "finding_evidence"} <= tables
        # Reapplying is a no-op, and the full downgrade/upgrade cycle works.
        command.upgrade(alembic_config(), "head")
        command.downgrade(alembic_config(), "base")
        with engine.connect() as conn:
            assert "approved_facts" not in inspect(conn).get_table_names()
        command.upgrade(alembic_config(), "head")
    finally:
        engine.dispose()


def test_expected_indexes_and_constraints_exist():
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        insp = inspect(engine)
        facts_ix = {i["name"] for i in insp.get_indexes("approved_facts")}
        assert {"ix_approved_facts_brand_status", "ix_approved_facts_brand_review_date", "ix_approved_facts_source_document_id"} <= facts_ix
        docs_ix = {i["name"] for i in insp.get_indexes("source_documents")}
        assert "uq_source_documents_live_content" in docs_ix
        checks = {c["name"] for c in insp.get_check_constraints("approved_facts")}
        assert any("status" in c for c in checks) and any("has_provenance" in c for c in checks)
        fks = {fk["name"]: fk for fk in insp.get_foreign_keys("approved_facts")}
        composite = fks["fk_approved_facts_source_same_brand"]
        assert composite["constrained_columns"] == ["source_document_id", "brand_id"]
        assert composite["options"]["ondelete"] == "RESTRICT"
    finally:
        engine.dispose()


def _ts_interface_fields(source: str, name: str) -> set[str]:
    match = re.search(rf"export interface {name}\s*(?:extends [^{{]+)?\{{(.*?)\n\}}", source, re.S)
    assert match, f"interface {name} not found in frontend/types/api.ts"
    return set(re.findall(r"^\s{2}(\w+)\??:", match.group(1), re.M))


def test_frontend_types_match_backend_schemas():
    ts = (REPO / "frontend" / "types" / "api.ts").read_text()
    schemas = app.openapi()["components"]["schemas"]
    for backend, frontend in (
        ("BrandRead", "Brand"), ("DocumentRead", "SourceDocument"), ("SectionRead", "DocumentSection"),
        ("FactRead", "Fact"), ("FactSourceRead", "FactSource"), ("FactRevisionRead", "FactRevision"),
        ("FactSummary", "FactSummary"), ("TableRead", "TableData"), ("HealthResponse", "Health"),
        ("ContentRead", "ContentItem"), ("ContentSummary", "ContentSummary"), ("ReviewRunBrief", "ReviewRunBrief"),
        ("ReviewRunRead", "ReviewRun"), ("FindingRead", "Finding"), ("EvidenceRead", "Evidence"),
        ("ImpactRead", "Impact"), ("ImpactDetail", "ImpactDetail"), ("ImpactFactBrief", "ImpactFactBrief"),
        ("ImpactContentBrief", "ImpactContentBrief"), ("ImpactRevisionRead", "ImpactRevision"),
        ("ImpactFindingRead", "ImpactFinding"), ("ImpactSummary", "ImpactSummary"),
        ("ImpactResolutionBrief", "ImpactResolutionBrief"),
        # Phase 4
        ("RevisionRead", "Revision"), ("RevisionHistory", "RevisionHistory"), ("DecisionBrief", "DecisionBrief"), ("CorrectionRead", "CorrectionRecord"),
        ("SuggestionRead", "Suggestion"), ("FindingDetail", "FindingDetail"), ("OverrideRead", "RiskOverride"), ("WorkflowEventRead", "WorkflowEvent"),
        ("BlockingFinding", "BlockingFinding"), ("Readiness", "Readiness"), ("WorkflowRead", "Workflow"),
        ("ImpactResolutionRead", "ImpactResolution"), ("ImpactHistory", "ImpactHistory"),
    ):
        expected = _ts_interface_fields(ts, frontend)
        if frontend == "ImpactDetail":  # `extends Impact`: Pydantic reports inherited fields too
            expected |= _ts_interface_fields(ts, "Impact")
        assert set(schemas[backend]["properties"]) == expected, f"{frontend} != {backend}"
    for backend, frontend in (("FactCreate", "FactCreateInput"), ("FactUpdate", "FactUpdateInput"), ("FactStatusUpdate", "FactStatusInput"), ("ContentCreate", "ContentCreateInput"),
                              ("RevisionCreate", "RevisionCreateInput"), ("CorrectionIn", "CorrectionInput"), ("DecisionCreate", "DecisionInput"), ("OverrideIn", "OverrideInput")):
        assert set(schemas[backend]["properties"]) == _ts_interface_fields(ts, frontend), f"{frontend} != {backend}"
    for enum_name, backend_schema, prop in (("FactStatus", "FactRead", "status"), ("EffectiveState", "FactRead", "effective_state"),
                                           ("FindingStatus", "FindingRead", "status"), ("Severity", "FindingRead", "severity"), ("RunStatus", "ReviewRunRead", "status"),
                                           ("EvidenceRole", "EvidenceRead", "role"),
                                           ("ImpactTrigger", "ImpactRead", "trigger_type"), ("ImpactChangeType", "ImpactRead", "change_type"),
                                           ("ImpactStatus", "ImpactRead", "status"), ("MatchBasis", "ImpactFindingRead", "match_basis"),
                                           ("WorkflowStatus", "ContentRead", "workflow_status"), ("WorkflowAction", "WorkflowEventRead", "action"),
                                           ("ActorRole", "WorkflowEventRead", "actor_role"), ("ReadinessState", "Readiness", "state"),
                                           ("CorrectionDecision", "CorrectionRead", "decision")):
        values = set(re.findall(r'"(\w+)"', re.search(rf"export type {enum_name}\s*=([^;]+);", ts).group(1)))
        prop_schema = schemas[backend_schema]["properties"][prop]
        assert values == set(prop_schema["enum"] if "enum" in prop_schema else [prop_schema["const"]]), enum_name
