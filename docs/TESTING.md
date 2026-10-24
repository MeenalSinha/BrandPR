# Testing and acceptance results

Results below are from actual runs. Environment: Ubuntu 24 container, Python 3.12, Node 22, PostgreSQL 16.15 (apt, started locally), no Docker, no browser, no AI provider credentials.
Backend: **229 pytest tests pass** against real PostgreSQL (schema rebuilt from migrations at the start of each run): 140 from Phases 0 to 2, 88 new in `tests/test_impacts.py` (Phase 3) and 1 new clock-guard test in `tests/test_phase0.py`.
Frontend: `tsc --noEmit` clean, **43 Vitest tests pass** (30 from Phases 0 to 2, 13 new), `next build` succeeds and includes `/fact-changes`.
Live: `scripts/e2e_live.mjs` (19 checks), `scripts/e2e_review.mjs` (18) and `scripts/e2e_fact_impacts.mjs` (26 PASS, 0 skipped) all pass against the running servers; the Phase 3 script was run three times in a row against the same database. `scripts/verify.sh` passed end to end.

## Phase 0 and 1 audit before Phase 2

The README and earlier results were not taken on trust. In this checkout, before changing anything:

* Backend suite (59 tests), frontend typecheck, 18 component tests and production build all passed.
* Migrations 0001 applied to an empty database; the seed ran; `/api/health` and `/api/health/db` answered, directly and through the Next.js proxy.
* `e2e_live.mjs` passed all 18 checks against the running servers.
* Independent probes against the live API: a fact citing another brand's document was rejected (422, field `source_document_id`), a nonexistent document was rejected, a disguised executable named `.pdf` was refused (415), deleting a document cited by a fact was refused (409 `document_in_use`), a malformed id gave a structured 422, an unapproved origin received no `Access-Control-Allow-Origin`, an allowed origin did, `APP_ENV=production` with the development password refused to start, and `.env` is git-ignored while `.env.example` is not.

No Phase 0 or Phase 1 defect was found, so no repair was needed. The completion gate was met before Phase 2 started. One Phase 1 tool needed a follow-up once Phase 2 existed: `seed.py --reset` would have failed on a foreign key when review data existed. Fixed, with a regression test (`test_seed_reset_removes_review_data_before_facts`).

## Commands

```bash
cd backend && .venv/bin/python -m pytest       # TEST_DATABASE_URL must name a disposable database such as brandpr_test
cd frontend && npm run typecheck && npm test && npm run build
node scripts/e2e_live.mjs            # backend and frontend must be running
node scripts/e2e_review.mjs          # Phase 2 workflow; creates uniquely named brands, safe to repeat
node scripts/e2e_fact_impacts.mjs    # Phase 3; creates its own brand, safe to repeat; starts a second backend for the expiry step
```

## Phase 0

| Test ID | Result | Evidence |
| --- | --- | --- |
| P0-01 | PASS | `test_p0_01_backend_starts_with_real_server` starts uvicorn as a subprocess and gets 200 from `/api/health` |
| P0-02 | PASS (no real browser) | `next build` succeeds; `next start` serves `/`, `/knowledge`, `/facts` with HTTP 200 (e2e script); component tests render both pages. Not opened in a real browser |
| P0-03 | PASS | `test_p0_03_health_endpoint` |
| P0-04 | PASS | `test_p0_04_database_connection` runs `SELECT 1` and `SHOW server_version`; e2e also checks it through the proxy and after a PostgreSQL restart |
| P0-05 | PASS | `test_p0_05_*`: values read from environment; production refuses development defaults |
| P0-06 | PASS | `test_p0_06*` scan the repository for key patterns and check `.env.example` and `.gitignore`; e2e scans the production browser bundle for server-side configuration names and the dev password |
| P0-07 | PASS | `test_p0_07*`: structured 422 with field names, 404 shape, no stack trace or path in 500 responses |
| P0-08 | PASS | `test_p0_08_cors_allows_dev_origin_only`: allowed origin gets headers, other origin does not |
| P0-09 | PASS | `test_p0_09_api_documentation_available`: `/api/docs` and OpenAPI paths and schemas |
| P0-10 | PASS | `test_p0_10_readme_documents_setup`, plus a full setup from a clean copy following the README. Docker path not run (see below) |

## Phase 1

