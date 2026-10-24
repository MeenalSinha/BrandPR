import type {
  ApiErrorDetail, Brand, DocumentSection, Fact, FactCreateInput, FactRevision, FactStatusInput, FactSummary,
  FactUpdateInput, Health, Page, SourceDocument, TableData,
  ContentCreateInput, ContentItem, ContentSummary, Finding, ReviewRun,
  Impact, ImpactDetail, ImpactHistory, ImpactResolution, ImpactSummary, ActorRole,
  DecisionInput, FindingDetail, RevisionCreateInput, RevisionHistory, Suggestion, Workflow,
  GuidelineRule, GuidelineRuleVersion, GuidelineLintIssue, PolicySimulation, PolicySimulationDetail, GovernanceInsights,
} from "@/types/api";

// Same-origin by default: Next.js proxies /api/* to the backend. Override only with a public, non-secret URL.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: ApiErrorDetail[] = [],
    public requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Message for one form field, if the server reported one. */
  fieldMessage(field: string): string | undefined {
    return this.details.find((d) => d.field === field)?.message;
  }
}

/** Demo identity sent with workflow calls. NOT authentication: the backend enforces roles, but anyone can claim one. */
let identity: { name: string; role: ActorRole } = { name: "", role: "creator" };
export function setIdentity(name: string, role: ActorRole) { identity = { name: name.trim(), role }; }
export function getIdentity() { return identity; }
const actorHeaders = (): Record<string, string> => (identity.name ? { "X-Actor-Name": identity.name, "X-Actor-Role": identity.role } : {});

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}), ...init.headers },
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the BrandPR API. Check that the backend is running and try again.");
  }
  if (response.status === 204) return undefined as T;
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* non-JSON body */
  }
  if (!response.ok) {
    const err = (body as { error?: { code?: string; message?: string; details?: ApiErrorDetail[]; request_id?: string } } | null)?.error;
    throw new ApiError(
      response.status, err?.code ?? "http_error", err?.message ?? `The server returned an unexpected error (${response.status}).`,
      err?.details ?? [], err?.request_id ?? null,
    );
  }
  return body as T;
}

const json = (method: string, data: unknown): RequestInit => ({ method, body: JSON.stringify(data) });
const qs = (params: Record<string, string | number | boolean | undefined | null>) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
};

