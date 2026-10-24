import { vi } from "vitest";

import type {
  Brand, ContentItem, DocumentSection, Evidence, Fact, Finding, Impact, ImpactContentBrief, ImpactDetail, ImpactResolution, ReviewRun, SourceDocument,
  Suggestion, WorkflowEvent, WorkflowStatus,
} from "@/types/api";

/** In-memory stand-in for the BrandPR API that mirrors the real response shapes and error format. */
export class FakeApi {
  brands: Brand[] = [];
  docs: SourceDocument[] = [];
  facts: Fact[] = [];
  sections: Record<string, DocumentSection[]> = {};
  calls: { method: string; url: string; body?: unknown; headers?: Record<string, string> }[] = [];
  failNext: { status: number; code: string; message: string; details?: { field: string; message: string }[] } | "network" | null = null;
  uploadResult: Partial<SourceDocument> | null = null;
  contents: ContentItem[] = [];
  runs: Record<string, ReviewRun[]> = {};
  findingsByRun: Record<string, Finding[]> = {};
  /** What the pretend backend answers when a review is started. Tests set this to a realistic backend response. */
  reviewResponder: ((item: ContentItem) => { run: Partial<ReviewRun>; findings: Finding[] }) | null = null;
  impacts: Impact[] = [];
  impactDetails: Record<string, ImpactDetail> = {};
  events: WorkflowEvent[] = [];
  /** What the pretend backend answers to suggest-correction; null means no AI provider is configured (503). */
  suggestResponder: ((finding: Finding) => Partial<Suggestion>) | null = null;
  private n = 1;
  id = () => `00000000-0000-4000-8000-${String(this.n++).padStart(12, "0")}`;

  /** The exact-revision brief the backend returns for an impact's content. */
  contentBrief(title: string, over: Partial<ImpactContentBrief> = {}): ImpactContentBrief {
    const id = over.id ?? this.id();
    return { id, title, created_at: "2026-10-20T00:00:00Z", asset_id: this.id(), revision_number: 1, latest_revision_id: id, latest_revision_number: 1, latest_revision_status: "draft", ...over };
  }

  /** A saved content revision as the backend returns it. */
  addContent(brandId: string, over: Partial<ContentItem> = {}): ContentItem {
    const item: ContentItem = {
      id: this.id(), brand_id: brandId, asset_id: this.id(), revision_number: 1, parent_submission_id: null, workflow_status: "draft", is_latest: true, change_note: null,
      title: "Summer Campaign Advertisement", content: "Battery life lasts up to 18 hours. Order today.", content_hash: "c".repeat(64), submitted_by: "Casey Creator",
      created_at: "2026-10-20T00:00:00Z", updated_at: "2026-10-20T00:00:00Z", review_count: 0, latest_review: null, ...over,
    };
    this.contents.push(item);
    return item;
  }

  /** Stores a finished review of `item` with the given findings (what the backend would hold after a review ran). */
  addReview(item: ContentItem, findings: Finding[], over: Partial<ReviewRun> = {}): ReviewRun {
    const run: ReviewRun = {
      id: this.id(), brand_id: item.brand_id, content_submission_id: item.id, status: "completed", analysis_mode: "full", content_hash: item.content_hash,
      requested_by: null, started_at: "2026-10-20T00:00:05Z", completed_at: "2026-10-20T00:00:06Z", provider_name: "fake", model_name: "fake-model",
      error_code: null, error_message: null, counts: {}, limitations: [], notes: [], total_findings: findings.length, findings: null, ...over,
    };
    const counts: Record<string, number> = { supported: 0, unsupported: 0, conflicting: 0, outdated: 0, uncertain: 0 };
    findings.forEach((f) => { f.review_run_id = run.id; counts[f.status] += 1; });
    run.counts = counts;
    this.runs[item.id] = [run, ...(this.runs[item.id] ?? [])];
    this.findingsByRun[run.id] = findings;
    return run;
  }

  private latestOf(item: ContentItem) {
    return this.contents.filter((c) => c.asset_id === item.asset_id).sort((a, b) => b.revision_number - a.revision_number)[0];
  }