| Test ID | Result | Evidence |
| --- | --- | --- |
| P1-01 | PASS | `test_p1_01_create_brand_persists_with_id` |
| P1-02 | PASS | `test_p1_02_create_fact_and_retrieve` |
| P1-03 | PASS | `test_p1_03_edit_fact_persists_after_reload` builds a fresh application and engine and reads the edit back |
| P1-04 | PASS | `test_p1_04_list_only_returns_selected_brand` |
| P1-05 | PASS | `test_p1_05_nonexistent_source_rejected_without_orphan` |
| P1-06 | PASS | `test_p1_06_*` rejected by the API and, bypassing the API, by the composite foreign key |
| P1-07 | PASS | `test_p1_07_mark_fact_expired_and_persist` |
| P1-08 | PASS | `test_p1_08_filter_by_status_category_and_search` |
| P1-09 | PASS | `test_p1_09_review_date_rules` with a fixed clock (overdue, today, boundary at 30 days, unscheduled) |
| P1-10 | PASS | `test_p1_10_referenced_document_policy`: delete refused 409, archive flags the fact, no new citations |
| P1-11 | PASS | `test_p1_11_valid_pdf_upload` |
| P1-12 | PASS | `test_p1_12_pdf_text_has_page_references` |
| P1-13 | PASS | `test_p1_13_plain_text_upload` |
| P1-14 | PASS | `test_p1_14_csv_headers_and_rows` |
| P1-15 | PASS | `test_p1_15*`: corrupt, blank and header-only files are recorded as failed with an error; no stored file remains |
| P1-16 | PASS | `test_p1_16_*`: nine disguised or unsupported files rejected with 415; nothing stored |
| P1-17 | PASS | `test_p1_17_oversized_file_rejected`: limit + 1 bytes gives 413, exactly the limit is accepted |
| P1-18 | PASS | `test_p1_18_duplicate_upload_policy` |
| P1-19 | PASS | `test_p1_19_associate_fact_with_uploaded_source` |
| P1-20 | PASS | `test_p1_20_inspect_fact_source` (title, filename, excerpt, verification flag) |
| P1-21 | PASS (API and UI logic) | `test_p1_21_*` page validation and page-2 section lookup; component test shows page 2 with the passage marked and a link to the original at that page. PDF opening in a browser viewer not exercised |
| P1-22 | PASS | `test_p1_22_manual_fact_requires_explicit_provenance` |
| P1-23 | PASS | `test_p1_23_invalid_fact_data_rejected_and_not_persisted` (nine invalid payloads, none persisted) |
| P1-24 | PASS | `test_p1_24_*` and the fresh-application reload in P1-03 |
| P1-25 | PASS (component test) | `P1-25` in `tests/ui.test.tsx`; live data path covered by the e2e script |
| P1-26 | PASS (component test) | `P1-26` and `P1-26b` (failed processing shown as failure) |
| P1-27 | PASS (component test) | `P1-27`: POST body checked, new fact appears without manual refresh |
| P1-28 | PASS (component test) | `P1-28`: PATCH sends only changed fields and `expected_version`; new value displayed |
| P1-29 | PASS (component test) | `P1-29`, `P1-29c`, `P1-29d`: server rejection, 500 with retry, unreachable backend |
| P1-30 | PASS (component test) | `P1-30`, `P1-30b` |

Additional backend tests cover approval semantics, transitions, expiry boundary, missing-expiry warning, pending validity, optimistic concurrency, atomic rollback, history snapshots, database check constraints, migration parity with the models (including downgrade and re-upgrade), and frontend/backend type agreement.

## Phase 2

All P2 rows below were executed. Backend tests are in `backend/tests/test_review.py` (unless noted); model output is injected with `FakeProvider` (`tests/fakes.py`); frontend tests are in `frontend/tests/ui.test.tsx` with the in-memory API stand-in updated to the real contracts.

