# BrandPR

This repository contains **Phase 0** (project setup and interface contracts), **Phase 1** (database and approved brand knowledge), **Phase 2** (claim verification and ProofGraph), **Phase 3** (Claim Ledger fact-change propagation), **Phase 4** (revision and approval workflow), **Phase 5** (guideline lint, policy sandbox, governance intelligence), and **Phase 6** (campaign intelligence, portfolio audits, and release readiness).
Phase 6 evaluates an entire collection of related marketing assets together as a campaign, detects cross-asset contradictions, outdated fact dependencies, open impacts, and workflow gaps, provides immutable audit snapshots with history comparison, and enforces a deterministic, evidence-backed release-readiness gate.

What works now: create brands, upload PDF, text and CSV source documents with page-level text extraction, manage approved facts with qualifications, validity dates, ownership, source citations, explicit approval and full change history, inspect any fact's source passage highlighted in the document, run deterministic and AI-assisted claim verification, trace and resolve fact-change impacts, manage guideline rules with deterministic linting, simulate policy revisions in a safe sandbox, view real-time governance intelligence analytics, organize assets into multi-channel campaigns, perform campaign-wide consistency audits, and evaluate release readiness with guarded sign-off.

## Folder structure

```text
brandpr/
├── README.md
├── .env.example               configuration template (copy to .env)
├── .gitignore
├── docker-compose.yml         db + backend + frontend
├── Makefile                   shortcuts (setup, migrate, seed, test)
├── backend/                   Python, FastAPI, SQLAlchemy, PostgreSQL
│   ├── app/
│   │   ├── main.py            app factory, CORS, request-id logging
│   │   ├── api/               routes: health, brands, documents, facts, content, reviews, impacts
│   │   ├── core/              config, structured errors, logging, clock
│   │   ├── db/                declarative base, session
│   │   ├── models/            SQLAlchemy tables
│   │   ├── schemas/           Pydantic API contracts (separate from models)
│   │   ├── services/          business rules: extraction, storage, documents, facts, content, impacts (Phase 3)
│   │   │   └── review/        Phase 2 pipeline: claims, retrieval, matching, terminology, evidence, providers, pipeline
│   │   └── scripts/           seed.py, make_test_data.py
│   ├── alembic/               migrations (0001 Phase 1, 0002 Phase 2, 0003 Phase 3)
│   ├── tests/                 pytest suite against real PostgreSQL
│   ├── requirements*.txt
│   └── Dockerfile
├── frontend/                  Next.js 15, React 19, TypeScript, Tailwind
│   ├── app/                   pages: /knowledge, /facts, /review, /fact-changes
│   ├── components/            shell, facts, documents, source viewer
│   ├── lib/                   API client, formatting, hooks
│   ├── types/api.ts           types mirroring backend schemas
│   └── tests/                 Vitest component tests
├── test-data/                 fictional Nova Systems PDF, TXT, CSV and bad-file samples
├── docs/                      DATA_MODEL.md, API.md, TESTING.md
└── scripts/                   verify.sh, e2e_live.mjs, e2e_review.mjs, e2e_fact_impacts.mjs
```

## Run it

Requirements: Python 3.11+, Node 20+, PostgreSQL 16 (or Docker).

### Option A: everything in Docker

```bash
cp .env.example .env
docker compose up --build
# in another terminal, once the backend is healthy:
docker compose exec backend python -m app.scripts.seed
```

Open http://localhost:3000. API docs are at http://localhost:8000/api/docs.

### Option B: local development

```bash
# 1. Configuration
cp .env.example .env

# 2. PostgreSQL (skip if you already run one; then create the brandpr user and database yourself)
docker compose up -d db

# 3. Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head                 # apply migrations
.venv/bin/python -m app.scripts.seed           # demo data: Nova Systems (use --reset to recreate)
.venv/bin/uvicorn app.main:app --reload --port 8000

# 4. Frontend (new terminal)
cd frontend
npm install
npm run dev                                    # http://localhost:3000
```