  private readiness(item: ContentItem) {
    const run = (this.runs[item.id] ?? [])[0] ?? null;
    const findings = run ? this.findingsByRun[run.id] ?? [] : [];
    const blocking = findings.filter((f) => f.severity === "high" && f.status !== "supported").map((f) => ({ finding_id: f.id, claim_text: f.claim_text, status: f.status, severity: f.severity, explanation: f.explanation, overridden: false }));
    const state = !run ? "no_review" : run.status === "failed" ? "review_failed" : run.status === "pending" || run.status === "running" ? "review_in_progress" : "ready";
    const reasons = state === "no_review" ? ["This revision has not been reviewed yet. Run a review first."] : state === "review_failed" ? [`The latest review failed and is not evidence of anything: ${run?.error_message ?? "failed"} Run the review again.`] : [];
    if (run?.status === "completed_limited") reasons.push("Limited analysis: no AI provider was available, so only deterministic rules ran.");
    return {
      state, ready_for_decision: state === "ready", reasons, review: run ? { id: run.id, status: run.status, analysis_mode: run.analysis_mode, started_at: run.started_at, completed_at: run.completed_at, counts: run.counts } : null,
      review_status: run?.status ?? null, analysis_mode: run?.analysis_mode ?? null, limited_mode: run?.status === "completed_limited", limitations: run?.limitations ?? [],
      counts: run?.counts ?? {}, blocking_findings: state === "ready" ? blocking : [],
    };
  }

  private workflowOf(item: ContentItem, role: string | undefined, name: string | undefined) {
    const ready = this.readiness(item);
    const actions: string[] = [];
    if (item.is_latest && item.workflow_status === "draft") { actions.push("run_review"); if (ready.ready_for_decision) actions.push("submit_review"); }
    if (item.is_latest && item.workflow_status !== "in_review") actions.push("create_revision");
    if (role === "reviewer" && item.is_latest && item.workflow_status === "in_review" && (item.submitted_by ?? "").toLowerCase() !== (name ?? "").toLowerCase()) {
      actions.push("request_changes", "reject");
      if (ready.ready_for_decision) actions.push("approve");
    }
    return {
      submission_id: item.id, asset_id: item.asset_id, brand_id: item.brand_id, title: item.title, revision_number: item.revision_number, is_latest: item.is_latest,
      created_by: item.submitted_by, workflow_status: item.workflow_status, readiness: ready,
      events: this.events.filter((e) => this.contents.some((c) => c.id === e.submission_id && c.asset_id === item.asset_id)),
      overrides: [], corrections: [], available_actions: role && name ? actions : [], approved_run_id: null,
    };
  }

  private pushEvent(item: ContentItem, action: WorkflowEvent["action"], to: WorkflowStatus, from: WorkflowStatus | null, actor: string, role: "creator" | "reviewer", rationale: string | null = null) {
    this.events.push({
      id: this.id(), submission_id: item.id, revision_number: item.revision_number, action, from_status: from, to_status: to, actor, actor_role: role, rationale,
      review_run_id: (this.runs[item.id] ?? [])[0]?.id ?? null, finding_ids: [], created_at: `2026-10-22T11:00:${String(this.events.length).padStart(2, "0")}Z`,
    });
  }

  private revisionOf(c: ContentItem) {
    const run = (this.runs[c.id] ?? [])[0] ?? null;
    const decision = this.events.filter((e) => e.submission_id === c.id && ["approved", "changes_requested", "rejected"].includes(e.action))[0];
    return {
      id: c.id, asset_id: c.asset_id, brand_id: c.brand_id, revision_number: c.revision_number, parent_submission_id: c.parent_submission_id, title: c.title,
      created_by: c.submitted_by, created_at: c.created_at, change_note: c.change_note, char_count: c.content.length, content_hash: c.content_hash,
      workflow_status: c.workflow_status, is_latest: c.is_latest, review_count: (this.runs[c.id] ?? []).length,
      latest_review: run ? { id: run.id, status: run.status, analysis_mode: run.analysis_mode, started_at: run.started_at, completed_at: run.completed_at, counts: run.counts } : null,
      decision: decision ? { id: decision.id, action: decision.action, actor: decision.actor, actor_role: decision.actor_role, rationale: decision.rationale, review_run_id: decision.review_run_id, created_at: decision.created_at } : null,
      correction_count: 0, open_impact_count: 0,
    };
  }

