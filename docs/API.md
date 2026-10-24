# API reference (Phases 0 to 4)

Interactive documentation is served by FastAPI at `/api/docs` (Swagger UI), `/api/redoc` and `/api/openapi.json`.

Errors always use one shape: `{"error": {"code", "message", "details": [{"field", "message"}], "request_id"}}`.
Lists use `{"items", "total", "limit", "offset"}`. Dates are ISO 8601.

| Method and path | Purpose |
| --- | --- |
| GET `/api/health` | Liveness |
| GET `/api/health/db` | Database connectivity (503 if unreachable) |
| GET, POST `/api/brands` | List, create |
| GET, PATCH `/api/brands/{brand_id}` | Read, update |
| GET `/api/brands/{brand_id}/documents` | List (`processing_status`, `include_archived`, `limit`, `offset`) |
| POST `/api/brands/{brand_id}/documents` | Multipart upload: `file`, optional `title` |
| GET `/api/documents/{id}` | Metadata |
| GET `/api/documents/{id}/sections` | Extracted sections (`page_number`) |
| GET `/api/documents/{id}/text` | Full extracted text |
| GET `/api/documents/{id}/table` | CSV headers and rows |
| GET `/api/documents/{id}/file` | Original file (`inline=true` for PDFs) |
| POST `/api/documents/{id}/archive` | Archive |
| DELETE `/api/documents/{id}` | Delete if no fact cites it |
| GET `/api/brands/{brand_id}/facts` | List with filters (below) |
| GET `/api/brands/{brand_id}/facts/summary` | Counts by effective and review state |
| POST `/api/brands/{brand_id}/facts` | Create |
| GET `/api/facts/{id}` | Read, including source |
| PATCH `/api/facts/{id}` | Edit (partial) |
| PATCH `/api/facts/{id}/status` | Change approval status |
| GET `/api/facts/{id}/revisions` | History |

Fact list filters: `status`, `category`, `effective_state`, `review_state`, `review_within_days` (review date on or before today plus N days, including overdue), `source_document_id`, `q` (search), `sort`, `limit`, `offset`.

Status codes: 201 created, 204 deleted, 404 not found, 409 conflict (duplicate, in use, version conflict), 413 too large, 415 unsupported file, 422 validation, 503 database unavailable.

## Content review (Phase 2)

| Method and path | Purpose |
| --- | --- |
| POST `/api/brands/{brand_id}/content` | Save a draft. Body: `title` (1 to 300 characters), `content` (non-blank, at most `MAX_CONTENT_CHARS`), optional `submitted_by`. Stored exactly as submitted. |
| GET `/api/brands/{brand_id}/content` | List drafts (no body text), newest first, with `review_count` and the latest run's counts |
| GET `/api/content/{content_id}` | The saved draft with its text |
| POST `/api/content/{content_id}/reviews` | Run a review now. Body optional: `requested_by`. Returns the run **with its findings** |
| GET `/api/content/{content_id}/reviews` | Every run for the draft, newest first (findings omitted) |
| GET `/api/reviews/{review_id}` | One run: status, mode, counts, limitations, notes (findings omitted) |
| GET `/api/reviews/{review_id}/findings` | Findings with evidence, ordered by position. Filter `status`; `limit` (default 200), `offset` |

### Review run

`status`:

| Value | Meaning |
| --- | --- |
| `running` / `pending` | Not finished. A run found in this state after a restart is changed to `failed` (`interrupted`). |
| `completed` | Full analysis with an AI provider; findings are saved. |
| `completed_limited` | Deterministic rules only because no provider is configured (`analysis_mode: "limited"`). `limitations` explains what was not checked. |
| `failed` | No findings are kept. `error_code` is `provider_unavailable`, `provider_invalid_output`, `persistence_failed`, `database_error`, `interrupted` or `internal_error`; `error_message` is safe to show. |

`POST .../reviews` answers **201 even when `status` is `failed`**, because a run record exists. Always check `status`. If the results cannot be saved the response is 503 `review_persistence_failed`, and the run is recorded as failed, never as completed.

Other fields: `counts` (findings per status, computed from the saved findings), `total_findings`, `limitations`, `notes` (non-fatal observations such as discarded model output), `provider_name`, `model_name`, `content_hash`, `started_at`, `completed_at`.

### Finding

