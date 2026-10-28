# BrandPR — Round 3 Final Release

BrandPR is an evidence-backed brand compliance and claim verification platform designed for marketing, legal, and regulatory PR teams. It replaces subjective manual content reviews with an immutable, inspectable chain of evidence connecting marketing copy to approved source materials.

BrandPR implements **Phases 0 through 6** and fulfills all **three commitments promised in Round 2**:
1. **Evidence-backed claim verification (ProofGraph)**: Extracts claims, matches approved facts, classifies findings into 5 distinct categories, and presents source citations with passage highlights and human-readable reasoning.
2. **Fact-change propagation (Claim Ledger)**: Automatically traces downstream content when an approved fact is modified or expires, generating persistent impact records without rewriting history or simulating counts.
3. **Human-controlled corrections and approvals**: Provides a transparent revision lifecycle where content is corrected, re-reviewed, subjected to reviewer decisions, and resolved against open impacts with full audit preservation.

---

## Architecture & Implementation Overview

```text
brandpr/
├── README.md                  Full product documentation and judge walkthrough
├── docker-compose.yml         db (PostgreSQL 16) + backend (FastAPI) + frontend (Next.js)
├── Makefile                   Shortcuts (setup, migrate, seed, test, run)
├── backend/                   FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16
│   ├── app/
│   │   ├── main.py            Application factory, CORS, request tracing, health endpoints
│   │   ├── api/               REST routes: health, brands, documents, facts, content,
│   │   │                      reviews, impacts, workflow, guidelines, insights, campaigns
│   │   ├── core/              Configuration, errors, structured logging, mockable clock
│   │   ├── db/                Declarative base, session management, transaction wrappers
│   │   ├── models/            SQLAlchemy models (Phases 1-6)
│   │   ├── schemas/           Pydantic v2 validation contracts
│   │   ├── services/          Business logic: documents, facts, review engine, claim ledger,
│   │   │   └── review/        ProofGraph pipeline: extractor, retrieval, matcher, providers
│   │   │                      workflow engine, guideline linting, policy sandbox, campaigns
│   │   └── scripts/           seed.py (deterministic Nova Systems dataset & workflow states)
│   ├── alembic/               Migrations 0001 (Phase 1) through 0006 (Phase 6)
│   └── tests/                 Pytest test suite (303 tests) against disposable PostgreSQL
├── frontend/                  Next.js 15, React 19, TypeScript 5, Tailwind CSS
│   ├── app/                   App router: /, /knowledge, /facts, /review, /fact-changes,
│   │                          /guidelines, /sandbox, /insights, /campaigns
│   ├── components/            Modular UI: OverviewView, ReviewView, WorkflowPanel,
│   │                          FactChangesView, FactList, SourceViewer, Guidelines, Campaigns
│   ├── lib/                   API client, role context, formatting utilities
│   ├── types/api.ts           TypeScript interfaces matching backend Pydantic schemas
│   └── tests/                 Vitest component test suite (76 tests across 4 suites)
├── test-data/                 Fictional Nova Systems PDF, TXT, CSV, and invalid file samples
├── docs/                      DATA_MODEL.md, API.md, TESTING.md
└── scripts/                   Automated verification & live E2E journey scripts:
                               verify.sh, verify.ps1, e2e_live.mjs, e2e_review.mjs,
                               e2e_fact_impacts.mjs, e2e_workflow.mjs, e2e_guidelines.mjs,
                               e2e_campaigns.mjs, e2e_security.mjs
```

---

## System Requirements

- **Operating System**: Linux, macOS, or Windows 10/11
- **Node.js**: v20.x or higher (`node -v`, `npm -v`)
- **Python**: v3.11 or v3.12 (`python --version`)
- **Database**: PostgreSQL 16 (local installation or Docker)
- **Containerization (Optional)**: Docker & Docker Compose v2+

---

## Quickstart & Local Setup

### 1. Database Configuration
BrandPR requires PostgreSQL 16. In the provided environment or Docker, the database service is typically configured on port `5432` or `5433`.

```bash
# Start PostgreSQL via Docker Compose
docker compose up -d db
```

*Note on Ports*: If `5432` is occupied by a host PostgreSQL instance, `docker-compose.yml` binds container port 5432 to host port `5433`. The `.env.example` file and scripts are pre-configured to handle both.

### 2. Backend Setup
```bash
# 1. Enter backend directory and create virtual environment
cd backend
python -m venv .venv

# 2. Activate virtual environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements-dev.txt

# 4. Set environment variables
# Copy configuration template:
cp ../.env.example ../.env
# Ensure DATABASE_URL points to your running database, e.g.:
# postgresql+psycopg://brandpr:brandpr_dev_password@localhost:5433/brandpr

# 5. Run database migrations (Phases 1-6)
alembic upgrade head

# 6. Seed reproducible demonstration data
python -m app.scripts.seed

# 7. Start FastAPI server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
The backend API is now running at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/api/docs`.