  private closeImpact(id: string, action: "resolved" | "dismissed", actor: string, rationale: string, submissionId: string | null) {
    const impact = this.impacts.find((i) => i.id === id)!;
    const sub = this.contents.find((c) => c.id === submissionId);
    impact.status = action;
    impact.resolution = { action, actor, rationale, created_at: "2026-10-23T12:00:00Z", resolving_submission_id: submissionId, resolving_revision_number: sub?.revision_number ?? null, resolving_review_run_id: sub ? (this.runs[sub.id] ?? [])[0]?.id ?? null : null };
    if (this.impactDetails[id]) Object.assign(this.impactDetails[id], { status: action, resolution: impact.resolution });
    const record: ImpactResolution = { id: this.id(), impact_id: id, action, from_status: "needs_review", to_status: action, actor, actor_role: "reviewer", rationale, resolving_submission_id: submissionId, resolving_revision_number: sub?.revision_number ?? null, resolving_review_run_id: impact.resolution.resolving_review_run_id, decision_event_id: null, created_at: "2026-10-23T12:00:00Z" };
    return record;
  }

  addBrand(name = "Nova Systems"): Brand {
    const b: Brand = { id: this.id(), name, description: "Fictional brand", created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z" };
    this.brands.push(b);
    return b;
  }

  addDoc(brandId: string, over: Partial<SourceDocument> = {}): SourceDocument {
    const d: SourceDocument = {
      id: this.id(), brand_id: brandId, title: "Nova spec", filename: "spec.pdf", mime_type: "application/pdf", size_bytes: 2048,
      source_type: "pdf", processing_status: "processed", content_hash: "a".repeat(64), page_count: 3, section_count: 3, char_count: 900,
      fact_count: 0, uploaded_at: "2026-10-02T00:00:00Z", processed_at: "2026-10-02T00:00:01Z", error_message: null, archived_at: null, ...over,
    };
    this.docs.push(d);
    this.sections[d.id] = [1, 2, 3].map((p) => ({
      id: this.id(), document_id: d.id, section_index: p - 1, kind: "page", page_number: p, line_start: null, line_end: null, row_start: null, row_end: null,
      text: p === 2 ? "Battery life: up to 18 hours under specified test conditions." : `Page ${p} text.`, meta: null,
    }));
    return d;
  }

  addFact(brandId: string, over: Partial<Fact> = {}): Fact {
    const f: Fact = {
      id: this.id(), brand_id: brandId, name: "Battery life", value: "Up to 18 hours", category: "product_spec", qualifications: "Under specified test conditions",
      unit: null, status: "active", effective_state: "current", review_state: "scheduled", warnings: [], source_document_id: null, source_page: null,
      source_excerpt: null, source_excerpt_verified: null, source_note: "Confirmed by product team", provenance: "manual", source: null, owner: "Product team",
      valid_from: null, review_date: "2027-01-01", expires_at: "2027-06-01", approved_by: "Meenal", approved_at: "2026-10-01T00:00:00Z", version: 1,
      created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z", ...over,
    };
    this.facts.push(f);
    return f;
  }

  makeEvidence(over: Partial<Evidence> = {}): Evidence {
    return {
      id: this.id(), role: "supports", fact_id: this.id(), source_document_id: null, document_section_id: null, source_title: null, source_page: null,
      excerpt: null, excerpt_verified: null, fact_name: "Battery life", fact_value: "Up to 18 hours", fact_qualifications: "Under specified test conditions",
      fact_status: "active", fact_effective_state: "current", fact_version: 1, relation_note: null, ...over,
    };
  }

  makeFinding(runId: string, content: string, claim: string, over: Partial<Finding> = {}): Finding {
    const start = content.indexOf(claim);
    return {
      id: this.id(), review_run_id: runId, claim_index: 0, claim_text: claim, claim_category: "quantitative", start_offset: start, end_offset: start + claim.length,
      status: "supported", severity: "low", explanation: "Current approved fact supports this claim.", recommended_action: null, requires_human_review: false,
      method: "deterministic", extraction_method: "deterministic", matched_fact_id: null, evidence: [], created_at: "2026-10-22T00:00:00Z", ...over,
    };
  }

  /** Adds an impact (and its detail) as the real backend would return it for a changed fact. */
  addImpact(brandId: string, over: Partial<Impact> & { detail?: Partial<ImpactDetail> } = {}): Impact {
    const { detail, ...rest } = over;
    const factId = rest.fact?.id ?? this.id();
    const contentId = rest.content?.id ?? this.id();
    const impact: Impact = {
      id: this.id(), brand_id: brandId, status: "needs_review", trigger_type: "fact_revision", change_type: "material_edit",
      headline: "Battery life: value changed from \"Up to 18 hours\" to \"Up to 14 hours\"", reason: "Battery life: value changed. This content was reviewed against an earlier version of this fact that is no longer the current approved evidence. Another review is recommended.",
      detected_at: "2026-10-23T09:00:00Z",
      fact: { id: factId, name: "Battery life", status: "proposed", effective_state: "unapproved", version: 2, value: "Up to 14 hours", unit: null },
      previous_fact_version: 1, current_fact_version: 2, previous_value: "Up to 18 hours", current_value: "Up to 14 hours",
      content: this.contentBrief("Summer Campaign Advertisement", { id: contentId }),
      source_review_run_id: this.id(), source_review_started_at: "2026-10-20T00:00:05Z", affected_claim: "Battery life lasts up to 18 hours", affected_finding_count: 1,
      latest_review_started_at: "2026-10-20T00:00:05Z", reviewed_since_detection: false, resolution: null, ...rest,
    };
    this.impacts.push(impact);
    const runId = impact.source_review_run_id;
    const finding = this.makeFinding(runId, impact.affected_claim ?? "claim", impact.affected_claim ?? "claim", {
      matched_fact_id: factId,
      evidence: [this.makeEvidence({ fact_id: factId, fact_value: impact.previous_value, fact_version: impact.previous_fact_version, excerpt: "Battery life: up to 18 hours under specified test conditions.", source_title: "Nova spec", source_page: 2 })],
    });
    this.impactDetails[impact.id] = {
      ...impact, change_summary: { material_fields: ["value"] },
      previous_snapshot: { name: impact.fact.name, value: impact.previous_value, unit: null, qualifications: "Under specified test conditions", version: impact.previous_fact_version },
      new_snapshot: { name: impact.fact.name, value: impact.current_value, unit: null },
      current_fact: this.addFact(brandId, { id: factId, name: impact.fact.name, value: impact.current_value, version: impact.fact.version, status: impact.fact.status, effective_state: impact.fact.effective_state }),
      trigger_revision: impact.trigger_type === "fact_revision" ? { id: this.id(), revision_number: 2, action: "updated", changes: {}, changed_by: "Meenal", change_reason: "Test results revised", created_at: "2026-10-23T09:00:00Z" } : null,
      findings: [{ finding, match_basis: "evidence", relied_fact_version: impact.previous_fact_version,
        review_run: { id: runId, status: "completed_limited", analysis_mode: "limited", started_at: impact.source_review_started_at, completed_at: impact.source_review_started_at, counts: { supported: 1 } } }],
      ...detail,
    };
    return impact;
  }

  private json(status: number, body: unknown) {
    return new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }

  private error(status: number, code: string, message: string, details: { field: string; message: string }[] = []) {
    return this.json(status, { error: { code, message, details, request_id: "test" } });
  }

  private summary(brandId: string) {
    const f = this.facts.filter((x) => x.brand_id === brandId);
    const by = (k: keyof Fact, v: string) => f.filter((x) => x[k] === v).length;
    return {
      total: f.length, review_warning_days: 30,
      by_effective_state: { current: by("effective_state", "current"), pending: 0, expired: by("effective_state", "expired"), unapproved: by("effective_state", "unapproved"), retired: 0 },
      by_review_state: { overdue: by("review_state", "overdue"), due_soon: by("review_state", "due_soon"), scheduled: by("review_state", "scheduled"), unscheduled: 0, not_applicable: 0 },
    };
  }

  handler = async (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
    const url = new URL(String(input), "http://localhost");
    const method = (init.method ?? "GET").toUpperCase();
    const body = init.body instanceof FormData ? init.body : init.body ? JSON.parse(String(init.body)) : undefined;
    const headers = Object.fromEntries(new Headers(init.headers as HeadersInit | undefined).entries());
    const role = headers["x-actor-role"];
    const name = headers["x-actor-name"];
    this.calls.push({ method, url: url.pathname + url.search, body, headers });
    if (this.failNext) {
      const f = this.failNext;
      this.failNext = null;
      if (f === "network") throw new TypeError("Failed to fetch");
      return this.error(f.status, f.code, f.message, f.details);
    }
    const p = url.pathname.replace(/^\/api/, "");
    let m: RegExpMatchArray | null;
    if (p === "/health") return this.json(200, { status: "ok", service: "brandpr-api", version: "0.1.0", environment: "test" });
    if (p === "/brands" && method === "GET") return this.json(200, { items: this.brands, total: this.brands.length, limit: 200, offset: 0 });
    if (p === "/brands" && method === "POST") {
      const b = this.addBrand(body.name);
      return this.json(201, b);
    }
    if ((m = p.match(/^\/brands\/([^/]+)\/documents$/))) {
      if (method === "GET") {
        const items = this.docs.filter((d) => d.brand_id === m![1] && (url.searchParams.get("include_archived") === "true" || !d.archived_at));
        return this.json(200, { items, total: items.length, limit: 200, offset: 0 });
      }
      const file = (body as FormData).get("file") as File;
      const d = this.addDoc(m[1], { title: ((body as FormData).get("title") as string) || file.name, filename: file.name, ...(this.uploadResult ?? {}) });
      return this.json(201, d);
    }
    if ((m = p.match(/^\/documents\/([^/]+)$/))) {
      const d = this.docs.find((x) => x.id === m![1]);
      return d ? this.json(200, d) : this.error(404, "not_found", "Document not found.");
    }
    if ((m = p.match(/^\/documents\/([^/]+)\/sections$/))) {
      const page = url.searchParams.get("page_number");
      const items = (this.sections[m[1]] ?? []).filter((s) => !page || s.page_number === Number(page));
      return this.json(200, { items, total: items.length, limit: 200, offset: 0 });
    }
    if ((m = p.match(/^\/brands\/([^/]+)\/fact-change-impacts\/summary$/))) {
      const all = this.impacts.filter((i) => i.brand_id === m![1]);
      const mine = all.filter((i) => i.status === "needs_review");
      const distinct = (xs: Impact[], k: (i: Impact) => string) => new Set(xs.map(k)).size;
      return this.json(200, {
        open_impacts: mine.length, resolved_impacts: all.filter((i) => i.status === "resolved").length, dismissed_impacts: all.filter((i) => i.status === "dismissed").length, total_impacts: all.length, facts_with_changes: distinct(mine, (i) => i.fact.id), content_needing_review: distinct(mine, (i) => i.content.id),
        expiry_affected_content: distinct(mine.filter((i) => i.trigger_type === "fact_expiry"), (i) => i.content.id),
        revision_affected_content: distinct(mine.filter((i) => i.trigger_type === "fact_revision"), (i) => i.content.id),
      });
    }
    if ((m = p.match(/^\/brands\/([^/]+)\/fact-change-impacts$/))) {
      const trig = url.searchParams.get("trigger_type");
      const fact = url.searchParams.get("fact_id");
      const st = url.searchParams.get("status");
      const limit = Number(url.searchParams.get("limit") ?? 50);
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const all = this.impacts.filter((i) => i.brand_id === m![1] && (!trig || i.trigger_type === trig) && (!fact || i.fact.id === fact) && (!st || i.status === st));
      return this.json(200, { items: all.slice(offset, offset + limit), total: all.length, limit, offset });
    }
    if ((m = p.match(/^\/fact-change-impacts\/([^/]+)$/))) {
      const d = this.impactDetails[m[1]];
      return d ? this.json(200, d) : this.error(404, "not_found", "Impact not found.");
    }
    if ((m = p.match(/^\/brands\/([^/]+)\/facts\/summary$/))) return this.json(200, this.summary(m[1]));
    if ((m = p.match(/^\/brands\/([^/]+)\/facts$/))) {
      if (method === "GET") {
        const q = (url.searchParams.get("q") ?? "").toLowerCase();
        const eff = url.searchParams.get("effective_state");
        const items = this.facts.filter((f) => f.brand_id === m![1] && (!q || f.name.toLowerCase().includes(q) || f.value.toLowerCase().includes(q)) && (!eff || f.effective_state === eff));
        return this.json(200, { items, total: items.length, limit: 25, offset: 0 });
      }
      const f = this.addFact(m[1], {
        ...body, status: body.status, effective_state: body.status === "active" ? "current" : "unapproved", approved_at: body.status === "active" ? "2026-10-22T00:00:00Z" : null,
        provenance: body.source_document_id ? "document" : "manual", review_state: "unscheduled",
      });
      return this.json(201, f);
    }
    if ((m = p.match(/^\/facts\/([^/]+)\/revisions$/))) return this.json(200, [{ id: this.id(), fact_id: m[1], revision_number: 1, action: "created", changes: {}, snapshot: {}, changed_by: "Meenal", change_reason: null, created_at: "2026-10-01T00:00:00Z" }]);
    if ((m = p.match(/^\/facts\/([^/]+)\/status$/))) {
      const f = this.facts.find((x) => x.id === m![1])!;
      f.status = body.status;
      f.effective_state = body.status === "active" ? "current" : body.status === "expired" ? "expired" : body.status === "retired" ? "retired" : "unapproved";
      f.version += 1;
      return this.json(200, f);
    }
    if ((m = p.match(/^\/facts\/([^/]+)$/)) && method === "PATCH") {
      const f = this.facts.find((x) => x.id === m![1])!;
      const { actor: _a, change_reason: _r, expected_version: _v, ...fields } = body;
      Object.assign(f, fields);
      f.version += 1;
      return this.json(200, f);
    }
    if ((m = p.match(/^\/brands\/([^/]+)\/content$/))) {
      if (method === "GET") {
        const items = this.contents.filter((c) => c.brand_id === m![1] && (url.searchParams.get("latest_only") !== "true" || c.is_latest)).map((c) => ({
          id: c.id, brand_id: c.brand_id, asset_id: c.asset_id, revision_number: c.revision_number, workflow_status: c.workflow_status, is_latest: c.is_latest, title: c.title, char_count: c.content.length, submitted_by: c.submitted_by, created_at: c.created_at,
          review_count: (this.runs[c.id] ?? []).length, latest_review: null,
        }));
        return this.json(200, { items, total: items.length, limit: 50, offset: 0 });
      }
      const details = [] as { field: string; message: string }[];
      if (!String(body.title ?? "").trim()) details.push({ field: "title", message: "Must not be blank." });
      if (!String(body.content ?? "").trim()) details.push({ field: "content", message: "Must not be blank." });
      if (details.length) return this.error(422, "validation_error", "The request data is invalid.", details);
      const item: ContentItem = {
        id: this.id(), brand_id: m[1], asset_id: this.id(), revision_number: 1, parent_submission_id: null, workflow_status: "draft", is_latest: true, change_note: null,
        title: body.title, content: body.content, content_hash: "b".repeat(64), submitted_by: body.submitted_by ?? null,
        created_at: "2026-10-22T10:00:00Z", updated_at: "2026-10-22T10:00:00Z", review_count: 0, latest_review: null,
      };
      this.contents.push(item);
      return this.json(201, item);
    }
    if ((m = p.match(/^\/content\/([^/]+)\/revisions$/))) {
      const item = this.contents.find((c) => c.id === m![1]);
      if (!item) return this.error(404, "not_found", "Content not found.");
      if (method === "GET") {
        const items = this.contents.filter((c) => c.asset_id === item.asset_id).sort((a, b) => a.revision_number - b.revision_number).map((c) => this.revisionOf(c));
        return this.json(200, { asset_id: item.asset_id, brand_id: item.brand_id, title: item.title, latest_revision_id: items[items.length - 1].id, items });
      }
      if (!name || !role) return this.error(401, "actor_required", "This action needs an actor.");
      const latest = this.latestOf(item);
      if (latest.id !== item.id) return this.error(409, "revision_conflict", `A newer revision (revision ${latest.revision_number}) already exists for this content.`, [{ field: "latest_revision_id", message: latest.id }]);
      const next: ContentItem = {
        ...item, id: this.id(), revision_number: item.revision_number + 1, parent_submission_id: item.id, workflow_status: "draft", is_latest: true, change_note: body.change_note ?? null,
        title: body.title ?? item.title, content: body.content, content_hash: "d".repeat(64), submitted_by: name, created_at: "2026-10-22T12:00:00Z", review_count: 0, latest_review: null,
      };
      item.is_latest = false;
      this.contents.push(next);
      this.pushEvent(next, "created", "draft", null, name, role as "creator" | "reviewer", body.change_note ?? null);
      return this.json(201, next);
    }
    if ((m = p.match(/^\/content\/([^/]+)\/workflow$/))) {
      const item = this.contents.find((c) => c.id === m![1]);
      return item ? this.json(200, this.workflowOf(item, role, name)) : this.error(404, "not_found", "Content not found.");
    }
    if ((m = p.match(/^\/content\/([^/]+)\/submit-review$/))) {
      const item = this.contents.find((c) => c.id === m![1])!;
      if (!name || !role) return this.error(401, "actor_required", "This action needs an actor.");
      const ready = this.readiness(item);
      if (!ready.ready_for_decision) return this.error(409, "review_required", ready.reasons[0]);
      item.workflow_status = "in_review";
      this.pushEvent(item, "submitted", "in_review", "draft", name, role as "creator" | "reviewer");
      return this.json(200, this.workflowOf(item, role, name));
    }
    if ((m = p.match(/^\/content\/([^/]+)\/decisions$/))) {
      const item = this.contents.find((c) => c.id === m![1])!;
      if (role !== "reviewer") return this.error(403, "reviewer_role_required", "Only a reviewer can do this.");
      if (item.workflow_status !== "in_review") return this.error(409, "invalid_transition", "A decision can only be recorded on a revision that is in review.");
      const ready = this.readiness(item);
      if (body.action === "approve") {
        if (!ready.ready_for_decision) return this.error(409, "review_failed", ready.reasons[0]);
        const missing = ready.blocking_findings.filter((b) => !(body.overrides ?? []).some((o: { finding_id: string; reason: string }) => o.finding_id === b.finding_id && o.reason.trim()));
        if (missing.length) return this.error(409, "high_risk_unresolved", "High-risk findings must be fixed in a new revision, or accepted by a reviewer with a recorded reason.");
      } else if (!String(body.rationale ?? "").trim()) return this.error(422, "validation_error", "A reason is required.", [{ field: "rationale", message: "Explain why." }]);
      const to = ({ approve: "approved", request_changes: "changes_requested", reject: "rejected" } as const)[body.action as "approve" | "request_changes" | "reject"];
      item.workflow_status = to;
      this.pushEvent(item, to, to, "in_review", name!, "reviewer", body.rationale ?? null);
      return this.json(201, this.workflowOf(item, role, name));
    }
    if ((m = p.match(/^\/findings\/([^/]+)\/suggest-correction$/))) {
      if (!this.suggestResponder) return this.error(503, "ai_unavailable", "No AI provider is configured (LLM_API_KEY is empty), so suggested corrections are unavailable. You can still correct the text manually.");
      const finding = Object.values(this.findingsByRun).flat().find((f) => f.id === m![1])!;
      return this.json(200, {
        finding_id: finding.id, review_run_id: finding.review_run_id, start_offset: finding.start_offset, end_offset: finding.end_offset, original_text: finding.claim_text, replacement_text: null,
        rationale: "Matches the approved fact.", cannot_suggest_reason: null, evidence_fact_ids: [], warnings: ["AI-generated: check the wording against the evidence before accepting."],
        requires_human_review: true, source: "ai", provider_name: "fake", model_name: "fake-model", ...this.suggestResponder(finding),
      });
    }
    if ((m = p.match(/^\/fact-change-impacts\/([^/]+)\/history$/))) {
      const impact = this.impacts.find((i) => i.id === m![1]);
      if (!impact) return this.error(404, "not_found", "Impact not found.");
      const item = this.contents.find((c) => c.id === impact.content.id)!;
      const revs = this.contents.filter((c) => c.asset_id === item.asset_id).sort((a, b) => a.revision_number - b.revision_number).map((c) => this.revisionOf(c));
      return this.json(200, {
        impact_id: impact.id, status: impact.status, detected_at: impact.detected_at, affected_submission_id: item.id, affected_revision_number: item.revision_number, asset_id: item.asset_id,
        latest_revision_id: revs[revs.length - 1].id, latest_revision_number: revs[revs.length - 1].revision_number, resolutions: [], revisions: revs,
        events: this.events.filter((e) => revs.some((r) => r.id === e.submission_id)),
      });
    }
    if ((m = p.match(/^\/fact-change-impacts\/([^/]+)\/(resolve|dismiss)$/))) {
      if (role !== "reviewer") return this.error(403, "reviewer_role_required", "Only a reviewer can close an impact.");
      const impact = this.impacts.find((i) => i.id === m![1])!;
      if (impact.status !== "needs_review") return this.error(409, "impact_not_open", `This impact is already ${impact.status}.`);
      if (!String(body.rationale ?? "").trim()) return this.error(422, "validation_error", "A rationale is required.", [{ field: "rationale", message: "A rationale is required." }]);
      if (m[2] === "resolve") {
        const sub = this.contents.find((c) => c.id === body.resolving_submission_id);
        if (!sub || sub.workflow_status !== "approved") return this.error(409, "revision_not_approved", "The revision is not approved, so it cannot resolve an impact.");
      }
      return this.json(200, this.closeImpact(impact.id, m[2] === "resolve" ? "resolved" : "dismissed", name!, body.rationale, m[2] === "resolve" ? body.resolving_submission_id : null));
    }
    if ((m = p.match(/^\/content\/([^/]+)\/reviews$/))) {
      const item = this.contents.find((c) => c.id === m![1]);
      if (!item) return this.error(404, "not_found", "Content not found.");
      if (method === "GET") return this.json(200, this.runs[item.id] ?? []);
      if (!this.reviewResponder) throw new Error("FakeApi.reviewResponder is not set");
      const { run: over, findings } = this.reviewResponder(item);
      const run: ReviewRun = {
        id: this.id(), brand_id: item.brand_id, content_submission_id: item.id, status: "completed", analysis_mode: "full", content_hash: item.content_hash,
        requested_by: body?.requested_by ?? null, started_at: "2026-10-22T10:00:01Z", completed_at: "2026-10-22T10:00:02Z", provider_name: "fake", model_name: "fake-model",
        error_code: null, error_message: null, counts: {}, limitations: [], notes: [], total_findings: findings.length, findings: null, ...over,
      };
      const counts: Record<string, number> = { supported: 0, unsupported: 0, conflicting: 0, outdated: 0, uncertain: 0 };
      findings.forEach((f) => { f.review_run_id = run.id; counts[f.status] += 1; });
      run.counts = { ...counts, ...over.counts };
      this.runs[item.id] = [{ ...run, findings: null }, ...(this.runs[item.id] ?? [])];
      this.findingsByRun[run.id] = findings;
      return this.json(201, { ...run, findings });
    }
    if ((m = p.match(/^\/content\/([^/]+)$/))) {
      const item = this.contents.find((c) => c.id === m![1]);
      return item ? this.json(200, item) : this.error(404, "not_found", "Content not found.");
    }
    if ((m = p.match(/^\/reviews\/([^/]+)\/findings$/))) {
      const items = this.findingsByRun[m[1]] ?? [];
      return this.json(200, { items, total: items.length, limit: 200, offset: 0 });
    }
    return this.error(404, "not_found", `No fake route for ${method} ${p}`);
  };

  install() {
    vi.stubGlobal("fetch", vi.fn(this.handler));
    return this;
  }
}