The browser calls same-origin `/api/*`; Next.js proxies it to `BACKEND_URL` (default http://localhost:8000). CORS is also configured for `CORS_ORIGINS` for direct API use.

### Configuration

All settings come from environment variables, documented in `.env.example`. Real secrets never belong in tracked files; `.env` is git-ignored. `APP_ENV=production` refuses to start with the development database password or localhost CORS origins. Uploaded files are stored under `STORAGE_DIR`, which must be on persistent storage in any deployment (docker compose uses a named volume).

## Tests

```bash
# create a test database once
createdb brandpr_test      # or: psql -c 'CREATE DATABASE brandpr_test' (needs the brandpr user)

cd backend && .venv/bin/python -m pytest          # 229 tests, real PostgreSQL, migrations from scratch
cd frontend && npm run typecheck && npm test      # types and 43 component tests
node scripts/e2e_live.mjs                         # live Phase 0/1 checks through the running frontend proxy
node scripts/e2e_review.mjs                       # live Phase 2 review workflow (creates its own brand; repeatable)
node scripts/e2e_fact_impacts.mjs                 # live Phase 3: fact change and expiry propagation (creates its own brand; repeatable)
```

`scripts/verify.sh` runs the automated checks together. See `docs/TESTING.md` for the acceptance-test matrix and the actual results.
The backend test run recreates the schema of the database named by `TEST_DATABASE_URL` (default `brandpr_test`); never point it at data you want to keep.

## Review content (Phase 2: ProofGraph)

Open **Review content** (`/review`), pick a brand, enter a title and the draft text, and choose **Review content**. The draft is saved first, then analysed:

1. **Claim extraction** finds numbers, prices, comparisons ("fastest"), performance and time-sensitive statements, and avoided or misspelled terms. Each claim keeps its exact position in the saved text so the page can highlight it.
2. **Retrieval** loads the brand's approved facts from PostgreSQL. Only facts that are approved and currently valid (`current`) can support or contradict a claim. Proposed, rejected, expired or retired facts, and every other brand's facts, never count as current evidence.
3. **Matching** compares values with their units and qualifiers ("up to", "always"), checks that the claim states the fact's conditions, and detects expired facts that the claim still relies on.
4. **Findings** get one status: `supported`, `unsupported` (no approved evidence found; this does not mean false), `conflicting`, `outdated` or `uncertain`, plus a priority and a flag when a person must review it.
5. **Evidence** shows the real fact, source document, page and verified passage behind each finding. A claim with no evidence says so and cites nothing.

Every review is saved as its own run; reopening a draft shows the stored findings, and reviewing again adds a new run without overwriting the old one.

### AI provider and limited mode

The engine works with or without a model. Set `LLM_API_KEY` (server-side only) to enable AI-assisted extraction of paraphrased claims and paraphrase matching; the default provider adapter targets the Anthropic Messages API (`LLM_MODEL`, `LLM_BASE_URL`). The model output must be valid JSON in a fixed shape; anything else fails the run. The model never supplies facts or citations: every fact id it returns is checked against the records the backend retrieved, and unknown ids are discarded. AI-assisted findings are always marked for human review.

With no key, reviews complete as **limited analysis**: deterministic rules only, labelled on the page and in the API (`completed_limited`, with `limitations`). If a configured provider is unreachable or returns unusable output, the run is recorded as `failed` and no findings are kept; a review is never reported as passed because a provider failed.

### Limits of the review engine

* Deterministic claim detection is rule-based and English-only. It will miss claims worded without numbers, comparatives or known terms unless a provider is configured.
* Paraphrases are not recognised in limited mode; a possible paraphrase is reported `uncertain` rather than guessed.
* Unit handling covers common units (time, mass, percent, currency, storage); unusual units are reported `uncertain`.
* Facts are only matched by subject words from their name, so a fact with a vague name may not be found.
* A saved submission is never edited. Corrections are saved as new revisions (Phase 4, below).
* Reviews run inside the request. Very long drafts or a slow provider can take a while; the request fails visibly rather than silently.
* The real provider integration was not run against a live model in this environment (see `docs/TESTING.md`).

## Fact changes (Phase 3: Claim Ledger)

Open **Fact changes** (`/fact-changes`) to see content that was reviewed against an approved fact that has since changed or expired. Each row shows the content, the changed fact, the value the earlier review relied on, the value now, the claim concerned and why it is flagged. **Inspect impact** opens the original claim with the evidence exactly as saved at review time next to the fact as it is now, what changed (revision, who, why), and a link to the draft's review page (`/review?content=<id>`).

How it works:

1. **Material changes only.** Editing an approved fact's name, value, category, unit, conditions or source, withdrawing its approval (proposed, expired, retired), or moving its dates so it is no longer valid today flags dependent content. Changing the owner or the review reminder date does not, and neither does extending a date or approving a proposed fact.
2. **Reliance is read from history, not guessed.** A review relied on the fact if its saved evidence cites it at an older version (or, for findings that name the fact without an evidence row, if the revision timeline shows an approved version in force when the run started). Failed reviews, other brands' content and unrelated drafts are never flagged.
3. **Automatic.** The fact update path itself records the impacts in the same database transaction as the edit. There is no button to remember, and if recording fails the edit is not saved.
4. **Nothing is rewritten.** Earlier reviews, findings and evidence stay exactly as they were; the impact is a separate record. BrandPR never edits, approves or rejects the content. Flagged items stay "Needs review"; resolving them belongs to Phase 4.
5. **No duplicates.** The database allows one impact per content item per event and attributes each historical finding to one event. Repeated requests, repeated propagation and concurrent requests all converge on the same records.

**Expiry.** A fact can stay stored as approved after its expiry date passes (the date is inclusive). Because no edit happens, expiry is detected by an **on-demand sweep** that runs whenever the impact list, a fact's impacts or the summary is requested. It is not a background job and there is no scheduler: an expiry is recorded the first time someone asks after the date. The page therefore always shows current expiry impacts, but nothing is flagged on a day nobody opens it.

Testing aid: `CLOCK_OFFSET_DAYS` shifts only the date used by validity rules (never stored timestamps) so expiry can be exercised against a running server; it is 0 by default and refused in production.

### Limits of fact-change propagation

* Expiry is checked on request, not by a scheduler (see above).
* If a fact lapsed and was then edited (or its date extended) before anyone requested the list, the lapse is still recorded when the edit is saved, so a late extension still flags the content that relied on the lapsed approval.
* A historical finding is flagged by the first event that invalidated the fact it relied on. If the same fact changes again, content that was already flagged for it is not given a second row; only reviews made after the fact was re-approved are flagged by the later event. The fact's live state is shown on each impact.
* Findings that name a fact without a versioned evidence record are matched using the revision timeline and the run's start time. A change committed between a run starting and loading the facts could be attributed to either side.
* Evidence saved while the fact was already expired is not treated as reliance on a current approval (that review already said "outdated").
* Archiving a source document does not invalidate its facts under the Phase 1 policy, so it creates no impact; the impact detail shows when a cited source is archived.
* An impact stays open after the content is reviewed again (`reviewed_since_detection` says so). It is closed only by a reviewer's decision (Phase 4, below).
* There is no authentication, so impact details are fetched by id without a brand check; lists are brand-scoped.
* The expiry sweep makes list requests write to the database.

## Correct, approve and close the loop (Phase 4)

Phase 4 lets a creator correct content without losing its history, have the correction reviewed again, obtain a human decision, and close the related fact-change impact with an audit trail.

**Revisions.** Every submission is revision 1 of a *content asset*. Correcting content never edits it: **Review content > open a draft > Create corrected revision** saves the next revision (the original stays read only on the left, changes are highlighted, and the history lists every revision). Reviews, findings, evidence and Phase 3 impacts keep pointing at the exact revision they were created for. If someone else saved a newer revision first you get a clear conflict and your text stays in the editor.

**Correcting findings.** In the editor each open finding shows its explanation, recommended action and the approved evidence. You can write the replacement yourself, or ask for suggested wording. A suggestion is a proposal: it is applied only when you press *Accept*, and your accept / reject / modify choice is saved with the revision. Suggestions need an AI provider (`LLM_API_KEY`); without one the button reports that plainly and manual correction works as normal. Nothing is ever faked.

**Approval.** A new revision starts as a *draft*. Run a review of it, then **Submit for approval**. A reviewer then approves, requests changes or rejects, with a reason for the last two. The backend refuses approval unless the latest review of that exact text finished (a failed review never counts, a limited-mode review is disclosed), the reviewer names that review, the revision is still the newest, and every high-risk finding that is not supported has a recorded override with a reason (the finding itself is never edited). Approval is never inherited by a later revision.

**Closing impacts.** On **Fact changes**, a reviewer resolves an impact with an *approved later revision* of the same content (or dismisses it with a reason). Opening a draft, editing it or reviewing it does not close anything, and neither does an approval whose review still conflicts with the changed fact. The original impact, its evidence and its trigger stay exactly as recorded; the resolution is an append-only record (who, when, why, which revision and review).

### Demo roles (not authentication)

BrandPR has no sign-in. Pick a **name** and a **Demo role** (creator or reviewer) in the sidebar; they are sent as `X-Actor-Name` / `X-Actor-Role` headers. The backend enforces what each role may do (only reviewers can decide, a reviewer cannot decide on a revision they created), but **anyone who can reach the API can claim any role**. This is a competition-prototype stand-in, not production-grade authentication, and must be replaced by real accounts before real use.

### Run it

```bash
cd backend && .venv/bin/alembic upgrade head          # applies migration 0004 (backfills each old submission as revision 1)
node scripts/e2e_workflow.mjs                         # live end-to-end run of the whole workflow (backend and frontend running)
./scripts/verify.sh                                   # all automated checks
```

### Limits of the Phase 4 workflow

* Demo roles only (above). Decisions record the claimed name.
* Impacts are closed once; there is no re-open. Closing is a reviewer action in the UI; the API also allows resolving several impacts as part of an approval (`resolve_impact_ids`).
* The UI does not yet link individual findings to a "request changes" decision (the API accepts `finding_ids`).
* Suggested corrections were exercised with a controlled test provider, not a live model.
* No diff beyond the highlighted changed passage and the side-by-side text.

## Guideline Lint, Policy Sandbox & Governance Intelligence (Phase 5)

Phase 5 elevates BrandPR from a content review tool into a proactive governance intelligence system. It introduces source-linked guideline rule management, rule linting, a policy simulation sandbox, and evidence-backed governance analytics.

### Guideline Rule Management & Lint (`/guidelines`)

* **Rule Extraction**: Brand administrators can extract candidate rules directly from processed source documents. Every extracted rule is created in `proposed` status and **never automatically activated**. An authorized reviewer must explicitly approve it.
* **Inspectable Provenance**: Every guideline rule is source-linked with document citations, page numbers, and direct source excerpts, or explicitly marked as manually authored.
* **Deterministic Lint Engine**: Inspects active and proposed rules to detect weaknesses before content violations occur:
  - Vague instructions without measurable criteria or approved examples (e.g. "market-leading", "best-in-class", "innovative").
  - Unclear or missing scope.
  - Missing executable conditions when conditional phrasing is used ("when", "unless", "except").
  - Missing concrete positive/negative examples for claim and terminology rules.
  - Cross-rule terminology contradictions (one rule requires what another prohibits).
  - Cross-rule comparative claim contradictions (conflicting comparative claim permissions across overlapping rules).
* **Rule Versioning**: When an active rule is edited, the previous version is preserved in `guideline_rule_versions` with who changed it and why. Historical review runs continue to reflect the policy that was active when they were reviewed.

### Policy Sandbox (`/sandbox`)

* **Replay Without Historical Mutation**: Brand managers can test proposed rule changes against real historical content submissions before activation.
* **Comparative Simulation**: Evaluates content under the baseline active rule and the proposed rule, displaying side-by-side verdicts (`supported`, `conflicting`, `unsupported`, or `not_evaluable`).
* **Outcome Differentiation**: Quantifies total evaluated submissions, outcomes changed, unchanged, and not-evaluable results with detailed explanations.
* **Strict Historical Data-Integrity Guarantee**: Running a policy simulation **never modifies** past review runs, findings, evidence snapshots, content revisions, approval decisions, or fact-change impacts, and does not automatically activate the proposed rule.

### Governance Intelligence (`/insights`)

* **100% Persisted Records**: All metrics and counts are computed directly from real database records (`ContentSubmission`, `ReviewRun`, `ReviewFinding`, `FactChangeImpact`, `WorkflowEvent`, `GuidelineLintResult`, `PolicySimulation`). There are no mock fixtures or hardcoded constants.
* **Time Filtering**: Filter review history and decisions by `7d`, `30d`, or `all`.
* **Deduplicated Analytics**: Database queries group findings strictly by review run and finding ID, ensuring findings joined to multiple evidence records are never double-counted.
* **Actionable Recommendations**: Evidence-backed recommendations that correlate observed review bottlenecks (e.g. repeated unapproved terms, active rules with unresolved lint issues, open fact impacts, high-risk finding clusters) with concrete suggested governance actions, explicitly marked as requiring human assessment.

### Run Phase 5

```bash
cd backend && .venv/bin/alembic upgrade head          # applies migration 0005 (guidelines, simulations, insights)
node scripts/e2e_guidelines.mjs                       # live end-to-end check of Phase 5 workflow (backend and frontend running)
./scripts/verify.sh                                   # all automated checks across all phases
```

## Campaign Intelligence, Portfolio Audits & Release Readiness (Phase 6)

Phase 6 elevates BrandPR to evaluate entire multi-channel marketing campaigns as unified portfolios. It bridges the gap between individual content approvals and launch readiness, providing cross-asset consistency verification, deterministic release gates, and immutable audit history.

### Campaign Workspace (`/campaigns`, `/campaigns/[campaignId]`)

* **Campaign Entities**: Group existing content assets under a brand with channel roles (e.g. `landing_page`, `email`, `social_post`, `ad`, `product_spec`).
* **Selected Revisions**: A campaign binds specific revisions of content assets (`selected_submission_id`). Replacing an asset's selected revision invalidates existing release assessments and triggers an automated staleness notification.
* **Brand Isolation**: Enforced by backend services and composite database checks; assets belonging to another brand cannot be added to a campaign.
* **Non-Destructive Membership**: Adding or removing assets from a campaign never copies, alters, or deletes the underlying content submissions, review runs, findings, or approval history.

### Campaign Consistency Audit Engine

Executes a comprehensive, evidence-backed evaluation across all selected campaign assets:
1. **Cross-Asset Fact Inconsistencies**: Detects when different campaign assets make conflicting or incompatible claims regarding the same approved brand fact (e.g., one asset claiming 24 hours of battery life while another claims 36 hours for the same product specification).
2. **Outdated Fact Dependencies & Open Impacts**: Identifies assets relying on expired fact versions or subject to unresolved fact-change impacts.
3. **Guideline Policy Alignment**: Verifies that active brand guidelines are adhered to across assets and flags guideline contradictions.
4. **Workflow & Approval Completeness**: Identifies unreviewed assets, failed reviews, pending human-review requirements, and incomplete Phase 4 reviewer approvals.
5. **Audit Snapshots & History Comparison**: Persists every audit as an immutable snapshot. Consecutive audit runs can be compared with `GET /api/campaign-audits/{id}/comparison/{prev_id}` to categorize `new`, `persistent`, `resolved`, and `unevaluable` findings.

### Deterministic Release-Readiness Gate

Release decisions are computed from real persisted database state:
* `blocked`: One or more hard blockers exist (confirmed fact contradictions, unresolved fact impacts, missing/failed reviews, workflow rejections).
* `needs_review`: No confirmed hard blockers, but pending human-review items or unapproved revisions remain.
* `ready_for_release`: All campaign assets have passing reviews for their exact content hashes, zero blockers, zero open impacts, and approved Phase 4 workflow status.
* `released`: Transition executed explicitly by an authorized reviewer (`X-Actor-Role: reviewer`). Non-reviewers are refused (403 Forbidden).

### Staleness Protection

An assessment is marked `is_stale=True` whenever:
* An asset's selected revision is replaced in the campaign.
* A content asset undergoes a material revision or new review.
* An active fact or guideline rule relied upon by the campaign changes.

Releasing a stale assessment is strictly forbidden by the backend (409 Conflict).

### Run Phase 6

```bash
cd backend && .venv/bin/alembic upgrade head          # applies migration 0006 (campaigns, audits, findings, decisions)
node scripts/e2e_campaigns.mjs                        # live end-to-end check of Phase 6 workflow (19 verification steps)
./scripts/verify.sh                                   # complete test suite across all phases
```

## Key behaviours

* Uploading a document never approves anything. New facts and rules are `proposed`; approval is an explicit action recorded with who and when.
* Editing the wording, value, qualifications or source of an approved fact returns it to `proposed`.
* Expiry is evaluated every time a fact is read, so an expired fact is never shown as current. A missing expiry date is flagged, not assumed to mean forever.
* Every fact and rule cites a document (with a page and a checked excerpt) or states a manual source. Cross-brand citations are rejected by the API and by database constraints.
* Documents cited by facts or rules cannot be deleted; archive them. Failed processing leaves a clearly failed record, never a success.
* Policy simulations and guideline lint checks are strictly isolated from historical review and approval records.

See `docs/DATA_MODEL.md` for every table schema, `docs/API.md` for the endpoints, and `docs/TESTING.md` for test coverage.

