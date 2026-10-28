"use client";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { Dialog, EmptyState, Field, Loading, Notice } from "@/components/ui";
import { SourceEvidence } from "@/components/SourceEvidence";
import { RevisionEditor } from "@/components/RevisionEditor";
import { RevisionHistory } from "@/components/RevisionHistory";
import { WorkflowPanel } from "@/components/WorkflowPanel";
import { WorkflowBadge } from "@/components/workflowUi";
import { useBrand, useToast } from "@/components/providers";
import { api, ApiError, errorMessage } from "@/lib/api";
import {
  CLAIM_LABELS, FINDING_HELP, FINDING_LABELS, FINDING_ORDER, formatDate, ROLE_LABELS, RUN_LABELS, segmentDraft, SEVERITY_LABELS,
} from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { ContentItem, Evidence, Finding, FindingStatus, ReviewRun } from "@/types/api";
import { IconCheck, IconAlert, IconInfo, IconExternalLink, IconReview } from "@/components/Icons";

const STATUS_STYLE: Record<FindingStatus, string> = {
  supported: "bg-state-current-wash text-state-current border-state-current-border",
  unsupported: "bg-state-unapproved-wash text-state-unapproved border-state-unapproved-border",
  conflicting: "bg-state-expired-wash text-state-expired border-state-expired-border",
  outdated: "bg-state-retired-wash text-state-retired border-state-retired-border",
  uncertain: "bg-state-pending-wash text-state-pending border-state-pending-border",
};

