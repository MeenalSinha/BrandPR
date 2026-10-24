// Mirrors the backend Pydantic schemas (backend/app/schemas). A backend test compares field names,
// so adding or removing a field on one side without the other fails the test suite.

export type FactStatus = "proposed" | "active" | "rejected" | "expired" | "retired";
export type FactCategory = "product_spec" | "approved_claim" | "terminology" | "legal_disclaimer" | "pricing" | "general";
export type EffectiveState = "current" | "pending" | "expired" | "unapproved" | "retired";
export type ReviewState = "overdue" | "due_soon" | "scheduled" | "unscheduled" | "not_applicable";
export type ProcessingStatus = "pending" | "processing" | "processed" | "failed";
export type SourceType = "pdf" | "text" | "csv";
export type SectionKind = "page" | "text_block" | "csv_rows";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Brand {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface SourceDocument {
  id: string;
  brand_id: string;
  title: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  source_type: SourceType;
  processing_status: ProcessingStatus;
  content_hash: string;
  page_count: number | null;
  section_count: number;
  char_count: number;
  fact_count: number;
  uploaded_at: string;
  processed_at: string | null;
  error_message: string | null;
  archived_at: string | null;
}

export interface DocumentSection {
  id: string;
  document_id: string;
  section_index: number;
  kind: SectionKind;
  page_number: number | null;
  line_start: number | null;
  line_end: number | null;
  row_start: number | null;
  row_end: number | null;
  text: string;
  meta: Record<string, unknown> | null;
}

export interface TableData {
  document_id: string;
  headers: string[];
  rows: { row_number: number; cells: Record<string, string> }[];
  total_rows: number;
  limit: number;
  offset: number;
}

export interface FactSource {
  document_id: string;
  title: string;
  filename: string;
  source_type: string;
  processing_status: string;
  page_count: number | null;
  archived: boolean;
}

export interface Fact {
  id: string;
  brand_id: string;
  name: string;
  value: string;
  category: FactCategory;
  qualifications: string | null;
  unit: string | null;
  status: FactStatus;
  effective_state: EffectiveState;
  review_state: ReviewState;
  warnings: string[];
  source_document_id: string | null;
  source_page: number | null;
  source_excerpt: string | null;
  source_excerpt_verified: boolean | null;
  source_note: string | null;
  provenance: "document" | "manual";
  source: FactSource | null;
  owner: string | null;
  valid_from: string | null;
  review_date: string | null;
  expires_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface FactRevision {
  id: string;
  fact_id: string;
  revision_number: number;
  action: "created" | "updated" | "status_changed";
  changes: Record<string, { old: unknown; new: unknown }>;
  snapshot: Record<string, unknown>;
  changed_by: string | null;
  change_reason: string | null;
  created_at: string;
}

export interface FactSummary {
  total: number;
  by_effective_state: Record<string, number>;
  by_review_state: Record<string, number>;
  review_warning_days: number;
}

export interface Health {
  status: string;
  service: string;
  version: string;
  environment: string;
}

export interface FactCreateInput {
  name: string;
  value: string;
  category?: FactCategory;
  qualifications?: string | null;
  unit?: string | null;
  owner?: string | null;
  valid_from?: string | null;
  review_date?: string | null;
  expires_at?: string | null;
  source_document_id?: string | null;
  source_page?: number | null;
  source_excerpt?: string | null;
  source_note?: string | null;
  status?: "proposed" | "active";
  actor?: string | null;
}

export interface FactUpdateInput {
  name?: string;
  value?: string;
  category?: FactCategory;
  qualifications?: string | null;
  unit?: string | null;
  owner?: string | null;
  valid_from?: string | null;
  review_date?: string | null;
  expires_at?: string | null;
  source_document_id?: string | null;
  source_page?: number | null;
  source_excerpt?: string | null;
  source_note?: string | null;
  actor?: string | null;
  change_reason?: string | null;
  expected_version?: number | null;
}

export interface FactStatusInput {
  status: FactStatus;
  actor?: string | null;
  reason?: string | null;
  expected_version?: number | null;
}

export interface ApiErrorDetail {
  field: string | null;
  message: string;
}

/* ---------------------------------------------------------------- Phase 2: content review (ProofGraph) */
export type FindingStatus = "supported" | "unsupported" | "conflicting" | "outdated" | "uncertain";
export type Severity = "low" | "medium" | "high";
export type RunStatus = "pending" | "running" | "completed" | "completed_limited" | "failed";
export type AnalysisMode = "full" | "limited";
export type EvidenceRole = "supports" | "conflicts" | "outdated" | "context" | "related_source";
export type ClaimCategory = "quantitative" | "comparative" | "performance" | "specification" | "pricing" | "terminology" | "time_sensitive" | "general";

export interface ContentCreateInput {
  title: string;
  content: string;
  submitted_by?: string | null;
}

export interface ReviewRunBrief {
  id: string;
  status: RunStatus;
  analysis_mode: AnalysisMode;
  started_at: string;
  completed_at: string | null;
  counts: Record<string, number>;
}

export type WorkflowStatus = "draft" | "in_review" | "changes_requested" | "approved" | "rejected";

export interface ContentItem {
  id: string;
  brand_id: string;
  asset_id: string;
  revision_number: number;
  parent_submission_id: string | null;
  workflow_status: WorkflowStatus;
  is_latest: boolean;
  change_note: string | null;
  title: string;
  content: string;
  content_hash: string;
  submitted_by: string | null;
  created_at: string;
  updated_at: string;
  review_count: number;
  latest_review: ReviewRunBrief | null;
}

export interface ContentSummary {
  id: string;
  brand_id: string;
  asset_id: string;
  revision_number: number;
  workflow_status: WorkflowStatus;
  is_latest: boolean;
  title: string;
  char_count: number;
  submitted_by: string | null;
  created_at: string;
  review_count: number;
  latest_review: ReviewRunBrief | null;
}

export interface Evidence {
  id: string;
  role: EvidenceRole;
  fact_id: string | null;
  source_document_id: string | null;
  document_section_id: string | null;
  source_title: string | null;
  source_page: number | null;
  excerpt: string | null;
  excerpt_verified: boolean | null;
  fact_name: string | null;
  fact_value: string | null;
  fact_qualifications: string | null;
  fact_status: string | null;
  fact_effective_state: string | null;
  fact_version: number | null;
  relation_note: string | null;
}

export interface Finding {
  id: string;
  review_run_id: string;
  claim_index: number;
  claim_text: string;
  claim_category: ClaimCategory;
  start_offset: number;
  end_offset: number;
  status: FindingStatus;
  severity: Severity;
  explanation: string;
  recommended_action: string | null;
  requires_human_review: boolean;
  method: "deterministic" | "ai_assisted";
  extraction_method: "deterministic" | "ai";
  matched_fact_id: string | null;
  evidence: Evidence[];
  created_at: string;
}

export interface ReviewRun {
  id: string;
  brand_id: string;
  content_submission_id: string;
  status: RunStatus;
  analysis_mode: AnalysisMode;
  content_hash: string;
  requested_by: string | null;
  started_at: string;
  completed_at: string | null;
  provider_name: string | null;
  model_name: string | null;
  error_code: string | null;
  error_message: string | null;
  counts: Record<string, number>;
  limitations: string[];
  notes: string[];
  total_findings: number;
  findings: Finding[] | null;
}

/* ---------------------------------------------------------------- Phase 3: Claim Ledger fact-change impacts */
export type ImpactTrigger = "fact_revision" | "fact_expiry";
export type ImpactChangeType = "material_edit" | "no_longer_approved" | "validity_changed" | "expired";
export type ImpactStatus = "needs_review" | "resolved" | "dismissed";
export type MatchBasis = "evidence" | "matched_fact";

export interface ImpactFactBrief {
  id: string;
  name: string;
  status: FactStatus;
  effective_state: EffectiveState;
  version: number;
  value: string;
  unit: string | null;
}

export interface ImpactContentBrief {
  id: string;
  title: string;
  created_at: string;
  asset_id: string;
  revision_number: number;
  latest_revision_id: string;
  latest_revision_number: number;
  latest_revision_status: WorkflowStatus;
}

export interface ImpactResolutionBrief {
  action: "resolved" | "dismissed";
  actor: string;
  rationale: string;
  created_at: string;
  resolving_submission_id: string | null;
  resolving_revision_number: number | null;
  resolving_review_run_id: string | null;
}

export interface Impact {
  id: string;
  brand_id: string;
  status: ImpactStatus;
  trigger_type: ImpactTrigger;
  change_type: ImpactChangeType;
  headline: string;
  reason: string;
  detected_at: string;
  fact: ImpactFactBrief;
  previous_fact_version: number;
  current_fact_version: number;
  previous_value: string;
  current_value: string;
  content: ImpactContentBrief;
  source_review_run_id: string;
  source_review_started_at: string;
  affected_claim: string | null;
  affected_finding_count: number;
  latest_review_started_at: string | null;
  reviewed_since_detection: boolean;
  resolution: ImpactResolutionBrief | null;
}

export interface ImpactRevision {
  id: string;
  revision_number: number;
  action: "created" | "updated" | "status_changed";
  changes: Record<string, { old: unknown; new: unknown }>;
  changed_by: string | null;
  change_reason: string | null;
  created_at: string;
}

export interface ImpactFinding {
  finding: Finding;
  match_basis: MatchBasis;
  relied_fact_version: number;
  review_run: ReviewRunBrief;
}

export interface ImpactDetail extends Impact {
  change_summary: Record<string, unknown>;
  previous_snapshot: Record<string, unknown>;
  new_snapshot: Record<string, unknown>;
  current_fact: Fact;
  trigger_revision: ImpactRevision | null;
  findings: ImpactFinding[];
}

export interface ImpactSummary {
  open_impacts: number;
  resolved_impacts: number;
  dismissed_impacts: number;
  total_impacts: number;
  facts_with_changes: number;
  content_needing_review: number;
  expiry_affected_content: number;
  revision_affected_content: number;
}

/* ---------------------------------------------------------------- Phase 4: revisions, approval workflow, impact resolution */
export type WorkflowAction = "created" | "submitted" | "approved" | "changes_requested" | "rejected";
export type DecisionAction = "approve" | "request_changes" | "reject";
export type ActorRole = "creator" | "reviewer";
export type CorrectionDecision = "accepted" | "rejected" | "modified" | "manual";
export type CorrectionSource = "ai" | "manual";
export type ReadinessState = "no_review" | "review_in_progress" | "review_failed" | "content_mismatch" | "ready";

export interface CorrectionInput {
  finding_id: string;
  decision: CorrectionDecision;
  source: CorrectionSource;
  original_text: string;
  replacement_text: string | null;
}

export interface RevisionCreateInput {
  title?: string | null;
  content: string;
  change_note?: string | null;
  corrections?: CorrectionInput[];
}

export interface DecisionBrief {
  id: string;
  action: WorkflowAction;
  actor: string;
  actor_role: ActorRole;
  rationale: string | null;
  review_run_id: string | null;
  created_at: string;
}

export interface Revision {
  id: string;
  asset_id: string;
  brand_id: string;
  revision_number: number;
  parent_submission_id: string | null;
  title: string;
  created_by: string | null;
  created_at: string;
  change_note: string | null;
  char_count: number;
  content_hash: string;
  workflow_status: WorkflowStatus;
  is_latest: boolean;
  review_count: number;
  latest_review: ReviewRunBrief | null;
  decision: DecisionBrief | null;
  correction_count: number;
  open_impact_count: number;
}

export interface RevisionHistory {
  asset_id: string;
  brand_id: string;
  title: string;
  latest_revision_id: string;
  items: Revision[];
}

export interface CorrectionRecord {
  id: string;
  finding_id: string;
  decision: CorrectionDecision;
  source: CorrectionSource;
  original_text: string;
  replacement_text: string | null;
  created_at: string;
}

export interface Suggestion {
  finding_id: string;
  review_run_id: string;
  start_offset: number;
  end_offset: number;
  original_text: string;
  replacement_text: string | null;
  rationale: string | null;
  cannot_suggest_reason: string | null;
  evidence_fact_ids: string[];
  warnings: string[];
  requires_human_review: true;
  source: "ai";
  provider_name: string | null;
  model_name: string | null;
}

export interface FindingDetail {
  finding: Finding;
  revision_number: number;
  submission_id: string;
}

export interface OverrideInput {
  finding_id: string;
  reason: string;
}

export interface DecisionInput {
  action: DecisionAction;
  review_run_id?: string | null;
  rationale?: string | null;
  finding_ids?: string[];
  overrides?: OverrideInput[];
  resolve_impact_ids?: string[];
  resolution_rationale?: string | null;
}

export interface RiskOverride {
  id: string;
  event_id: string;
  review_run_id: string;
  finding_id: string;
  reason: string;
  actor: string;
  created_at: string;
}

export interface WorkflowEvent {
  id: string;
  submission_id: string;
  revision_number: number;
  action: WorkflowAction;
  from_status: WorkflowStatus | null;
  to_status: WorkflowStatus;
  actor: string;
  actor_role: ActorRole;
  rationale: string | null;
  review_run_id: string | null;
  finding_ids: string[];
  created_at: string;
}

export interface BlockingFinding {
  finding_id: string;
  claim_text: string;
  status: string;
  severity: string;
  explanation: string;
  overridden: boolean;
}

export interface Readiness {
  state: ReadinessState;
  ready_for_decision: boolean;
  reasons: string[];
  review: ReviewRunBrief | null;
  review_status: RunStatus | null;
  analysis_mode: AnalysisMode | null;
  limited_mode: boolean;
  limitations: string[];
  counts: Record<string, number>;
  blocking_findings: BlockingFinding[];
}

export interface Workflow {
  submission_id: string;
  asset_id: string;
  brand_id: string;
  title: string;
  revision_number: number;
  is_latest: boolean;
  created_by: string | null;
  workflow_status: WorkflowStatus;
  readiness: Readiness;
  events: WorkflowEvent[];
  overrides: RiskOverride[];
  corrections: CorrectionRecord[];
  available_actions: string[];
  approved_run_id: string | null;
}

export interface ImpactResolution {
  id: string;
  impact_id: string;
  action: "resolved" | "dismissed";
  from_status: string;
  to_status: string;
  actor: string;
  actor_role: ActorRole;
  rationale: string;
  resolving_submission_id: string | null;
  resolving_revision_number: number | null;
  resolving_review_run_id: string | null;
  decision_event_id: string | null;
  created_at: string;
}

export interface ImpactHistory {
  impact_id: string;
  status: ImpactStatus;
  detected_at: string;
  affected_submission_id: string;
  affected_revision_number: number;
  asset_id: string;
  latest_revision_id: string;
  latest_revision_number: number;
  resolutions: ImpactResolution[];
  revisions: Revision[];
  events: WorkflowEvent[];
}