### 3. Frontend Setup (New Terminal)
```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Start development server (or production build)
npm run dev
# Or for optimized production build:
# npm run build && npm run start
```
The frontend application is now accessible at `http://localhost:3000`.

---

## Seed Data Mechanism

To inspect the system immediately without manual setup, the repository includes a reproducible seed script (`backend/app/scripts/seed.py`).

Run the seed script at any time:
```bash
cd backend
.venv/bin/python -m app.scripts.seed --reset
# On Windows:
.\.venv\Scripts\python.exe -m app.scripts.seed --reset
```

### What is Seeded for "Nova Systems"
1. **Source Documents**:
   - `specs_sheet_2025.txt`: Technical specifications for the Nova Pro device (Page-level text extracted, verified).
   - `press_release_q1.txt`: Official company milestones and pricing guidelines.
2. **Approved Fact Base**:
   - 8 active approved facts covering Battery Life, Processing Speed, Display Resolution, Pricing, and Operating Limits.
   - Each fact is linked to a source document excerpt and citation.
3. **Fact-Change Impact State (Commitment 2)**:
   - "Nova Product Brochure": Contains marketing copy evaluated against Battery Life v1 (36 hours).
   - The seed script materially updates Battery Life to v2 (30 hours), creating an active, real **`needs_review` impact record** ready for inspection on `/fact-changes`.
4. **Content Revision & Approval Workflow State (Commitment 3)**:
   - "Nova Launch Campaign":
     - **Revision 1**: Contains an unapproved comparative claim. Reviewed and transitioned to `changes_requested` by reviewer Alex Compliance with documented feedback.
     - **Revision 2**: Corrected copy removing the unapproved claim. Re-reviewed cleanly (`supported`) and transitioned to `approved` by Alex Compliance.

---

## Verifying the Test Suite

BrandPR maintains a strict, zero-defect verification standard.

> **CRITICAL SAFETY NOTE**: Automated backend tests run against a **disposable test database** specified by `TEST_DATABASE_URL` (default: `postgresql+psycopg://brandpr:brandpr_dev_password@localhost:5433/brandpr_test`). The test runner recreates the database schema on each run. **Never point `TEST_DATABASE_URL` at production data or your primary seed database.**

### Run Tests Directly
```bash
# Run backend pytest suite directly against disposable test DB:
cd backend && pytest
# Or:
python -m pytest

# Run frontend tests and typecheck:
cd frontend && npm run typecheck && npm test
```

### Run Full Verification Script
We provide one-command verification scripts that run backend unit/integration tests, frontend TypeScript typechecking, frontend Vitest component tests, and a production build:

**On Linux / macOS:**
```bash
./scripts/verify.sh
```

**On Windows (PowerShell):**
```powershell
.\scripts\verify.ps1
```

### Run Live End-to-End Test Journeys
With backend (port 8000) and frontend (port 3000) running:
```bash
node scripts/e2e_live.mjs           # Basic live health & proxy checks (18/18 PASS)
node scripts/e2e_review.mjs         # ProofGraph claim verification journey (17/17 PASS)
node scripts/e2e_fact_impacts.mjs   # Claim Ledger fact-change propagation (19/19 PASS)
node scripts/e2e_workflow.mjs       # Revisions, review decisions, impact resolution (24/24 PASS)
node scripts/e2e_guidelines.mjs     # Guideline linting and policy sandbox (23/23 PASS)
node scripts/e2e_campaigns.mjs      # Campaign consistency and release readiness (19/19 PASS)
node scripts/e2e_security.mjs       # Production security and JWT authorization (8/8 PASS)
```

---

## The Three Round 2 Commitments: Walkthrough for Judges

BrandPR's root URL (`http://localhost:3000/`) loads the **Overview & Judge Guide**, which explains each workflow and provides direct navigation.

### COMMITMENT 1: Evidence-Backed Claim Verification (ProofGraph)
**Navigation**: Open **Review Content** (`/review`).