| Test ID | Result | Evidence |
| --- | --- | --- |
| P2-01 | PASS | `test_p2_01_submit_valid_draft`: 201, UUID, trimmed title, 64-character hash |
| P2-02 | PASS | `test_p2_02_*` (7 invalid payloads: blank and missing title or content, unknown field): 422 with field names, nothing saved |
| P2-03 | PASS | `test_p2_03_content_length_limit`: exactly the limit accepted, limit + 1 rejected (test limit 5,000) |
| P2-04 | PASS | `test_p2_04_*`: structured 404 `not_found` |
| P2-05 | PASS | `test_p2_05_*`: text returned exactly as submitted, list omits body |
| P2-06 | PASS | `test_p2_06_*`: a new application and engine read the saved draft |
| P2-07 | PASS | `test_p2_07_one_quantitative_claim` |
| P2-08 | PASS | `test_p2_08_*`: three claims in order, no duplicates, also when a model repeats them |
| P2-09 | PASS | `test_p2_09_*`: no claims is `completed` / `completed_limited` with a note; provider failure is `failed`; the three are distinguishable |
| P2-10 | PASS | `test_p2_10_*`: `content[start:end] == claim_text` for every finding, including a model-found claim |
| P2-11 | PASS | `test_p2_11_*`: 5 malformed outputs give `failed` / `provider_invalid_output`, zero findings saved; `test_p2_11b`: invented claim text is discarded with a note |
| P2-12 | PASS | `test_p2_12_*`: identical findings and evidence ids across two runs, different run ids |
| P2-13 | PASS | `test_p2_13_and_21_*`: supported with the approved wording and conditions |
| P2-14 | PASS | `test_p2_14_*`: 24 hours against up to 18 hours is `conflicting`, evidence is the real fact, page 2 |
| P2-15 | PASS | `test_p2_15_and_22_*`: comparative claim is `unsupported`, high priority, no evidence rows |
| P2-16 | PASS | `test_p2_16*`: fact marked expired, fact expired by date (clock moved), and a claim matching an expired fact while a current fact exists: all `outdated` |
| P2-17 | PASS | `test_p2_17*`: proposed fact is not evidence (explanation says it is not approved); rejected and retired facts also do not support |
| P2-18 | PASS | `test_p2_18_*`: another brand's fact is never used; that brand's own review does use it |
| P2-19 | PASS | `test_p2_19*`: omitted conditions give `uncertain`; "always 18 hours" gives `conflicting`; dropping "up to" gives `uncertain` |
| P2-20 | PASS | `test_p2_20_*`: lower maximum, different units, and "real-world" conditions are `uncertain` with human review |
| P2-21 | PASS | `test_p2_13_and_21_*`: evidence ids, title, page, excerpt and section id match the stored rows and the sections endpoint |
| P2-22 | PASS | `test_p2_15_and_22_*`: no evidence rows in the table for an unsupported finding |
| P2-23 | PASS | `test_p2_23_*`: nonexistent, other-brand and malformed fact ids from the model are discarded, zero evidence rows, run notes the discard; `23b`: a valid id is accepted but flagged AI-assisted and for review; `23c`: a model "supports" cannot override a numeric conflict |
| P2-24 | PASS | `test_p2_24_*`: four claims, four different outcomes, each with its own evidence and correct offsets |
| P2-25 | PASS | `test_p2_25_*`: the run is `running` in the database before analysis starts |
| P2-26 | PASS | `test_p2_26_*`: findings saved against the right run and brand |
| P2-27 | PASS | `test_p2_27_*`: run, paged findings and the status filter match the creation response |
| P2-28 | PASS | `test_p2_28_*`: two runs; the first run's findings are unchanged after the world changed |
| P2-29 | PASS | `test_p2_29*`: provider unavailable and a failure while interpreting give `failed` with no findings; no key gives `completed_limited` with the limitation text |
| P2-30 | PASS | `test_p2_30*`: persistence failure returns 503 `review_persistence_failed`, no internal detail, the run ends `failed`, zero findings (also when failure occurs mid-save: atomic) |
| P2-31 | PASS | `test_p2_31_*`: malformed ids give 422, unknown ids give 404, on all five new routes |
| P2-32 | PASS | `test_p2_32_*` with a fresh application; also verified live with a real backend process restart (2 runs and identical counts before and after) |
| P2-33 | PASS | UI test: page renders in `AppShell`, nav link to `/review` |
| P2-34 | PASS | UI test: POST `/brands/{id}/content` body then POST `/content/{id}/reviews` through the real API client |
| P2-35 | PASS | UI test: counts and finding list equal the backend response (plus validation test: empty input never calls the API) |
| P2-36 | PASS | UI test: explanation, evidence role, fact, conditions and highlighted claim for the selected finding |
| P2-37 | PASS | UI test: citation opens the source drawer on page 2 with the passage marked and the sections request for that page |
| P2-38 | PASS | UI test: unsupported claim shows "No suitable approved evidence was found" and no evidence items or source buttons |
| P2-39 | PASS | UI tests: save error shows the server message and no results; a `failed` run shows the failure and Retry and no counts, then a retry succeeds; limited mode is labelled and an empty result is not shown as failure |
| P2-40 | PASS | UI test: after unmounting, reopening a draft calls the content, reviews and findings endpoints and makes no POST |

Additional tests: database integrity (`test_review_schema.py`: other-brand evidence, nonexistent references, evidence pointing at nothing, cross-brand run and finding, status/severity/offset/run-status checks, restricted deletion, indexes), migration 0002 from a populated Phase 1 schema with downgrade and re-upgrade, frontend/backend type agreement for all new schemas, the OpenAPI listing of new routes, interrupted runs marked failed at startup, review does not modify any fact row, and the provider adapter over a mocked HTTP transport (`test_provider_adapter.py`: request shape, HTTP errors, timeouts, unreadable responses, no secret in errors, no key means no provider).

### Mandatory end-to-end demonstration

`node scripts/e2e_review.mjs` (through the same-origin proxy, real backend and database, no model): creates a unique brand, uploads the Nova specification PDF, creates an approved fact citing page 2, submits a campaign with a supported, a conflicting and an unsupported comparative claim, starts the review, retrieves the run and findings, checks evidence ids, document, section, page and verified passage against the stored rows, checks the unsupported claim has no citation, checks brand association, retrieves everything again and compares it, runs a second review and confirms it is a separate run. 18 checks, all pass, run twice in a row.