function FindingBadge({ status }: { status: FindingStatus }) {
  return (
    <span data-testid="finding-status" className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide ${STATUS_STYLE[status]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {FINDING_LABELS[status]}
    </span>
  );
}

interface Current { item: ContentItem; run: ReviewRun | null; findings: Finding[] }

function Draft({ item, findings, selectedId, onSelect }: { item: ContentItem; findings: Finding[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const segments = useMemo(() => segmentDraft(item.content, findings), [item.content, findings]);
  return (
    <section aria-label="Submitted draft" className="rounded-xl border border-rule bg-sheet p-6 shadow-subtle">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule/70 pb-3 mb-4">
        <h3 className="flex flex-wrap items-center gap-2.5 text-lg font-bold text-ink">
          {item.title}
          <span data-testid="revision-label" className="rounded-full bg-paper px-2.5 py-0.5 text-xs font-semibold text-ink-soft border border-rule">
            Revision {item.revision_number}
          </span>
          <WorkflowBadge status={item.workflow_status} />
        </h3>
        <p className="text-xs text-ink-faint">
          Saved {formatDate(item.created_at)}{item.submitted_by ? ` by ${item.submitted_by}` : ""}
        </p>
      </div>
      <p className="mb-4 text-xs text-ink-soft">
        Highlighted passages are claims identified by ProofGraph. Select any claim to inspect its evidence trail.
      </p>
      <div className="rounded-lg bg-paper/30 p-4 border border-rule/50">
        <p data-testid="draft-text" className="whitespace-pre-wrap font-serif text-[17px] leading-relaxed text-ink">
          {segments.map((seg, i) => {
            if (!seg.findingIds.length) return <span key={i}>{seg.text}</span>;
            const selected = selectedId !== null && seg.findingIds.includes(selectedId);
            return (
              <mark
                key={i}
                data-testid={selected ? "claim-mark-selected" : "claim-mark"}
                onClick={() => onSelect(selected ? seg.findingIds[0] : seg.findingIds[seg.findingIds.length - 1])}
                className={`cursor-pointer rounded px-1.5 py-0.5 transition-all duration-150 ${
                  selected
                    ? "bg-signal/20 text-signal-dark font-medium ring-2 ring-signal"
                    : "bg-signal-wash text-ink hover:bg-signal/15"
                }`}
              >
                {seg.text}
              </mark>
            );
          })}
        </p>
      </div>
    </section>
  );
}

function EvidenceCard({ ev, onOpen }: { ev: Evidence; onOpen: (ev: Evidence) => void }) {
  return (
    <article data-testid="evidence-item" className="rounded-lg border border-rule bg-paper/60 p-4 shadow-subtle transition-all">
      <div className="flex items-center justify-between border-b border-rule/60 pb-2 mb-2">
        <h4 className="text-xs font-bold uppercase tracking-wider text-signal">{ROLE_LABELS[ev.role]}</h4>
        <span className="text-[11px] font-medium text-ink-faint">Version {ev.fact_version}</span>
      </div>
      {ev.fact_name && (
        <div className="space-y-1">
          <p className="text-sm font-semibold text-ink">
            <strong>{ev.fact_name}:</strong> <span className="font-normal text-ink-soft">{ev.fact_value}</span>
          </p>
          {ev.fact_qualifications && (
            <p className="text-xs text-ink-soft">
              <strong className="text-ink-soft">Conditions:</strong> {ev.fact_qualifications}
            </p>
          )}
          <p className="text-[11px] text-ink-faint">
            Approved fact state at review: <span className="font-medium text-ink-soft">{ev.fact_effective_state}</span>
          </p>
        </div>
      )}
      {ev.source_title && (
        <p className="mt-2.5 text-xs text-ink-soft">
          <strong className="text-ink">Source:</strong> {ev.source_title}{ev.source_page ? `, page ${ev.source_page}` : ""}
        </p>
      )}
      {ev.excerpt && (
        <blockquote className="mt-2.5 rounded border-l-2 border-signal bg-sheet p-3 font-serif text-sm text-ink-soft leading-relaxed shadow-subtle">
          &ldquo;{ev.excerpt}&rdquo;
          {ev.excerpt_verified === false && (
            <span className="mt-1 block text-xs font-semibold text-state-expired">
              This passage was not found in the stored source text.
            </span>
          )}
        </blockquote>
      )}
      {ev.relation_note && <p className="mt-2 text-xs text-ink-faint italic">{ev.relation_note}</p>}
      {ev.source_document_id && (
        <button type="button" className="btn btn-secondary mt-3 text-xs py-1.5 min-h-[32px] gap-1.5" onClick={() => onOpen(ev)}>
          <IconExternalLink className="h-3 w-3 text-signal" />
          Open source{ev.source_page ? ` (page ${ev.source_page})` : ""}
        </button>
      )}
    </article>
  );
}

function EvidencePanel({ finding, onOpen }: { finding: Finding | null; onOpen: (ev: Evidence) => void }) {
  if (!finding) {
    return (
      <aside aria-label="Evidence" className="flex h-full min-h-[300px] flex-col items-center justify-center rounded-xl border border-dashed border-rule bg-sheet p-8 text-center text-ink-faint shadow-subtle">
        <IconReview className="h-8 w-8 mb-2 text-ink-faint/60" />
        <p className="text-sm font-medium">Select a finding to inspect its explanation and evidence.</p>
      </aside>
    );
  }
  const cited = finding.evidence.filter((e) => e.role !== "related_source");
  return (
    <aside aria-label="Evidence" data-testid="evidence-panel" className="rounded-xl border border-rule bg-sheet p-5 shadow-subtle space-y-4">
      <div className="border-b border-rule/70 pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <FindingBadge status={finding.status} />
          <span className={`rounded px-2 py-0.5 text-xs font-bold ${
            finding.severity === "high" ? "bg-state-expired-wash text-state-expired" : "bg-paper text-ink-soft"
          }`}>
            {SEVERITY_LABELS[finding.severity]}
          </span>
          <span className="text-xs font-medium text-ink-faint">{CLAIM_LABELS[finding.claim_category]}</span>
        </div>
        <h3 className="mt-2.5 font-serif text-lg font-semibold text-ink leading-snug">
          &ldquo;{finding.claim_text}&rdquo;
        </h3>
        <p className="mt-2 text-sm text-ink-soft leading-relaxed">{finding.explanation}</p>
        {finding.recommended_action && (
          <div className="mt-2.5 rounded-lg bg-paper p-2.5 text-xs text-ink-soft border border-rule/60">
            <strong className="text-ink">Suggested action:</strong> {finding.recommended_action}
          </div>
        )}
        {finding.requires_human_review && (
          <p data-testid="needs-review" className="mt-2.5 flex items-center gap-1.5 text-xs font-semibold text-terracotta">
            <IconAlert className="h-3.5 w-3.5" />
            A person must review this finding before the content is published.
          </p>
        )}
        {finding.method === "ai_assisted" && (
          <p className="mt-1 text-xs text-ink-faint">
            This finding used an AI-assisted comparison. The cited records are real; the match itself needs human confirmation.
          </p>
        )}
      </div>

      {cited.length === 0 && (
        <p data-testid="no-evidence" className="rounded-lg border-l-4 border-state-unapproved bg-state-unapproved-wash p-3.5 text-xs font-bold text-state-unapproved">
          No suitable approved evidence was found. No source is cited because none exists.
        </p>
      )}
      <div className="space-y-3">
        {finding.evidence.map((ev) => <EvidenceCard key={ev.id} ev={ev} onOpen={onOpen} />)}
      </div>
    </aside>
  );
}

function Summary({ run }: { run: ReviewRun }) {
  return (
    <section aria-label="Review summary" className="rounded-xl border border-rule bg-sheet p-4 shadow-subtle">
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {FINDING_ORDER.map((s) => {
          const count = run.counts[s] ?? 0;
          return (
            <li
              key={s}
              title={FINDING_HELP[s]}
              className={`rounded-lg border p-3.5 transition-all ${
                count > 0 ? STATUS_STYLE[s] : "border-rule/60 bg-paper/40 text-ink-faint"
              }`}
            >
              <span data-testid={`count-${s}`} className="block font-serif text-3xl font-bold tracking-tight">
                {count}
              </span>
              <span className="mt-0.5 block text-xs font-bold uppercase tracking-wider">{FINDING_LABELS[s]}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function RunBanner({ run, onRetry, busy }: { run: ReviewRun; onRetry: () => void; busy: boolean }) {
  if (run.status === "failed") {
    return (
      <Notice kind="error" action={<button className="btn btn-secondary" onClick={onRetry} disabled={busy}>Retry review</button>}>
        <span data-testid="run-failed">The review did not finish, so nothing in this draft has been verified.</span>
        <span className="block font-normal">{run.error_message ?? "The review failed."}</span>
      </Notice>
    );
  }
  if (run.status === "running" || run.status === "pending") return <Notice kind="warning">This review is still {RUN_LABELS[run.status].toLowerCase()}. It has not produced findings yet.</Notice>;
  return (
    <div className="space-y-2">
      {run.status === "completed_limited" && (
        <Notice kind="warning"><span data-testid="limited-mode">Limited analysis.</span>
          {run.limitations.map((l) => <span key={l} className="block font-normal">{l}</span>)}</Notice>
      )}
      {run.total_findings === 0 && <Notice kind="info">No claims were identified in this draft{run.status === "completed_limited" ? " by the deterministic rules" : ""}. This is a review result, not a failure.</Notice>}
      {run.notes.filter((n) => !n.startsWith("No candidate claims")).map((n) => <Notice key={n} kind="info">{n}</Notice>)}
      <p className="text-sm text-ink-soft">{RUN_LABELS[run.status]} {formatDate(run.completed_at)}{run.model_name ? ` using ${run.model_name}` : " without an AI provider"}.</p>
    </div>
  );
}

export function ReviewView() {
  const { brand, actor } = useBrand();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [errors, setErrors] = useState<{ title?: string; content?: string }>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState<Current | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [opened, setOpened] = useState<Evidence | null>(null);
  const [loadingDraft, setLoadingDraft] = useState(false);
  const [editing, setEditing] = useState(false);
  const [version, setVersion] = useState(0);
  const [latestId, setLatestId] = useState<string | null>(null);

  const history = useResource(brand ? () => api.listLatestContent(brand.id) : null, [brand?.id]);
  const selected = current?.findings.find((f) => f.id === selectedId) ?? null;

  const runReview = useCallback(async (item: ContentItem) => {
    setBusy(true);
    setError(null);
    try {
      const run = await api.startReview(item.id, actor);
      setCurrent({ item, run, findings: run.findings ?? [] });
      setSelectedId(run.findings?.[0]?.id ?? null);
      if (run.status === "failed") toast.push("error", "The review did not finish.");
      history.reload();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [actor, toast, history]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!brand) return;
    const next: typeof errors = {};
    if (!title.trim()) next.title = "Enter a title for this draft.";
    if (!body.trim()) next.content = "Paste or write the content to review.";
    setErrors(next);
    if (next.title || next.content) return;
    setBusy(true);
    setError(null);
    let item: ContentItem;
    try {
      item = await api.createContent(brand.id, { title: title.trim(), content: body, submitted_by: actor || null });
    } catch (err) {
      if (err instanceof ApiError) setErrors({ title: err.fieldMessage("title"), content: err.fieldMessage("content") });
      setError(errorMessage(err));
      setBusy(false);
      return;
    }
    setCurrent({ item, run: null, findings: [] });
    setBusy(false);
    await runReview(item);
  }

  async function openDraft(id: string) {
    setLoadingDraft(true);
    setError(null);
    setEditing(false);
    setLatestId(null);
    try {
      const [item, runs] = await Promise.all([api.getContent(id), api.listReviews(id)]);
      const latest = runs[0] ?? null;
      const findings = latest && latest.status !== "failed" ? (await api.reviewFindings(latest.id)).items : [];
      setCurrent({ item, run: latest, findings });
      setSelectedId(findings[0]?.id ?? null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoadingDraft(false);
    }
  }

  // Deep link from the Fact changes page: /review?content=<id> opens that draft with its stored review.
  useEffect(() => {
    const id = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("content");
    if (id && brand) void openDraft(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brand?.id]);

  /** Something changed on the server (a decision, a new revision): reload the open revision and the lists. */
  function refreshAll() {
    setVersion((v) => v + 1);
    history.reload();
    if (current) void api.getContent(current.item.id).then((item) => setCurrent((c) => (c && c.item.id === item.id ? { ...c, item } : c)), () => {});
  }

  function revisionSaved(item: ContentItem) {
    setEditing(false);
    setCurrent({ item, run: null, findings: [] });
    setSelectedId(null);
    setVersion((v) => v + 1);
    history.reload();
    toast.push("success", `Revision ${item.revision_number} saved. Review it next.`);
  }

  function startOver() {
    setEditing(false); setLatestId(null);
    setCurrent(null); setSelectedId(null); setTitle(""); setBody(""); setErrors({}); setError(null);
  }

  function loadSampleCopy() {
    setTitle("Nova Launch Campaign");
    setBody(
      "Meet the all-new Nova.\n" +
      "Battery life is up to 18 hours under specified test conditions.\n" +
      "Multi-core performance delivers a 25% improvement versus the previous generation.\n" +
      "Nova is the fastest laptop on the market.\n" +
      "Battery life is 24 hours under specified test conditions."
    );
    setErrors({});
  }

  if (!brand) return <EmptyState title="Create a brand first">Content is reviewed against one brand&rsquo;s approved facts. Use &ldquo;New brand&rdquo; in the sidebar, then add source documents and facts.</EmptyState>;

  return (
    <div className="space-y-8">
      <header className="border-b border-rule/60 pb-5">
        <h1 className="text-3xl font-bold tracking-tight text-ink">Review content</h1>
        <p className="mt-1.5 text-sm text-ink-soft">
          Check a draft for <span data-testid="review-brand" className="font-semibold text-ink">{brand.name}</span> against approved facts. Every finding shows the approved evidence behind it, or says plainly that none was found.
        </p>
      </header>

      {error && <Notice kind="error" action={current && !current.run ? <button className="btn btn-secondary text-xs" disabled={busy} onClick={() => runReview(current.item)}>Retry review</button> : undefined}>{error}</Notice>}

      {!current && (
        <form onSubmit={submit} noValidate className="rounded-xl border border-rule bg-sheet p-6 shadow-subtle space-y-5" aria-label="Submit content">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule/60 pb-3">
            <div>
              <h2 className="text-lg font-bold text-ink">Submit Content for ProofGraph Review</h2>
              <p className="text-xs text-ink-soft">Paste draft marketing copy or PR claims for deterministic & evidence-backed verification.</p>
            </div>
            <button type="button" className="btn btn-secondary text-xs" onClick={loadSampleCopy}>
              Load sample marketing copy
            </button>
          </div>
          <Field label="Title" htmlFor="draft-title" error={errors.title}>
            <input id="draft-title" className="input" placeholder="e.g. Q4 Launch Announcement" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} aria-invalid={Boolean(errors.title)} autoComplete="off" />
          </Field>
          <Field label="Content to review" htmlFor="draft-content" error={errors.content} hint={`${body.length.toLocaleString()} characters`}>
            <textarea id="draft-content" className="input font-serif text-[15px] leading-relaxed" rows={9} placeholder="Paste draft text here..." value={body} onChange={(e) => setBody(e.target.value)} aria-invalid={Boolean(errors.content)} />
          </Field>
          <div className="flex items-center justify-between pt-1">
            <button className="btn btn-primary" disabled={busy}>{busy ? "Reviewing" : "Review content"}</button>
            <span className="text-xs text-ink-faint">Verified against active brand ledger</span>
          </div>
        </form>
      )}

      {busy && <Loading label="Reviewing against approved facts" />}

      {current && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 bg-sheet rounded-xl border border-rule p-3 shadow-subtle">
            <div className="flex flex-wrap items-center gap-2.5">
              <button className="btn btn-secondary text-xs py-1.5 min-h-[32px]" onClick={startOver}>New draft</button>
              <button className="btn btn-secondary text-xs py-1.5 min-h-[32px]" disabled={busy} onClick={() => runReview(current.item)}>Review this draft again</button>
            </div>
            {current.item.is_latest && current.item.workflow_status !== "in_review" && !editing && (
              <div className="flex flex-wrap items-center gap-2">
                <button className="btn btn-primary text-xs py-1.5 min-h-[32px]" onClick={() => setEditing(true)}>Create corrected revision</button>
                <span className="text-xs text-ink-faint hidden sm:inline">Saves corrections as rev {current.item.revision_number + 1}</span>
              </div>
            )}
          </div>
          {!current.item.is_latest && (
            <Notice kind="info" action={<button className="btn btn-secondary text-xs" onClick={() => openDraft(latestId ?? current.item.id)} disabled={!latestId}>Open the latest revision</button>}>
              This is revision {current.item.revision_number}, kept for the record. A newer revision exists, so this one is read only.
            </Notice>
          )}
          {editing && (
            <RevisionEditor base={current.item} findings={current.findings} onSaved={revisionSaved} onCancel={() => setEditing(false)}
                            onConflict={(id) => setLatestId(id)} />
          )}
          {current.run ? <RunBanner run={current.run} onRetry={() => runReview(current.item)} busy={busy} /> : !busy && <Notice kind="warning">This draft is saved but has not been reviewed yet.</Notice>}
          {current.run && current.run.status !== "failed" && current.run.status !== "running" && <Summary run={current.run} />}
          <Draft item={current.item} findings={current.findings} selectedId={selectedId} onSelect={setSelectedId} />
          {current.findings.length > 0 && (
            <div className="grid gap-6 lg:grid-cols-[1fr_1fr] items-start">
              <section aria-label="Findings" className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-bold text-ink">Findings ({current.findings.length})</h2>
                  <span className="text-xs text-ink-faint">Select finding to inspect evidence</span>
                </div>
                <ul className="divide-y divide-rule rounded-xl border border-rule bg-sheet shadow-subtle overflow-hidden">
                  {current.findings.map((f) => {
                    const isSelected = f.id === selectedId;
                    return (
                      <li key={f.id}>
                        <button
                          data-testid="finding-item"
                          aria-pressed={isSelected}
                          onClick={() => setSelectedId(f.id)}
                          className={`block w-full p-4 text-left transition-all ${
                            isSelected
                              ? "bg-signal-wash border-l-4 border-signal pl-3 shadow-subtle"
                              : "hover:bg-paper/60"
                          }`}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                            <div className="flex items-center gap-2">
                              <FindingBadge status={f.status} />
                              <span className={`rounded px-1.5 py-0.5 text-[11px] font-bold uppercase tracking-wider ${
                                f.severity === "high" ? "bg-state-expired-wash text-state-expired" : "bg-paper text-ink-soft"
                              }`}>
                                {SEVERITY_LABELS[f.severity]}
                              </span>
                            </div>
                            {f.requires_human_review && (
                              <span className="rounded bg-state-unapproved-wash px-1.5 py-0.5 text-[11px] font-bold text-state-unapproved">
                                Needs human review
                              </span>
                            )}
                          </div>
                          <span className="mt-1 block font-serif text-[15px] font-medium text-ink leading-snug">
                            &ldquo;{f.claim_text}&rdquo;
                          </span>
                          <span className="mt-1 block text-xs text-ink-soft line-clamp-2 leading-relaxed">
                            {f.explanation}
                          </span>
                          {f.recommended_action && (
                            <span className="mt-2 block text-xs text-signal font-medium">
                              <strong>Suggested action:</strong> {f.recommended_action}
                            </span>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
              <EvidencePanel finding={selected} onOpen={setOpened} />
            </div>
          )}
        </div>
      )}

      {current && (
        <div className="space-y-6 pt-4 border-t border-rule/70">
          <WorkflowPanel contentId={current.item.id} reviewKey={`${current.run?.id ?? "none"}-${version}`} onChanged={refreshAll} />
          <RevisionHistory contentId={current.item.id} currentId={current.item.id} version={`${version}-${current.run?.id ?? "none"}`} onOpen={openDraft} />
        </div>
      )}

      {!current && (
        <section aria-label="Previous drafts" className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold text-ink">Previous drafts</h2>
              <p className="mt-0.5 text-xs text-ink-soft">Showing the newest revision of each draft. Open one to see its older revisions.</p>
            </div>
          </div>
          {history.loading && <Loading label="Loading drafts" />}
          {history.error && <Notice kind="error" action={<button className="btn btn-secondary" onClick={history.reload}>Try again</button>}>{errorMessage(history.error)}</Notice>}
          {loadingDraft && <Loading label="Opening draft" />}
          {history.data && history.data.items.length === 0 && <EmptyState title="No drafts reviewed yet">Submit a draft above. It is saved with its review so you can reopen the findings later.</EmptyState>}
          {history.data && history.data.items.length > 0 && (
            <ul className="divide-y divide-rule rounded-xl border border-rule bg-sheet shadow-subtle overflow-hidden">
              {history.data.items.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 p-4 hover:bg-paper/40 transition-colors">
                  <div>
                    <button className="btn btn-quiet px-0 font-bold text-ink text-base hover:text-signal text-left" onClick={() => openDraft(c.id)}>{c.title}</button>
                    <p className="mt-0.5 text-xs text-ink-soft flex flex-wrap items-center gap-2">
                      <span data-testid="draft-revision" className="font-semibold text-ink">Revision {c.revision_number}</span>
                      <span>&middot;</span>
                      <WorkflowBadge status={c.workflow_status} />
                      <span>&middot;</span>
                      <span>{formatDate(c.created_at)}</span>
                      <span>&middot;</span>
                      <span>{c.review_count} review{c.review_count === 1 ? "" : "s"}</span>
                      {c.latest_review ? ` · latest: ${RUN_LABELS[c.latest_review.status]}` : ""}
                    </p>
                  </div>
                  <button className="btn btn-secondary text-xs py-1 min-h-[30px]" onClick={() => openDraft(c.id)}>Open draft</button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {opened?.source_document_id && (
        <Dialog variant="drawer" title="Source evidence" description={opened.fact_name ? `Cited for ${opened.fact_name}` : "Related source text"} onClose={() => setOpened(null)}>
          <SourceEvidence documentId={opened.source_document_id} page={opened.source_page} excerpt={opened.excerpt} />
        </Dialog>
      )}
    </div>
  );
}