**Judge Walkthrough**:
1. Click **"Load sample marketing copy"** in the submission form (or enter your own copy with numbers, superlatives, and claims).
2. Click **"Review content"**. The system saves Revision 1 and executes the ProofGraph pipeline:
   - **Claim Extraction**: Isolates specific factual statements, numerical specs, and comparative statements.
   - **Approved Fact Retrieval**: Matches claims against active, approved facts belonging to the brand.
   - **Evidence Classification**: Assigns one of 5 distinct categories:
     - `supported`: Approved fact corroborates the claim within stated tolerances.
     - `conflicting`: Claim contradicts approved fact value or units.
     - `outdated`: Claim cites a fact whose validity window has expired.
     - `unsupported`: No approved fact corroborates the claim (clearly distinguished from false).
     - `uncertain`: Ambiguous conditions or non-standard units requiring human assessment.
3. **Inspect Findings**:
   - Click any highlighted claim in the text to focus its finding.
   - View the cited fact, current approved value, source document name, page number, and exact highlighted passage.
   - Notice the plain-English explanation generated for non-technical compliance reviewers.

### COMMITMENT 2: Fact-Change Propagation (Claim Ledger)
**Navigation**: Open **Fact Changes** (`/fact-changes`).

**Judge Walkthrough**:
1. Select the **Nova Systems** brand. You will see the pre-seeded open impact for **"Nova Product Brochure"**.
2. Click **"Inspect impact"**:
   - The ledger displays side-by-side comparison:
     - Historical value relied upon when content was reviewed: `36 hours (Battery Life v1)`.
     - Live approved fact value now in force: `30 hours (Battery Life v2)`.
   - The audit log details who changed the fact, when, and the change rationale.
3. **Test Live Propagation**:
   - Open **Approved Facts** (`/facts`).
   - Edit an approved fact materially (e.g. change "Nova Pro Base Price" from `$999` to `$1,099`).
   - Return to `/fact-changes`. An impact record has been automatically generated in the same transaction for all content that cited the earlier price.
   - Metadata-only edits (e.g. updating internal review reminders) do **not** trigger false impacts.
   - Expiry dates past today are detected via the on-demand sweep without relying on fragile background cron jobs.

### COMMITMENT 3: Human-Controlled Corrections & Approvals
**Navigation**: Open **Review Content** (`/review`) and select an asset with open findings.

**Judge Walkthrough**:
1. Notice the revision selector showing the history of drafts and revisions.
2. Click **"Create corrected revision"**. The current revision is frozen as an immutable historical record; Revision 2 is initialized in `draft` status.
3. Edit the problematic claim in the editor to align with the approved fact.
4. Click **"Review content"** to verify the corrected revision.
5. In the **Workflow & Approvals** panel:
   - Switch your demo role to **Reviewer** using the 1-click role switcher in the panel header.
   - Click **"Submit for approval"** (creator action) then **"Approve"** (reviewer action).
   - Enter compliance notes. The reviewer's identity and timestamp are cryptographically committed to the audit ledger.
6. Return to **Fact Changes** (`/fact-changes`):
   - With an approved, non-conflicting Revision 2, the reviewer can click **"Resolve Impact"** and bind the resolution to Revision 2.
   - The impact status transitions to `resolved`. The resolution is permanent, auditable, and immutable.

---

## Supporting Phases 5 & 6

- **Guideline Linting (`/guidelines`)**: Deterministic lint engine identifies ambiguous guidance, missing conditional thresholds, and conflicting cross-guideline directives before content is created.
- **Policy Sandbox (`/sandbox`)**: Replay proposed rule changes across historical content submissions to observe approval impact without mutating historical review runs.
- **Campaign Intelligence (`/campaigns`)**: Evaluate multi-channel campaign portfolios (e.g. Landing Page + Ad Copy + Press Release) for cross-asset contradictions and enforce an automated, evidence-backed release-readiness gate.

---

## Disclosed Limitations & Boundary Conditions

1. **AI Provider Fallback Mode**:
   - When `LLM_API_KEY` is not provided, BrandPR operates in **Heuristic Fallback Mode** (`completed_limited`). It relies on deterministic regex, unit converters, and token similarity algorithms. It will flag complex stylistic paraphrases as `uncertain` rather than guessing or hallucinating facts.
2. **Demo Role Headers vs. Production Auth**:
   - In local development mode (`APP_ENV=development`), user identities are supplied via `X-Actor-Name` and `X-Actor-Role` headers with 1-click UI switchers. In production deployments (`APP_ENV=production`), caller-asserted headers are strictly rejected in favor of verified HMAC-SHA256 JWT bearer tokens.
3. **Database Concurrency in Sandbox**:
   - PostgreSQL runs outside isolated network sandboxes. When executing CLI commands or tests, ensure the PostgreSQL port (default 5433 or 5432) is accessible.
4. **Document Archival vs. Deletion**:
   - Documents cited by approved facts or active guideline rules cannot be deleted from storage; they must be archived to preserve the legal chain of custody.