## Phase 2 audit before Phase 3

Nothing from the Phase 2 report was taken on trust. In this checkout, before any Phase 3 change (environment: Ubuntu 24 container, PostgreSQL 16.15 installed with apt and started locally, a dedicated disposable `brandpr_test` database for the destructive test setup and a separate `brandpr` database for the live servers):

* `scripts/verify.sh` steps run individually: backend **140 passed**; frontend typecheck clean; **30** Vitest tests passed; production build succeeded.
* Migrations 0001 and 0002 applied to an empty database, the seed ran, `/api/health` and `/api/health/db` answered directly and through the Next.js proxy.
* `e2e_live.mjs`: all 19 checks passed. `e2e_review.mjs`: all 18 checks passed.
* Independent probes against the live API: another brand's review of an identical claim received no evidence from the first brand; a malformed id gave a structured 422 and an unknown id a structured 404; an active fact edited to a past expiry date read back as `expired`, as the Phase 1 policy states.

**Defects found: none.** No Phase 0, 1 or 2 code needed repair. One documentation inaccuracy was corrected: the README said 139 backend tests where the suite had 140. The Phase 2 completion gate was satisfied before Phase 3 started.

## Phase 3

Backend IDs are in `backend/tests/test_impacts.py` (real PostgreSQL, the real review pipeline in limited mode, the real fact API; no model provider is involved). Expiry tests control the date by patching `app.core.clock.today`. Frontend IDs are in `frontend/tests/ui.test.tsx` (Vitest, jsdom, in-memory API stand-in that mirrors the real response shapes). "PASS" means the test was run and passed in this environment.

### A. Explicit fact changes

| Test ID | Result | Evidence |
| --- | --- | --- |
| P3-01 | PASS | `test_p3_01`: owner-only edit creates no impact rows |
| P3-02 | PASS | `test_p3_02`: value edit flags both campaigns that relied on version 1; headline names old and new value |
| P3-03 | PASS | `test_p3_03`: the link row holds the real `finding_evidence` id, basis `evidence`; affected claim matches the reviewed finding |
| P3-04 | PASS | `test_p3_04`: with the evidence rows deleted, the finding that names the fact only through `matched_fact_id` is still flagged (basis `matched_fact`, version 1 inferred from the revision timeline). `test_p3_04b`: a run that started while the fact was not approved is not flagged |
| P3-05 | PASS | `test_p3_05`: versions 1 to 2; previous value "Up to 18 hours" from history, current value from the live fact |
| P3-06 | PASS | `test_p3_06`: a review made against version 3 is not flagged when the version-2 event is replayed, and is flagged (3 to 4, previous value "Up to 14 hours") by a later change |
| P3-07 | PASS | `test_p3_07`: two findings on one fact in one draft give one impact with `affected_finding_count` 2 and one database row |
| P3-08 | PASS | `test_p3_08`: five reviewed campaigns, five impacts |
| P3-09 | PASS | `test_p3_09`: the draft that relied on a different fact is not flagged |
| P3-10 | PASS | `test_p3_10`: another brand with an equivalent fact and campaign is not flagged, and the reverse direction also holds |

### B. Material versus metadata-only

| Test ID | Result | Evidence |
| --- | --- | --- |
| P3-11 | PASS | `test_p3_11_to_14[value]` |
| P3-12 | PASS | `test_p3_11_to_14[qualifications]` |
| P3-13 | PASS | `test_p3_11_to_14[unit]`, `[category]`, `[name]` |
| P3-14 | PASS | `[source_page]`, `[source_excerpt]`, and `test_p3_14b` (changing the source document; the snapshots show both document ids) |
| P3-15 | PASS | `test_p3_15` for retired, proposed and expired: `no_longer_approved`, fact state no longer current |
| P3-16 | PASS | `test_p3_16a` extending the expiry creates nothing; `16b` moving it into the past flags (`validity_changed`); `16c` valid-from in the future flags; `16d` shortening to a still-valid date flags nothing until the date passes, then the sweep flags |
| P3-17 | PASS | `test_p3_17` owner change |
| P3-18 | PASS | `test_p3_18` review reminder date: no impact (Phase 1 policy treats it as a reminder) |
| P3-19 | PASS | `test_p3_19`: value edit returns the fact to `proposed`, dependent content is flagged, and a new draft using the proposed wording gets no supporting evidence from it. `test_p3_19b`: approving it adds no impact |

Pure rules are also tested directly (`test_assess_revision_rules`, 9 cases, plus the not-current and inclusive-expiry boundaries).

### C. Idempotency and concurrency

