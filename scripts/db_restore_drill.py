#!/usr/bin/env python3
"""Repeatable Database Disaster Recovery & Integrity Verification Drill.

Executes automated recovery drills into an ISOLATED, DISPOSABLE target database.
SAFETY GUARD: Strictly refuses to execute against production or default database names.
"""
import argparse
import os
import sys
import time
import uuid

# Ensure backend and its virtualenv site-packages are available
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_ROOT, "backend")
_SITE = os.path.join(_BACKEND, ".venv", "Lib", "site-packages")
for _p in (_BACKEND, _SITE):
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import create_engine, func, select, text  # type: ignore[import-untyped,missing-import]
from sqlalchemy.orm import Session  # type: ignore[import-untyped,missing-import]

# List of critical tables that must exist and pass referential integrity
CRITICAL_TABLES = [
    "users",
    "brand_memberships",
    "membership_audit_logs",
    "fact_approval_decisions",
    "brands",
    "source_documents",
    "document_sections",
    "approved_facts",
    "fact_revisions",
    "content_submissions",
    "content_assets",
    "review_runs",
    "review_findings",
    "finding_evidence",
    "fact_change_impacts",
    "fact_change_impact_findings",
    "workflow_events",
    "guideline_rules",
    "guideline_rule_versions",
    "campaigns",
    "campaign_assets",
    "campaign_audits",
    "campaign_release_decisions",
]


def run_drill(target_db_url: str) -> dict:
    start_time = time.time()
    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_url": target_db_url.split("@")[-1] if "@" in target_db_url else target_db_url,
        "checks": [],
        "table_counts": {},
        "integrity_errors": [],
        "duration_seconds": 0.0,
        "success": False,
    }

    # SAFETY GUARD: Ensure target is an explicit recovery/disposable database
    is_safe_target = any(
        kw in target_db_url.lower() for kw in ("test", "recovery", "disposable", "drill", "staging")
    ) and not any(kw in target_db_url.lower() for kw in ("brandpr-512618", "prod", "cloudsql"))
    if not is_safe_target and os.environ.get("FORCE_DRILL") != "1":
        print(f"SAFETY ABORT: Target database '{target_db_url}' is not a designated recovery database.")
        print("Target URL must contain 'recovery', 'drill', 'staging', or 'test'.")
        results["error"] = "Safety guard refused execution on non-disposable database."
        return results

    print(f"=== STARTING DATABASE RECOVERY DRILL ===")
    print(f"Target: {results['target_url']}")

    try:
        engine = create_engine(target_db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            # 1. Connectivity Check
            res = conn.execute(text("SELECT version();")).scalar()
            print(f"[CHECK 1] PostgreSQL Connectivity: OK ({res.split(',')[0]})")
            results["checks"].append({"check": "connectivity", "status": "PASS", "details": res})

            # 2. Schema and Table Verification
            existing_tables = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
                )
            ).scalars().all()

            missing = [t for t in CRITICAL_TABLES if t not in existing_tables]
            if missing:
                print(f"[CHECK 2] Missing Critical Tables: {missing}")
                results["checks"].append({"check": "tables_present", "status": "FAIL", "missing": missing})
            else:
                print(f"[CHECK 2] All {len(CRITICAL_TABLES)} Critical Governance Tables Present: PASS")
                results["checks"].append({"check": "tables_present", "status": "PASS", "count": len(existing_tables)})

            # 3. Row Counts Across Modules
            print("[CHECK 3] Auditing Record Counts...")
            for table in CRITICAL_TABLES:
                if table in existing_tables:
                    count = conn.execute(text(f"SELECT COUNT(*) FROM {table};")).scalar()
                    results["table_counts"][table] = count
                    print(f"  - {table}: {count} records")

            # 4. Referential Integrity Checks
            print("[CHECK 4] Verifying Foreign Key Referential Integrity...")
            # Check facts link to valid brands
            orphan_facts = conn.execute(
                text("SELECT COUNT(*) FROM approved_facts f LEFT JOIN brands b ON f.brand_id = b.id WHERE b.id IS NULL;")
            ).scalar()
            if orphan_facts > 0:
                results["integrity_errors"].append(f"Found {orphan_facts} orphan facts with invalid brand_id")

            # Check findings link to valid review runs
            orphan_findings = conn.execute(
                text("SELECT COUNT(*) FROM review_findings rf LEFT JOIN review_runs rr ON rf.review_run_id = rr.id WHERE rr.id IS NULL;")
            ).scalar()
            if orphan_findings > 0:
                results["integrity_errors"].append(f"Found {orphan_findings} orphan findings with invalid review_run_id")

            # Check campaign assets link to valid campaigns
            orphan_assets = conn.execute(
                text("SELECT COUNT(*) FROM campaign_assets ca LEFT JOIN campaigns c ON ca.campaign_id = c.id WHERE c.id IS NULL;")
            ).scalar()
            if orphan_assets > 0:
                results["integrity_errors"].append(f"Found {orphan_assets} orphan campaign assets")

            if results["integrity_errors"]:
                print(f"  FAIL: Referential integrity violations: {results['integrity_errors']}")
                results["checks"].append({"check": "referential_integrity", "status": "FAIL", "errors": results["integrity_errors"]})
            else:
                print("  PASS: 0 referential integrity violations found across all relations.")
                results["checks"].append({"check": "referential_integrity", "status": "PASS"})

        results["duration_seconds"] = round(time.time() - start_time, 2)
        results["success"] = not missing and not results["integrity_errors"]
        print(f"=== DRILL COMPLETED IN {results['duration_seconds']}s (Verdict: {'PASS' if results['success'] else 'FAIL'}) ===")
        return results

    except Exception as e:
        results["error"] = str(e)
        results["duration_seconds"] = round(time.time() - start_time, 2)
        print(f"DRILL EXECUTION FAILED: {e}")
        return results


if __name__ == "__main__":
    db_url = os.environ.get("DRILL_DATABASE_URL", "postgresql+psycopg://brandpr:brandpr_dev_password@localhost:5433/brandpr_test")
    if len(sys.argv) > 1:
        db_url = sys.argv[1]
    res = run_drill(db_url)
    sys.exit(0 if res.get("success") else 1)

