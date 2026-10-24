import type { ClaimCategory, EffectiveState, EvidenceRole, FactCategory, FactStatus, FindingStatus, ImpactChangeType, ImpactStatus, ImpactTrigger, ProcessingStatus, ReviewState, RunStatus, Severity, WorkflowAction, WorkflowStatus } from "@/types/api";

export const CATEGORY_LABELS: Record<FactCategory, string> = {
  product_spec: "Product specification",
  approved_claim: "Approved claim",
  terminology: "Terminology",
  legal_disclaimer: "Legal disclaimer",
  pricing: "Pricing",
  general: "General",
};

export const EFFECTIVE_LABELS: Record<EffectiveState, string> = {
  current: "Current", pending: "Not yet valid", expired: "Expired", unapproved: "Unapproved", retired: "Retired",
};

export const STATUS_LABELS: Record<FactStatus, string> = {
  proposed: "Proposed", active: "Approved", rejected: "Rejected", expired: "Marked expired", retired: "Retired",
};

export const PROCESSING_LABELS: Record<ProcessingStatus, string> = {
  pending: "Waiting", processing: "Reading", processed: "Processed", failed: "Failed",
};

export const WARNING_LABELS: Record<string, string> = {
  no_expiry_date: "No expiry date recorded. Confirm it is still valid at the next review.",
  expired_by_date: "Approved, but its expiry date has passed.",
  review_overdue: "Review is overdue.",
  review_due_soon: "Review is due soon.",
  source_document_archived: "The source document is archived.",
  excerpt_not_found_in_source: "The saved excerpt was not found in the source text.",
};

export function formatDate(value: string | null | undefined): string {
  if (!value) return "Not set";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function reviewText(state: ReviewState, date: string | null): string {
  if (state === "not_applicable") return "";
  if (state === "unscheduled") return "No review date";
  if (state === "overdue") return `Review overdue since ${formatDate(date)}`;
  if (state === "due_soon") return `Review due ${formatDate(date)}`;
  return `Review on ${formatDate(date)}`;
}

/** Wrap occurrences of the excerpt in a <mark>. Whitespace-insensitive, case-insensitive. */
export function splitByExcerpt(text: string, excerpt: string | null | undefined): { text: string; hit: boolean }[] {
  const words = (excerpt ?? "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return [{ text, hit: false }];
  const pattern = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+");
  const match = new RegExp(pattern, "i").exec(text);
  if (!match) return [{ text, hit: false }];
  return [
    { text: text.slice(0, match.index), hit: false },
    { text: match[0], hit: true },
    { text: text.slice(match.index + match[0].length), hit: false },
  ].filter((p) => p.text.length > 0);
}

export const FINDING_LABELS: Record<FindingStatus, string> = {
  supported: "Supported", unsupported: "Unsupported", conflicting: "Conflicting", outdated: "Outdated", uncertain: "Uncertain",
};
export const FINDING_ORDER: FindingStatus[] = ["supported", "unsupported", "conflicting", "outdated", "uncertain"];
export const FINDING_HELP: Record<FindingStatus, string> = {
  supported: "Current approved evidence supports the claim under its conditions.",
  unsupported: "No approved evidence was found. This does not mean the claim is false.",
  conflicting: "Approved evidence contradicts the claim.",
  outdated: "The claim relies on a fact that has expired or been retired.",
  uncertain: "The relationship to the evidence cannot be decided reliably. A person should check.",
};
export const SEVERITY_LABELS: Record<Severity, string> = { low: "Low priority", medium: "Medium priority", high: "High priority" };
export const ROLE_LABELS: Record<EvidenceRole, string> = {
  supports: "Supporting evidence", conflicts: "Conflicting evidence", outdated: "Outdated evidence", context: "Related approved fact",
  related_source: "Related source text (not an approved fact)",
};
export const CLAIM_LABELS: Record<ClaimCategory, string> = {
  quantitative: "Number", comparative: "Comparison", performance: "Performance", specification: "Specification", pricing: "Price",
  terminology: "Terminology", time_sensitive: "Time-sensitive", general: "General",
};
export const RUN_LABELS: Record<RunStatus, string> = {
  pending: "Waiting", running: "Running", completed: "Completed", completed_limited: "Completed with limited analysis", failed: "Failed",
};

export interface DraftSegment { text: string; findingIds: string[] }

/** Split the saved draft at every finding boundary so each piece knows which findings cover it. Offsets come from the backend. */
export function segmentDraft(content: string, findings: { id: string; start_offset: number; end_offset: number }[]): DraftSegment[] {
  const points = new Set<number>([0, content.length]);
  for (const f of findings) {
    if (f.start_offset >= 0 && f.end_offset <= content.length && f.end_offset > f.start_offset) { points.add(f.start_offset); points.add(f.end_offset); }
  }
  const cuts = Array.from(points).sort((a, b) => a - b);
  const out: DraftSegment[] = [];
  for (let i = 0; i < cuts.length - 1; i++) {
    const [a, b] = [cuts[i], cuts[i + 1]];
    out.push({ text: content.slice(a, b), findingIds: findings.filter((f) => f.start_offset <= a && f.end_offset >= b && f.end_offset > f.start_offset).map((f) => f.id) });
  }
  return out;
}

export const TRIGGER_LABELS: Record<ImpactTrigger, string> = {
  fact_revision: "Approved fact changed", fact_expiry: "Approval expired",
};
export const CHANGE_LABELS: Record<ImpactChangeType, string> = {
  material_edit: "Meaning or evidence changed", no_longer_approved: "No longer approved", validity_changed: "Validity dates changed", expired: "Expiry date passed",
};
export const IMPACT_STATUS_LABELS: Record<ImpactStatus, string> = { needs_review: "Needs review", resolved: "Resolved", dismissed: "Dismissed" };

export const WORKFLOW_LABELS: Record<WorkflowStatus, string> = {
  draft: "Draft", in_review: "In review", changes_requested: "Changes requested", approved: "Approved", rejected: "Rejected",
};
export const ACTION_LABELS: Record<WorkflowAction, string> = {
  created: "Revision created", submitted: "Submitted for approval", approved: "Approved", changes_requested: "Changes requested", rejected: "Rejected",
};