| Test ID | Result | Evidence |
| --- | --- | --- |
| P3-20 | PASS | `test_p3_20`: propagation replayed three times for one revision; rows stay at 2 and links at 2 |
| P3-21 | PASS | `test_p3_21`: repeated list and summary requests after expiry return the same ids and row count |
| P3-22 | PASS | `test_p3_22`: two threads with separate sessions compute the same candidates (synchronised by a barrier) and then write; exactly one set of rows results, one thread creates 2 and the other 0. `test_p3_22b` and `22c`: the database itself rejects a duplicate event for a content item and a second attribution of a finding |
| P3-23 | PASS | `test_p3_23`: a database error raised during impact recording rolls the edit back (fact still version 1, active, one revision, no impacts, error returned); the same edit then succeeds |
| P3-24 | PASS | `test_p3_24`: a run turned `failed` is not flagged; `24b`: a review that failed at the provider is not flagged |
| P3-25 | PASS | `test_p3_25`: a zero-claim review and an unsupported-claim review are not flagged |

Extra edge cases: `test_lapse_before_the_edit_is_recorded_once_as_an_expiry` (a fact that lapsed and is then edited yields one expiry impact per campaign, not two events) and `test_extension_saved_after_a_lapse_still_records_the_lapse`.

### D. Expiry

| Test ID | Result | Evidence |
| --- | --- | --- |
| P3-26 | PASS | `test_p3_26`: date equal to `expires_at` is still current; nothing flagged |
| P3-27, P3-28 | PASS | `test_p3_27_28`: the next day both campaigns are flagged, `fact_expiry`, fact stored `active` with effective state `expired`, no new revision |
| P3-29 | PASS | `test_p3_29`: expired fact with no dependent content creates no rows |
| P3-30 | PASS | `test_p3_30`: sweeps on four dates, one impact per asset |
| P3-31 | PASS | `test_p3_31`: no expiry date, date set to 2040, nothing flagged |
| P3-32 | PASS | `test_p3_32`: after a re-approval, a review of the newer version is flagged by the later expiry with previous version 3, while the older campaigns keep their single revision-based impact |

### E. Historical integrity

| Test ID | Result | Evidence |
| --- | --- | --- |
| P3-33 | PASS | `test_p3_33`: full row snapshots of `review_findings`, `finding_evidence`, `review_runs` and `content_submissions` are identical before and after an edit, an approval, a retirement and an expiry sweep |
| P3-34 | PASS | `test_p3_34`: the saved evidence still reads "Up to 18 hours", version 1, active/current, with excerpt and page |
| P3-35 | PASS | `test_p3_35`: previous snapshot, new snapshot, live fact and saved evidence differ and are all present |
| P3-36 | PASS | `test_p3_36`: SQL joins confirm each impact's revision belongs to its fact, its run belongs to its content, each linked finding belongs to a run of that content, and brands agree |
| P3-37 | PASS (by policy) | `test_p3_37`: archiving the source leaves the fact `current` with a `source_document_archived` warning (existing Phase 1 policy), so no impact is created; after a later edit the impact detail reports the source as archived and keeps the historical citation. Archival is not treated as invalidating evidence because the Phase 1 and 2 code still allows archived-source facts as evidence |

### F. API

| Test ID | Result | Evidence |
| --- | --- | --- |
| P3-38 | PASS | `test_p3_38` (five impacts in pages of 2: totals, sizes, no overlap, order equals the unpaged order, summary) and `38b` (filters by status, trigger, fact and content) |
| P3-39 | PASS | `test_p3_39` |
| P3-40 | PASS | `test_p3_40`: trigger revision, who and why, changes, summary, historical finding and saved evidence, source run |
| P3-41 | PASS | `test_p3_41`: unknown fact, impact, brand and a `fact_id` filter naming no fact give structured 404 |
| P3-42 | PASS | `test_p3_42` (3 malformed ids) and `42b` (7 invalid filter or paging values) give structured 422 |
| P3-43 | PASS | `test_p3_43`: another brand sees an empty list and zero summary, and a `fact_id` from the first brand is a 404; `43b`: the database refuses an impact whose brand differs from its fact, content or run |
| P3-44 | PASS | `test_p3_44`: with an unreachable database all four endpoints return 503 `database_unavailable`, no `items`, no host or user in the body; `44b`: a failing sweep fails the request with 500 and no internal detail |

### G. Frontend

| Test ID | Result | Evidence |
| --- | --- | --- |
| P3-45 | PASS | Impacts and summary are requested from `/api/brands/<id>/fact-change-impacts`; counts equal what the (stateful) API returned, including distinct fact and content counts and expiry |
| P3-46 | PASS | Row shows content, fact, previous and current values, claim, reason and status |
| P3-47 | PASS | Detail shows "Historical: version 1" and "Current: version 2" boxes, the reason, the revision and its reason, and the statement that nothing was changed automatically |
| P3-48 | PASS | The original claim, the evidence value, excerpt and "Nova spec, page 2", and the saved version are displayed |
| P3-49 | PASS | Empty state, summary shows 0 because the API returned 0 |
| P3-50 | PASS | A 503 shows an error with Try again, no empty state and no summary figure |
| P3-51 | PASS | Unmount and mount again: same records fetched again |
| P3-52 | PASS | The link is `/review?content=<id>`; `P3-52b`: `ReviewView` given that URL opens the draft with its stored findings and starts no new review |