export const api = {
  health: () => request<Health>("/health"),
  listBrands: () => request<Page<Brand>>("/brands?limit=200"),
  createBrand: (data: { name: string; description?: string | null }) => request<Brand>("/brands", json("POST", data)),

  listDocuments: (brandId: string, opts: { includeArchived?: boolean } = {}) =>
    request<Page<SourceDocument>>(`/brands/${brandId}/documents${qs({ limit: 200, include_archived: opts.includeArchived })}`),
  uploadDocument: (brandId: string, file: File, title?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (title?.trim()) form.append("title", title.trim());
    return request<SourceDocument>(`/brands/${brandId}/documents`, { method: "POST", body: form });
  },
  getDocument: (id: string) => request<SourceDocument>(`/documents/${id}`),
  getSections: (id: string, page?: number) => request<Page<DocumentSection>>(`/documents/${id}/sections${qs({ page_number: page, limit: 200 })}`),
  getTable: (id: string, offset = 0, limit = 100) => request<TableData>(`/documents/${id}/table${qs({ offset, limit })}`),
  archiveDocument: (id: string) => request<SourceDocument>(`/documents/${id}/archive`, { method: "POST" }),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  fileUrl: (id: string, inline = false, page?: number) => `${API_BASE}/documents/${id}/file${inline ? "?inline=true" : ""}${inline && page ? `#page=${page}` : ""}`,

  listFacts: (brandId: string, p: Record<string, string | number | undefined>) => request<Page<Fact>>(`/brands/${brandId}/facts${qs(p)}`),
  factSummary: (brandId: string) => request<FactSummary>(`/brands/${brandId}/facts/summary`),
  createFact: (brandId: string, data: FactCreateInput) => request<Fact>(`/brands/${brandId}/facts`, json("POST", data)),
  getFact: (id: string) => request<Fact>(`/facts/${id}`),
  updateFact: (id: string, data: FactUpdateInput) => request<Fact>(`/facts/${id}`, json("PATCH", data)),
  setFactStatus: (id: string, data: FactStatusInput) => request<Fact>(`/facts/${id}/status`, json("PATCH", data)),
  factRevisions: (id: string) => request<FactRevision[]>(`/facts/${id}/revisions`),

  listContent: (brandId: string) => request<Page<ContentSummary>>(`/brands/${brandId}/content?limit=50`),
  createContent: (brandId: string, data: ContentCreateInput) => request<ContentItem>(`/brands/${brandId}/content`, json("POST", data)),
  getContent: (id: string) => request<ContentItem>(`/content/${id}`),
  startReview: (contentId: string, requestedBy?: string | null) => request<ReviewRun>(`/content/${contentId}/reviews`, json("POST", { requested_by: requestedBy || null })),
  listReviews: (contentId: string) => request<ReviewRun[]>(`/content/${contentId}/reviews`),
  getReview: (id: string) => request<ReviewRun>(`/reviews/${id}`),
  listImpacts: (brandId: string, p: Record<string, string | number | undefined> = {}) =>
    request<Page<Impact>>(`/brands/${brandId}/fact-change-impacts${qs(p)}`),
  impactSummary: (brandId: string) => request<ImpactSummary>(`/brands/${brandId}/fact-change-impacts/summary`),
  factImpacts: (factId: string) => request<Page<Impact>>(`/facts/${factId}/impacts?limit=200`),
  getImpact: (id: string) => request<ImpactDetail>(`/fact-change-impacts/${id}`),
  listLatestContent: (brandId: string) => request<Page<ContentSummary>>(`/brands/${brandId}/content?limit=50&latest_only=true`),
  revisions: (contentId: string) => request<RevisionHistory>(`/content/${contentId}/revisions`),
  createRevision: (contentId: string, data: RevisionCreateInput) =>
    request<ContentItem>(`/content/${contentId}/revisions`, { ...json("POST", data), headers: actorHeaders() }),
  workflow: (contentId: string) => request<Workflow>(`/content/${contentId}/workflow`, { headers: actorHeaders() }),
  submitForReview: (contentId: string) => request<Workflow>(`/content/${contentId}/submit-review`, { method: "POST", headers: actorHeaders() }),
  decide: (contentId: string, data: DecisionInput) => request<Workflow>(`/content/${contentId}/decisions`, { ...json("POST", data), headers: actorHeaders() }),
  getFinding: (id: string) => request<FindingDetail>(`/findings/${id}`),
  suggestCorrection: (id: string) => request<Suggestion>(`/findings/${id}/suggest-correction`, { method: "POST", headers: actorHeaders() }),
  resolveImpact: (id: string, data: { resolving_submission_id: string; rationale: string }) =>
    request<ImpactResolution>(`/fact-change-impacts/${id}/resolve`, { ...json("POST", data), headers: actorHeaders() }),
  dismissImpact: (id: string, rationale: string) =>
    request<ImpactResolution>(`/fact-change-impacts/${id}/dismiss`, { ...json("POST", { rationale }), headers: actorHeaders() }),
  impactHistory: (id: string) => request<ImpactHistory>(`/fact-change-impacts/${id}/history`),
  reviewFindings: (id: string) => request<Page<Finding>>(`/reviews/${id}/findings?limit=200`),

  // Phase 5: Guidelines, Policy Sandbox & Governance Intelligence
  listGuidelines: (brandId: string, status?: string) =>
    request<Page<GuidelineRule>>(`/brands/${brandId}/guidelines${qs({ status, limit: 200 })}`),
  getGuideline: (id: string) => request<GuidelineRule>(`/guidelines/${id}`),
  createGuideline: (brandId: string, data: {
    title: string;
    rule_text: string;
    category?: string;
    severity?: string;
    scope?: string | null;
    conditions?: Record<string, unknown> | null;
    status?: string;
    source_document_id?: string | null;
    source_page?: number | null;
    source_excerpt?: string | null;
    owner?: string | null;
  }) => request<GuidelineRule>(`/brands/${brandId}/guidelines`, { ...json("POST", data), headers: actorHeaders() }),
  updateGuideline: (id: string, data: {
    title?: string;
    rule_text?: string;
    status?: string;
    category?: string;
    severity?: string;
    scope?: string | null;
    conditions?: Record<string, unknown> | null;
    source_excerpt?: string | null;
    owner?: string | null;
    change_reason?: string | null;
    expected_version?: number | null;
  }) => request<GuidelineRule>(`/guidelines/${id}`, { ...json("PATCH", data), headers: actorHeaders() }),
  extractGuidelines: (brandId: string, data: { source_document_id: string }) =>
    request<{ extracted_count: number; proposed_rules: GuidelineRule[] }>(
      `/brands/${brandId}/guidelines/extract`,
      { ...json("POST", data), headers: actorHeaders() },
    ),
  getGuidelineVersions: (id: string) => request<GuidelineRuleVersion[]>(`/guidelines/${id}/versions`),
  proposeGuidelineVersion: (id: string, data: {
    rule_text: string;
    conditions?: Record<string, unknown> | null;
    examples?: Record<string, unknown> | null;
    source_reference?: string | null;
    change_reason: string;
  }) => request<GuidelineRuleVersion>(`/guidelines/${id}/versions`, { ...json("POST", data), headers: actorHeaders() }),
  runGuidelineLint: (brandId: string) =>
    request<{ total_issues: number; issues: GuidelineLintIssue[] }>(
      `/brands/${brandId}/guideline-lint`,
      { method: "POST", headers: actorHeaders() },
    ),
  getGuidelineLintResults: (brandId: string) =>
    request<Page<GuidelineLintIssue>>(`/brands/${brandId}/guideline-lint-results?limit=200`),
  listPolicySimulations: (brandId: string) =>
    request<Page<PolicySimulation>>(`/brands/${brandId}/policy-simulations?limit=100`),
  createPolicySimulation: (brandId: string, data: {
    rule_id: string;
    proposed_rule_text: string;
    proposed_conditions?: Record<string, unknown> | null;
    sample_content_ids?: string[] | null;
  }) => request<PolicySimulationDetail>(`/brands/${brandId}/policy-simulations`, { ...json("POST", data), headers: actorHeaders() }),
  getPolicySimulation: (id: string) => request<PolicySimulationDetail>(`/policy-simulations/${id}`),
  getGovernanceInsights: (brandId: string, period = "all") =>
    request<GovernanceInsights>(`/brands/${brandId}/insights${qs({ period })}`),
};

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : "Something went wrong.";
}