| Field | Notes |
| --- | --- |
| `claim_text`, `start_offset`, `end_offset` | `content[start_offset:end_offset] == claim_text` for the saved draft (character offsets) |
| `claim_category` | `quantitative`, `comparative`, `performance`, `specification`, `pricing`, `terminology`, `time_sensitive`, `general` |
| `status` | `supported`, `unsupported`, `conflicting`, `outdated`, `uncertain` (definitions in DATA_MODEL.md). **Unsupported does not mean false.** |
| `severity` | `low`, `medium`, `high` (review priority; defaults overridable with `REVIEW_SEVERITY_OVERRIDES`) |
| `explanation`, `recommended_action` | Text produced from the matched records |
| `requires_human_review` | True for high priority, conflicting, outdated and uncertain findings, and every AI-assisted finding |
| `method`, `extraction_method` | `deterministic` or `ai_assisted`; `deterministic` or `ai` |
| `matched_fact_id` | The main approved fact involved, if any |
| `evidence[]` | See below. Empty when no approved evidence exists. |

### Evidence

`role`: `supports`, `conflicts`, `outdated` (a matching fact that has expired or been retired), `context` (a related approved fact that neither supports nor contradicts), `related_source` (a real sentence from a source document that is **not** an approved fact; never support).
Each item carries the references (`fact_id`, `source_document_id`, `document_section_id`, `source_page`) and a snapshot taken at review time (`excerpt`, `excerpt_verified`, `fact_name`, `fact_value`, `fact_qualifications`, `fact_status`, `fact_effective_state`, `fact_version`, `relation_note`). The references are validated by composite foreign keys, so evidence cannot point at another brand's records or at nothing.

Errors use the standard structure. Status codes added in Phase 2: 404 unknown brand, content or review; 422 invalid body, over-long content, malformed ids or an unknown `status` filter; 503 `review_persistence_failed` or `database_unavailable`.


## Fact-change impacts (Phase 3)

Content that was reviewed against an approved fact that has since changed or expired. Impacts are created automatically: by `PATCH /api/facts/{id}` and `PATCH /api/facts/{id}/status` when the change is material, and by the expiry sweep. There is no endpoint to create, edit or resolve one.

| Method and path | Purpose |
| --- | --- |
| GET `/api/brands/{brand_id}/fact-change-impacts` | Page of impacts, newest first. Filters: `fact_id` (must belong to the brand, else 404), `status` (`needs_review`), `trigger_type` (`fact_revision`, `fact_expiry`), `content_id`; `limit` 1-200 (default 50), `offset`. |
| GET `/api/brands/{brand_id}/fact-change-impacts/summary` | Counts computed from the stored rows. |
| GET `/api/facts/{fact_id}/impacts` | Impacts of one fact (same filters except `fact_id`). |
| GET `/api/fact-change-impacts/{impact_id}` | One impact with its historical findings and snapshots. |

**Expiry sweep.** The three list and summary requests first run the on-demand expiry sweep for the brand: facts stored as `active` whose `expires_at` is before today (inclusive date) are checked for content that relied on them, and impacts are recorded once. It is not a background job, so expiry impacts appear the first time the ledger is read after the date passes. These GET requests therefore write; repeating them never duplicates records. The detail endpoint does not sweep.

### Impact (list item)

| Field | Meaning |
| --- | --- |
| `id`, `brand_id`, `status` | Identity; `status` is `needs_review` |
| `trigger_type`, `change_type` | `fact_revision` or `fact_expiry`; `material_edit`, `no_longer_approved`, `validity_changed` or `expired` |
| `headline`, `reason` | What changed, and why the content is flagged. Written when the impact was recorded. |
| `detected_at` | When it was recorded |
| `fact` | The fact **now**: `id`, `name`, `status`, `effective_state`, `version`, `value`, `unit` |
| `previous_fact_version`, `previous_value` | What the affected review relied on (from the revision history) |
| `current_fact_version`, `current_value` | The version after the change; the value of the fact now |
| `content` | `id`, `title`, `created_at` of the affected content |
| `source_review_run_id`, `source_review_started_at` | The historical review that relied on the fact |
| `affected_claim`, `affected_finding_count` | First claim that relied on the fact, and how many findings did |
| `latest_review_started_at`, `reviewed_since_detection` | Informational: a completed review started after detection. The impact is **not** resolved by it. |

### Impact detail

Adds `change_summary` (changed fields, `before_effective_state`, `after_effective_state`), `previous_snapshot` (the fact as recorded at the version the review relied on), `new_snapshot` (the fact as recorded at the change), `current_fact` (the full fact now, including source and archive state), `trigger_revision` (revision number, `changes`, `changed_by`, `change_reason`; null for expiry) and `findings[]`: each is the complete historical finding with its evidence exactly as saved, plus `match_basis` (`evidence` or `matched_fact`), `relied_fact_version` and the `review_run` summary.

### Summary

`open_impacts`, `facts_with_changes` (distinct facts), `content_needing_review` (distinct content), `expiry_affected_content`, `revision_affected_content`.

### Errors