Also covered: trigger filtering and pagination go through the API, and the shell navigation links to `/fact-changes`.

### Schema and migration

| Check | Result | Evidence |
| --- | --- | --- |
| Models and migration agree | PASS | `alembic check` reports no new operations; `test_models_and_migration_agree` compares the model metadata with the migrated schema |
| Upgrade, downgrade, re-upgrade | PASS | `test_migration_0003_...` on the test database, and manually: 0003 up, down to 0002, up again. Phase 1 and 2 row counts are identical before downgrade, after it and after re-upgrade, and the feature works afterwards |
| Upgrade of a database that already holds Phase 2 data | PASS | The live `brandpr` database (seeded and used by the earlier E2E runs) was upgraded from 0002 to 0003 in place |
| Constraints and indexes | PASS | `test_schema_has_the_required_constraints_and_indexes` |
| Python and TypeScript contracts agree | PASS | `test_frontend_types_match_backend_schemas` now includes the impact schemas and their enums |

### Mandatory end-to-end demonstration

`node scripts/e2e_fact_impacts.mjs`: through the frontend proxy, real backend, PostgreSQL and review pipeline. It creates a unique brand, uploads the Nova PDF, creates an approved fact citing page 2 and a second fact, submits two campaigns that use the first, an unrelated draft and a draft with no claims, reviews all four, checks the persisted evidence cites the fact at version 1, edits the fact through `PATCH /api/facts/{id}`, and confirms with no further call that exactly the two campaigns are flagged, that the trigger is the stored revision (id, who, reason), that previous and current snapshots differ, that the original findings and evidence are byte-identical, that repeated requests return the same records, that an owner-only edit adds nothing, and that another brand sees nothing. For the expiry step it starts a second backend process with `CLOCK_OFFSET_DAYS=10` against the same database: the weight fact reads expired there and current in the normal backend; the sweep flags only the weight draft, repeated sweeps add nothing, and the normal backend then returns the same persisted impact and its detail. 26 checks PASS, 0 skipped, repeated three times in a row. The first run of the final script version passed without changes, so no script defect was masked.

### Test validity check

To confirm the tests do not pass vacuously, two deliberate faults were introduced temporarily and then reverted: disabling propagation in the fact service made 42 of the 88 Phase 3 backend tests fail; treating owner and review-date edits as material made 5 fail (P3-01, P3-17, P3-18 and two rule cases). After restoring the code all 88 passed again.

## Not run, and limits (Phase 3)

* **Real AI provider: NOT RUN.** Phase 3 is deterministic and was verified only with reviews in limited mode (`completed_limited`). The dependency query accepts `completed` (full-mode) runs through the same status filter, but no test creates a full-mode run and then propagates a change, so that path is untested.
* Browser: no real browser. The page was verified with Vitest and jsdom, a production build, and an HTTP 200 for `/fact-changes`. Layout on small screens, keyboard flow in the drawer and the visual distinction between historical and current values were not inspected by eye.
* Docker: untested (no daemon).
* Expiry in the live E2E uses `CLOCK_OFFSET_DAYS` on a second backend process, not a real day passing. The sweep logic itself is also tested with the patched application clock.
* Not tested: very large numbers of reviews per fact (performance beyond the indexed queries), concurrent edits of a fact racing the expiry sweep (the sweep uses `SKIP LOCKED` and a per-brand advisory lock by design, but only the concurrent-propagation case is tested), non-UTC edge cases around midnight, and propagation after a database restart mid-request.
* Not implemented in Phase 3: a background scheduler for expiry, notifications. (Resolving impacts was added in Phase 4.)
* Other limits are listed in the README under "Limits of fact-change propagation".

## Not run, and limits (Phase 2)

* **Real AI provider: NOT RUN.** No credentials were available. The provider adapter is tested only against a mocked HTTP transport, and the model-assisted pipeline only with a controlled fake. Whether a live model returns usable claim or assessment JSON, and its latency, are untested. The full-mode path is therefore verified for its handling of model output, not for model quality.
* Browser: no real browser. UI behaviour is tested with Vitest and jsdom, and the production build serves `/review`. Visual layout, keyboard flow and the highlight rendering were not inspected by eye.
* Docker: still untested (no daemon).
* Not tested: very long drafts near the character limit under a slow provider, concurrent reviews of one draft, non-English content, PDFs with unusual encodings, claims split across lines.
* The deterministic rules are deliberately conservative and English-only; see the README for the full list of limits.
* Severity defaults are a policy choice (for example every unsupported numeric claim is high priority) and may need tuning with real reviewers.

