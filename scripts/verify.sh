#!/usr/bin/env bash
# Runs every automated check. Requires PostgreSQL reachable at TEST_DATABASE_URL (a database named brandpr_test).
set -euo pipefail
cd "$(dirname "$0")/.."
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+psycopg://brandpr:brandpr_dev_password@localhost:5433/brandpr_test}"
echo "== backend tests"; (cd backend && ${PYTHON:-.venv/bin/python} -m pytest)
echo "== frontend typecheck and tests"; (cd frontend && npm run typecheck && npm test)
echo "== frontend production build"; (cd frontend && BACKEND_URL=http://localhost:8000 npm run build)
echo "All automated checks passed. Start the backend and frontend, then run:"
echo "  node scripts/e2e_live.mjs"
echo "  node scripts/e2e_review.mjs"
echo "  node scripts/e2e_fact_impacts.mjs"
echo "  node scripts/e2e_workflow.mjs"
echo "  node scripts/e2e_guidelines.mjs"
echo "  node scripts/e2e_campaigns.mjs"