Standard structure. 404 unknown brand, fact or impact, or a `fact_id` filter naming another brand's fact. 422 malformed ids, unknown `status` or `trigger_type`, `limit` outside 1-200 or negative `offset`. 503 `database_unavailable`: the request fails; an empty list is never returned for a failed query. 500 `internal_error` with no internal detail if the sweep fails. A fact edit whose impact recording fails returns an error and the edit is not saved (409 `integrity_error` or 500).

There is no authentication yet, so an impact id is not scoped to a brand; ids are unguessable UUIDs and every list is brand-scoped.

## Revisions and approval workflow (Phase 4)

**Identity (demo, not authentication).** Endpoints marked *actor* need `X-Actor-Name` and `X-Actor-Role` (`creator` or `reviewer`). Missing headers: `401 actor_required`. Unknown role: `422`. Reviewer-only endpoints answer `403 reviewer_role_required` to a creator. The claim is not authenticated; see the README.

Existing responses gained fields: content items carry `asset_id`, `revision_number`, `parent_submission_id`, `workflow_status`, `is_latest`, `change_note`; `GET /brands/{id}/content` accepts `latest_only=true` (one row per asset); impacts carry `resolution` and revision information on `content`; the impact summary adds `resolved_impacts`, `dismissed_impacts`, `total_impacts`.

| Method and path | Who | What |
|---|---|---|
| `POST /content/{id}/revisions` | actor | Body `{ title?, content, change_note?, corrections[] }`. Creates the next revision (201, returns the content item). `{id}` must be the newest revision, else `409 revision_conflict` (details: `latest_revision_id`, `latest_revision_number`). `409 revision_in_review` while a decision is pending. `422` for blank, over-long or unchanged text and for corrections citing findings of another revision. |
| `GET /content/{id}/revisions` | any | The asset's revisions, oldest first, each with review count, latest review, final decision, correction and open-impact counts. |
| `GET /findings/{id}` | any | One finding with evidence, its revision number and submission id. |
| `POST /findings/{id}/suggest-correction` | actor | A proposal for one claim; nothing is stored or applied. `503 ai_unavailable` without a provider, `409 nothing_to_correct` (supported claim), `409 no_current_evidence` (no currently approved fact is cited), `502 suggestion_failed`. Response has `replacement_text` (nullable), `rationale`, `warnings` (for example numbers not in the facts), `requires_human_review: true`. |
| `POST /content/{id}/submit-review` | actor | `draft -> in_review`. Needs a finished review of this exact text (`409 review_required`, `review_failed`, `review_in_progress`, `review_content_mismatch`), the newest revision (`409 revision_superseded`), and a draft (`409 invalid_transition`). |
| `GET /content/{id}/workflow` | any (headers optional) | `workflow_status`, `readiness` (`state`, `ready_for_decision`, reasons, limited mode and limitations, counts, `blocking_findings`), every workflow event of the asset, overrides, this revision's corrections, `available_actions` for the caller (empty without headers) and `approved_run_id`. |
| `POST /content/{id}/decisions` | reviewer | Body `{ action: approve\|request_changes\|reject, review_run_id?, rationale?, finding_ids[], overrides[{finding_id, reason}], resolve_impact_ids[], resolution_rationale? }` (201, returns the workflow). |
| `POST /fact-change-impacts/{id}/resolve` | reviewer | Body `{ resolving_submission_id, rationale }`. Returns the resolution record. Repeating the same request returns the same record (200). |
| `POST /fact-change-impacts/{id}/dismiss` | reviewer | Body `{ rationale }` (required). Repeating the same dismissal returns the same record. |
| `GET /fact-change-impacts/{id}/history` | any | Status, resolution records, the asset's revisions and every workflow event. |

### Decision rules

* `approve`: revision `in_review`, newest, not created by the deciding reviewer (`403 self_review_not_allowed`); `review_run_id` required (`422`) and must be the latest run (`409 stale_review`); that run must be finished with a matching content hash; every high-risk finding that is not `supported` needs an `overrides` entry with a reason (`409 high_risk_unresolved`, details list the findings; `422` for a blank reason or an override of a finding that is not overridable).
* `request_changes` / `reject`: a non-blank `rationale` is required; `finding_ids` must belong to the latest review.
* A second decision on a revision is `409 invalid_transition`.
* Overrides and `resolve_impact_ids` are only valid with `approve`.

### Impact resolution errors (all `409` unless noted)

`impact_not_open`, `wrong_brand`, `wrong_asset`, `wrong_revision`, `revision_not_approved`, `no_approval_evidence`, `review_not_completed`, `review_hash_mismatch`, `review_predates_impact`, `fact_changed_since_review`, `conflict_unresolved` (details list the findings), `stale_evidence`. `404` unknown impact or revision; `422` blank rationale.