## Not run, and limits (Phases 0 and 1)

* Docker: no Docker daemon was available. `docker-compose.yml` and both Dockerfiles are untested.
* Real-browser testing: no browser was available. The P1-25 to P1-30 results come from Vitest with jsdom and an in-memory API stand-in, backed by live API checks through the Next.js server. Use the manual checklist below before a demo.
* Not tested: concurrent heavy upload load, files near the page and row limits, PDFs with unusual encodings.
* Scanned PDFs are reported as failed (no OCR in this phase).

## Manual UI checklist (about 10 minutes)

1. Run the seed, open `/facts`: seven facts, mixed Current, Expired, Unapproved, with review warnings.
2. Click a fact's source: the drawer shows the PDF page text with the passage highlighted; Open original at page N opens the PDF.
3. New fact with no source note: the form blocks save. Add a note, save, see it as Unapproved.
4. Approve it from Details; edit its value; confirm it returns to Unapproved and History shows both entries.
5. Brand knowledge: upload `test-data/nova_spec_table.csv`, then `corrupt.pdf` (shows Failed with a reason), then `unsupported.exe` (rejected with a message), then the same CSV again (duplicate message).
6. Inspect a document cited by a fact and try Delete: it is refused; Archive it and confirm the fact shows a warning.
7. Stop the backend and reload: an error message with Try again appears, not a blank page.
8. Create a new brand: both pages show empty states.
9. Review content: submit a draft with `Battery life is up to 18 hours under specified test conditions.`, `Battery life is 24 hours.` and `Nova is the fastest laptop.`. Expect supported, conflicting and unsupported findings, a "Limited analysis" notice if no key is set, the claims highlighted in the draft, and "No suitable approved evidence was found" for the comparative claim. Open a citation and confirm it shows page 2 with the passage marked. Reload, reopen the draft under Previous drafts, and confirm the same findings appear.

## Phase 3 audit before Phase 4

Run on a freshly provisioned sandbox (PostgreSQL 16 installed with apt, databases `brandpr` and the disposable `brandpr_test`; the destructive test setup points only at `brandpr_test`).

| Check | Result |
|---|---|
| `pytest` (backend) | PASS, 229 passed |
| Frontend typecheck, `npm test`, production build | PASS, 43 tests; build succeeded |
| `node scripts/e2e_live.mjs` | PASS, 19 checks |
| `node scripts/e2e_review.mjs` | PASS, 18 checks |
| `node scripts/e2e_fact_impacts.mjs` | PASS, 26 checks (including the expiry step with a second backend) |
| `/api/health`, `/api/health/db` | PASS |
| Secrets in the frontend bundle (`LLM_API_KEY`, DB password, `sk-ant`) | None found in `.next/static` |
| Migrations 0001-0003: upgrade, downgrade to base, upgrade again | PASS |
| Code review of the Phase 3 checklist against the actual models and services | No defect found in the Phase 3 behaviour |

**Defect found during the audit (Phase 3 area):** `python -m app.scripts.seed --reset` did not delete fact-change impacts, so it would fail with a foreign-key error as soon as any impact existed. The old tests never combined a reset with impacts. Fixed in Phase 4 (the reset now removes impacts and the new history tables), with regression test P4-52.

**Completion gate:** satisfied before any Phase 4 code was written. No unresolved critical regression remained.

## Phase 4

Counts below come from the final run of `./scripts/verify.sh` and the four live scripts on this sandbox.

| Suite | Result |
|---|---|
| Backend `pytest` | **PASS, 281 passed** (229 earlier + 52 new in `tests/test_workflow.py`) |
| Frontend typecheck | PASS |
| Frontend component tests | **PASS, 68** (43 earlier + 25 new in `tests/workflow.test.tsx`) |
| Frontend production build | PASS |
| `e2e_live.mjs` / `e2e_review.mjs` / `e2e_fact_impacts.mjs` | PASS 19 / 18 / 26 (rerun after migration 0004 on a database that already held Phase 1-3 data) |
| `e2e_workflow.mjs` (new) | **PASS, 26 checks**, run twice for repeatability; steps 17-18 read through a second backend process |
| Migration 0004 on a database with legacy data | PASS: backfill verified (P4-51 and manual run), downgrade to 0003 and upgrade again, zero model/schema difference reported by Alembic |

Two existing tests were changed because the behaviour they described was deliberately replaced, not weakened: the Phase 3 sentence "BrandPR has not changed, approved or rejected this content" (on the impact panel) is gone, and the limited-analysis text now also appears in the approval panel. The Phase 3 impact-summary test gained the three new count fields.

