"use client";
import Link from "next/link";
import { useState } from "react";

import { EventList, WorkflowBadge } from "@/components/workflowUi";

import { Dialog, EffectiveBadge, EmptyState, Loading, Notice } from "@/components/ui";
import { useBrand, useToast } from "@/components/providers";
import { api, ApiError, errorMessage } from "@/lib/api";
import { CHANGE_LABELS, FINDING_LABELS, formatDate, IMPACT_STATUS_LABELS, ROLE_LABELS, TRIGGER_LABELS } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { Impact, ImpactDetail, ImpactStatus, ImpactTrigger } from "@/types/api";

const PAGE = 10;

function SummaryCards({ brandId }: { brandId: string }) {
  const summary = useResource(() => api.impactSummary(brandId), [brandId]);
  if (summary.loading && !summary.data) return <Loading label="Loading summary" />;
  // A failed request is reported as a failure. It is never shown as zero.
  if (summary.error || !summary.data) {
    return <Notice kind="error" action={<button className="btn btn-secondary" onClick={summary.reload}>Try again</button>}>The summary could not be loaded: {errorMessage(summary.error)}</Notice>;
  }
  const s = summary.data;
  const cards: [string, number, string][] = [
    ["facts", s.facts_with_changes, "Facts with detected changes"],
    ["content", s.content_needing_review, "Content items needing review"],
    ["expiry", s.expiry_affected_content, "Items affected by expiry"],
    ["open", s.open_impacts, "Open impact records"],
    ["resolved", s.resolved_impacts, "Resolved"],
    ["dismissed", s.dismissed_impacts, "Dismissed"],
  ];
  return (
    <section aria-label="Summary">
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {cards.map(([key, n, label]) => (
          <li key={key} className="border border-rule bg-sheet px-3 py-3">
            <span data-testid={`summary-${key}`} className="block font-serif text-3xl font-semibold">{n}</span>
            <span className="text-sm font-bold">{label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ValueBox({ heading, tone, children }: { heading: string; tone: "old" | "new"; children: React.ReactNode }) {
  return (
    <div className={`border-l-4 px-4 py-3 ${tone === "old" ? "border-rule-strong bg-paper" : "border-signal bg-signal-wash"}`}>
      <h4 className="text-sm font-bold text-ink-soft">{heading}</h4>
      {children}
    </div>
  );
}

function snapshotLine(s: Record<string, unknown>): string {
  const unit = s.unit ? ` ${s.unit}` : "";
  return `${String(s.value ?? "")}${unit}`;
}

function ImpactDetailPanel({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [tick, setTick] = useState(0);
  const detail = useResource(() => api.getImpact(id), [id, tick]);
  if (detail.loading && !detail.data) return <Loading label="Loading impact" />;
  if (detail.error || !detail.data) return <Notice kind="error" action={<button className="btn btn-secondary" onClick={detail.reload}>Try again</button>}>{errorMessage(detail.error)}</Notice>;
  const d: ImpactDetail = detail.data;
  const changed = () => { setTick((t) => t + 1); onChanged(); };
  const prev = d.previous_snapshot;
  const rev = d.trigger_revision;
  return (
    <div className="space-y-5" data-testid="impact-detail">
      <div>
        <p className="text-sm font-bold text-ink-soft">{TRIGGER_LABELS[d.trigger_type]} &middot; {CHANGE_LABELS[d.change_type]} &middot; detected {formatDate(d.detected_at)}</p>
        <h3 className="mt-1 font-serif text-2xl">{d.content.title}</h3>
        <p className="mt-2" data-testid="impact-reason">{d.reason}</p>
        {d.status === "needs_review" && d.reviewed_since_detection && <p className="mt-2 text-sm font-bold text-state-current">This content has been reviewed again since this was recorded. That alone does not close the impact: it needs a corrected revision approved by a reviewer, or a documented dismissal.</p>}
      </div>

      <section aria-label="What changed" className="grid gap-3 md:grid-cols-2">
        <ValueBox heading={`Historical: version ${d.previous_fact_version}, relied on by the earlier review`} tone="old">
          <p data-testid="detail-previous" className="font-bold">{snapshotLine(prev)}</p>
          {prev.qualifications ? <p className="text-sm text-ink-soft">Conditions: {String(prev.qualifications)}</p> : null}
        </ValueBox>
        <ValueBox heading={`Current: version ${d.current_fact.version}`} tone="new">
          <p data-testid="detail-current" className="font-bold">{snapshotLine(d.current_fact as unknown as Record<string, unknown>)}</p>
          {d.current_fact.qualifications && <p className="text-sm text-ink-soft">Conditions: {d.current_fact.qualifications}</p>}
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm">Fact state now: <EffectiveBadge state={d.current_fact.effective_state} /></p>
          {d.current_fact.source?.archived && <p className="mt-1 text-sm font-bold text-state-unapproved">The cited source document is archived.</p>}
        </ValueBox>
      </section>

      <section aria-label="Change record">
        <h4 className="text-sm font-bold text-ink-soft">What changed</h4>
        <p className="mt-1">{d.headline}</p>
        {rev && (
          <p className="mt-1 text-sm text-ink-soft">
            Revision {rev.revision_number} on {formatDate(rev.created_at)}{rev.changed_by ? ` by ${rev.changed_by}` : ""}{rev.change_reason ? `. Reason given: ${rev.change_reason}` : ""}.
          </p>
        )}
      </section>

      <section aria-label="Historical claims">
        <h4 className="text-sm font-bold text-ink-soft">Claims reviewed against the earlier version ({d.findings.length})</h4>
        <ul className="mt-2 space-y-3">
          {d.findings.map((f) => (
            <li key={f.finding.id} data-testid="historical-finding" className="border border-rule bg-sheet p-4">
              <p className="font-serif text-lg">&ldquo;{f.finding.claim_text}&rdquo;</p>
              <p className="mt-1 text-sm"><strong>{FINDING_LABELS[f.finding.status]}</strong> in the review of {formatDate(f.review_run.started_at)}. {f.finding.explanation}</p>
              <p className="mt-1 text-sm text-ink-soft">
                {f.match_basis === "evidence" ? `Saved evidence cites fact version ${f.relied_fact_version}.` : `The finding names this fact without a versioned evidence record; version ${f.relied_fact_version} is inferred from the revision history.`}
              </p>
              {f.finding.evidence.filter((e) => e.fact_id === d.fact.id).map((e) => (
                <blockquote key={e.id} data-testid="historical-evidence" className="mt-2 border-l-2 border-rule-strong pl-3">
                  <span className="block text-sm font-bold text-ink-soft">{ROLE_LABELS[e.role]} as saved at review time</span>
                  <span className="font-bold">{e.fact_name}:</span> {e.fact_value}
                  {e.fact_qualifications && <span className="block text-sm text-ink-soft">Conditions: {e.fact_qualifications}</span>}
                  {e.excerpt && <span className="mt-1 block font-serif">{e.excerpt}</span>}
                  {e.source_title && <span className="block text-sm text-ink-soft">{e.source_title}{e.source_page ? `, page ${e.source_page}` : ""}</span>}
                </blockquote>
              ))}
            </li>
          ))}
        </ul>
      </section>

      <ResolutionSection impact={d} onChanged={changed} />
    </div>
  );
}

function ResolutionSection({ impact: d, onChanged }: { impact: ImpactDetail; onChanged: () => void }) {
  const { role, actor } = useBrand();
  const toast = useToast();
  const history = useResource(() => api.impactHistory(d.id), [d.id, d.status]);
  const [choice, setChoice] = useState("");
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const h = history.data;
  const open = d.status === "needs_review";
  const candidates = (h?.revisions ?? []).filter((r) => r.workflow_status === "approved" && r.revision_number > d.content.revision_number);

  async function act(kind: "resolve" | "dismiss") {
    setBusy(true);
    setError(null);
    try {
      if (kind === "resolve") await api.resolveImpact(d.id, { resolving_submission_id: choice, rationale: rationale.trim() });
      else await api.dismissImpact(d.id, rationale.trim());
      toast.push("success", kind === "resolve" ? "Impact resolved." : "Impact dismissed.");
      setRationale("");
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError && e.details.length ? `${e.message} ${e.details.map((x) => x.message).join(" ")}` : errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Resolution" data-testid="resolution-section" className="space-y-4 border-t border-rule pt-5">
      <h4 className="text-lg font-semibold">Resolution <span data-testid="detail-status" className="text-base text-ink-soft">({IMPACT_STATUS_LABELS[d.status as ImpactStatus]})</span></h4>
      <p className="text-sm text-ink-soft">Recorded against revision {d.content.revision_number} of this content. {d.content.latest_revision_number > d.content.revision_number ? `The newest revision is ${d.content.latest_revision_number} (${d.content.latest_revision_status.replace("_", " ")}).` : "No newer revision exists yet."}</p>
      {d.resolution && (
        <div data-testid="resolution-record" className="border-l-4 border-state-current bg-state-current-wash px-4 py-3">
          <p className="font-bold">{d.resolution.action === "resolved" ? "Resolved" : "Dismissed"} by {d.resolution.actor} on {formatDate(d.resolution.created_at)}</p>
          <p className="mt-1">&ldquo;{d.resolution.rationale}&rdquo;</p>
          {d.resolution.resolving_submission_id && (
            <p className="mt-1 text-sm">Closed by revision {d.resolution.resolving_revision_number}, reviewed in run {d.resolution.resolving_review_run_id?.slice(0, 8)}. <Link className="underline" href={`/review?content=${d.resolution.resolving_submission_id}`}>Open that revision</Link></p>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <Link className="btn btn-primary" href={`/review?content=${open ? d.content.latest_revision_id : d.content.id}`}>{open ? "Open the latest revision to correct it" : "Open the reviewed revision"}</Link>
        {open && d.content.latest_revision_id !== d.content.id && <Link className="btn btn-secondary" href={`/review?content=${d.content.id}`}>Open the affected revision</Link>}
      </div>

      {open && role === "reviewer" && (
        <div data-testid="resolve-form" className="space-y-3 border border-rule bg-paper p-4">
          <p className="text-sm font-bold">Reviewer decision as {actor || "(enter your name)"}</p>
          <label className="label" htmlFor="resolve-choice">Resolve with an approved, later revision</label>
          <select id="resolve-choice" className="input" value={choice} onChange={(e) => setChoice(e.target.value)} disabled={!candidates.length}>
            <option value="">{candidates.length ? "Choose a revision" : "No approved later revision yet"}</option>
            {candidates.map((r) => <option key={r.id} value={r.id}>Revision {r.revision_number} (approved)</option>)}
          </select>
          {!candidates.length && <p className="text-sm text-ink-soft">Correct the content, review it against the current fact and have it approved first. Reviewing or editing alone does not close an impact.</p>}
          <label className="label" htmlFor="resolve-rationale">Reason (required)</label>
          <textarea id="resolve-rationale" className="input" rows={2} value={rationale} onChange={(e) => setRationale(e.target.value)} />
          {error && <Notice kind="error">{error}</Notice>}
          <div className="flex flex-wrap gap-3">
            <button className="btn btn-primary" disabled={busy || !choice || !rationale.trim()} onClick={() => act("resolve")}>Resolve impact</button>
            <button className="btn btn-secondary" disabled={busy || !rationale.trim()} onClick={() => act("dismiss")}>Dismiss: no action needed</button>
          </div>
        </div>
      )}
      {open && role !== "reviewer" && <p data-testid="reviewer-only" className="text-sm text-ink-soft">Only a reviewer can resolve or dismiss an impact. Switch the demo role in the sidebar.</p>}

      {h && (
        <details>
          <summary className="cursor-pointer font-bold">History of this content ({h.revisions.length} revision{h.revisions.length === 1 ? "" : "s"})</summary>
          <ul className="mt-2 text-sm">
            {h.revisions.map((r) => <li key={r.id} className="py-1">Revision {r.revision_number} <WorkflowBadge status={r.workflow_status} /> &middot; {r.latest_review ? `latest review: ${r.latest_review.status}` : "not reviewed"}</li>)}
          </ul>
          <div className="mt-3"><EventList events={h.events} /></div>
        </details>
      )}
    </section>
  );
}

export function FactChangesView() {
  const { brand } = useBrand();
  const [offset, setOffset] = useState(0);
  const [trigger, setTrigger] = useState<"" | ImpactTrigger>("");
  const [status, setStatus] = useState<"needs_review" | "resolved" | "dismissed" | "">("needs_review");
  const [factId, setFactId] = useState("");
  const [open, setOpen] = useState<Impact | null>(null);
  const [summaryTick, setSummaryTick] = useState(0);
  const brandId = brand?.id ?? null;

  const facts = useResource(brandId ? () => api.listFacts(brandId, { limit: 200, sort: "name" }) : null, [brandId]);
  const params = { limit: PAGE, offset, status: status || undefined, trigger_type: trigger || undefined, fact_id: factId || undefined };
  const impacts = useResource(brandId ? () => api.listImpacts(brandId, params) : null, [brandId, offset, trigger, factId, status]);

  if (!brand) return <EmptyState title="Create a brand first">Fact changes are tracked per brand. Use &ldquo;New brand&rdquo; in the sidebar.</EmptyState>;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-semibold">Fact changes</h1>
        <p className="mt-1 text-ink-soft">
          Content for <span data-testid="changes-brand">{brand.name}</span> that was reviewed against an approved fact that has since changed or expired.
          Earlier reviews are never rewritten. Each item stays on record until a reviewer resolves it with an approved corrected revision, or dismisses it with a reason. Expiry is checked each time this page loads.
        </p>
      </header>

      <SummaryCards key={`${brand.id}-${impacts.data?.total ?? "x"}-${summaryTick}`} brandId={brand.id} />

      <section aria-label="Affected content" className="space-y-4">
        <div role="tablist" aria-label="Impact status" className="flex flex-wrap gap-2">
          {([["needs_review", "Needs review"], ["resolved", "Resolved"], ["dismissed", "Dismissed"], ["", "All"]] as const).map(([value, label]) => (
            <button key={value || "all"} role="tab" aria-selected={status === value} data-testid={`tab-${value || "all"}`}
                    className={`btn ${status === value ? "btn-primary" : "btn-secondary"}`} onClick={() => { setStatus(value); setOffset(0); }}>{label}</button>
          ))}
        </div>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="label" htmlFor="impact-trigger">Trigger</label>
            <select id="impact-trigger" className="input" value={trigger} onChange={(e) => { setTrigger(e.target.value as "" | ImpactTrigger); setOffset(0); }}>
              <option value="">All triggers</option>
              <option value="fact_revision">{TRIGGER_LABELS.fact_revision}</option>
              <option value="fact_expiry">{TRIGGER_LABELS.fact_expiry}</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="impact-fact">Fact</label>
            <select id="impact-fact" className="input" value={factId} onChange={(e) => { setFactId(e.target.value); setOffset(0); }}>
              <option value="">All facts</option>
              {facts.data?.items.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </div>
        </div>

        {impacts.loading && !impacts.data && <Loading label="Loading affected content" />}
        {impacts.error && (
          <Notice kind="error" action={<button className="btn btn-secondary" onClick={impacts.reload}>Try again</button>}>
            The affected content could not be loaded, so nothing is shown here. {errorMessage(impacts.error)}
          </Notice>
        )}
        {!impacts.error && impacts.data && impacts.data.total === 0 && (
          <EmptyState title={status === "needs_review" ? "No content is affected" : "Nothing here"}>
            {status === "resolved" ? "No impact has been resolved yet." : status === "dismissed" ? "No impact has been dismissed." : "No reviewed content depends on a fact that has changed or expired"}{trigger || factId ? " with these filters" : ""}. Material edits to approved facts and expiry dates are checked automatically.
          </EmptyState>
        )}
        {!impacts.error && impacts.data && impacts.data.items.length > 0 && (
          <>
            <ul className="rule-list border border-rule bg-sheet" data-testid="impact-list">
              {impacts.data.items.map((i) => (
                <li key={i.id} data-testid="impact-row" className="grid gap-3 px-4 py-4 md:grid-cols-[1.2fr_1fr_1fr_auto]">
                  <div>
                    <p className="font-bold" data-testid="impact-content">{i.content.title} <span className="text-sm font-normal text-ink-soft">revision {i.content.revision_number}</span></p>
                    <p className="text-sm text-ink-soft">{TRIGGER_LABELS[i.trigger_type]} &middot; {formatDate(i.detected_at)}</p>
                    {i.affected_claim && <p className="mt-1 font-serif text-sm" data-testid="impact-claim">&ldquo;{i.affected_claim}&rdquo;{i.affected_finding_count > 1 ? ` (+${i.affected_finding_count - 1} more)` : ""}</p>}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-ink-soft">Changed fact</p>
                    <p data-testid="impact-fact">{i.fact.name}</p>
                    <p className="text-sm text-ink-soft" data-testid="impact-reason-short">{CHANGE_LABELS[i.change_type]}</p>
                  </div>
                  <div className="text-sm">
                    <p><span className="font-bold">Previous (v{i.previous_fact_version}):</span> <span data-testid="impact-previous">{i.previous_value}</span></p>
                    <p><span className="font-bold">Current (v{i.fact.version}):</span> <span data-testid="impact-current">{i.current_value}</span></p>
                    <p className={`mt-1 font-bold ${i.status === "needs_review" ? "text-state-unapproved" : "text-state-current"}`} data-testid="impact-status">{IMPACT_STATUS_LABELS[i.status]}</p>
                    {i.resolution && <p className="text-sm text-ink-soft" data-testid="impact-resolution-line">{i.resolution.action === "resolved" ? `Resolved by revision ${i.resolution.resolving_revision_number}` : "Dismissed"} &middot; {i.resolution.actor} &middot; {formatDate(i.resolution.created_at)}</p>}
                  </div>
                  <div className="flex items-start"><button className="btn btn-secondary" onClick={() => setOpen(i)}>Inspect impact</button></div>
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-ink-soft">
              <p>Showing {offset + 1} to {Math.min(offset + PAGE, impacts.data.total)} of {impacts.data.total}</p>
              <div className="flex gap-2">
                <button className="btn btn-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                <button className="btn btn-secondary" disabled={offset + PAGE >= impacts.data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
              </div>
            </div>
          </>
        )}
      </section>

      {open && (
        <Dialog variant="drawer" title="Fact change impact" description={`${open.fact.name} · ${open.content.title}`} onClose={() => setOpen(null)}>
          <ImpactDetailPanel id={open.id} onChanged={() => { impacts.reload(); setSummaryTick((t) => t + 1); }} />
        </Dialog>
      )}
    </div>
  );
}