### A. Revision management (backend)
P4-01 first submission is revision 1 of its own asset; P4-02 correction creates revision 2 and the original (text, hash, title) is untouched; P4-03 hashes equal sha256 of the saved text; P4-04 numbering, history survives a fresh client; P4-05 old findings and evidence unchanged; P4-06 stale base gives `revision_conflict`; **P4-07 six simultaneous creations: exactly one succeeds, revision numbers stay unique**; P4-08 the database refuses a forged cross-brand asset, a parent from another asset and a duplicate number; P4-09 revisions are immutable in the database; P4-10 title change and validation; P4-11 identity headers; P4-12 `latest_only`; P4-13 no revision while a decision is pending.

### B. Correction and review
P4-14 inspect a finding and evidence; P4-15 manual correction works with no provider; P4-16 a suggestion is a proposal and is grounded in the current fact (nothing stored); P4-17 unsupported numbers are flagged; P4-18 refusals are honest (supported claim, no evidence, provider failure, malformed output); P4-19 accepted/modified/rejected suggestions are recorded with the revision and foreign findings are refused; P4-20 the new review covers the new text and the current fact version; P4-21 a failed review is never approval-ready; P4-22 limited mode is disclosed.

### C. Approval
P4-23 submit; P4-24 drafts cannot be approved; P4-25 approval is persisted with actor, role, run and time (re-read through a fresh client and SQL); P4-26 creators cannot act as reviewers; P4-27 no self-approval; P4-28 stale review; P4-29 failed latest review blocks approval; P4-30 a review of other text cannot approve this text; P4-31 high-risk findings block approval, override needs a reason, finding unchanged; P4-32 non-high findings do not block and cannot be overridden; P4-33 request changes; P4-34 reject; P4-35 no repeated or reversed decision (also at database level); P4-36 no inherited approval; P4-37 history, append-only; P4-38 superseded revisions.

### D. Impact resolution
P4-39 correct, review, approve and resolve the right impact in one transaction, unrelated impact untouched, original impact and historical findings unchanged, dashboard counts match; P4-40 explicit resolve, idempotent repeat, closed impact cannot be re-closed; P4-41 nothing short of an approved revision resolves (new revision, review, in-review all refused); P4-42 a failed review cannot resolve, even with a forged approval row; **P4-43 a conflicting claim cannot resolve, and the failed resolution rolls back the whole approval**; P4-44 an approval whose review predates the impact, or a fact changed after the review, does not count; P4-45 wrong asset, brand or revision; P4-46 dismissal (reviewer, reason, idempotent, original impact intact); P4-47 impact history; P4-48 database guards (no status change without a resolution row, no rewrite, no re-open); P4-49 expiry impacts close the same way; P4-50 identity checks come first; P4-51 migration backfill with legacy rows; P4-52 seed reset.

### E. Frontend (jsdom component tests)
P4-U01 to U09 revision editor (read-only original, evidence first, manual correction saved as a new revision, AI suggestion only applied on Accept, rejection recorded, honest "no provider" message, conflict keeps the text, missing name explained, older revision read only); U10 to U17 approval panel (failed review not ready, submit, reviewer decision, self-review blocked, reasons required, high-risk override reason, limited mode, server refusal shown); U20 to U26 Fact changes (status tabs query the API, counts from the API, resolve with an approved revision, no candidates, dismissal needs a reason, creators cannot close, server refusal shown, nothing marked resolved); U30 sidebar role is the role sent.

### Mandatory end-to-end demonstration
`node scripts/e2e_workflow.mjs` (needs the backend and frontend running): brand, real PDF source, approved fact, two campaigns reviewed; the fact changes and creates impacts; the affected revision is opened and its stale finding inspected; a manual correction becomes revision 2 and revision 1 is proven unchanged (text, hash, findings, evidence); revision 2 is reviewed on its own text; submission, refused creator approval, reviewer approval, resolution of only the affected impact; a later revision does not inherit approval; history; **reload through a second backend process**; then the high-risk scenario (blocked, blank override refused, audited override recorded, finding unchanged), a conflicting approval that cannot clear the impact, an audited dismissal, a change request, and totals checked against the persisted records. Result: 26 PASS, 0 FAIL, 0 SKIP, repeated twice.

### Not run, and limits (Phase 4)
* **Suggested corrections with a real model were not run** (no `LLM_API_KEY` in this environment). The path is tested with a controlled provider; the live script confirms the honest 503 without a provider.
* **Reviews ran in limited (deterministic) mode** in all live runs; the full AI mode was not exercised.
* **No real browser**: the UI is tested with jsdom component tests against a stateful fake of the API (its rules were written to match the backend and are not a substitute for it). The pages build and the backend contract test compares every new type. Desktop and mobile widths were **not** checked visually; layouts use the existing responsive grid classes.
* Demo roles are not authentication (see the README). A reviewer name differing from the creator's name is the only separation of duties enforced.
* The UI does not send `finding_ids` with "request changes" (the API supports it and the tests cover it).
* Impacts cannot be re-opened.
* The "reload" in the live script is a second backend process reading the same database, not a browser refresh.
