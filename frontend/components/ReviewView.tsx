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

const STATUS_STYLE: Record<FindingStatus, string> = {
  supported: "bg-state-current-wash text-state-current",
  unsupported: "bg-state-unapproved-wash text-state-unapproved",
  conflicting: "bg-state-expired-wash text-state-expired",
  outdated: "bg-state-retired-wash text-state-retired",
  uncertain: "bg-state-pending-wash text-state-pending",
};

function FindingBadge({ status }: { status: FindingStatus }) {
  return <span data-testid="finding-status" className={`inline-block rounded px-2 py-0.5 text-sm font-bold ${STATUS_STYLE[status]}`}>{FINDING_LABELS[status]}</span>;
}

interface Current { item: ContentItem; run: ReviewRun | null; findings: Finding[] }

function Draft({ item, findings, selectedId, onSelect }: { item: ContentItem; findings: Finding[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const segments = useMemo(() => segmentDraft(item.content, findings), [item.content, findings]);
  return (
    <section aria-label="Submitted draft" className="border border-rule bg-sheet p-5">
      <h3 className="flex flex-wrap items-center gap-2 text-lg font-semibold">{item.title} <span data-testid="revision-label" className="text-sm font-bold text-ink-soft">Revision {item.revision_number}</span> <WorkflowBadge status={item.workflow_status} /></h3>
      <p className="mb-3 text-sm text-ink-soft">Saved {formatDate(item.created_at)}{item.submitted_by ? ` by ${item.submitted_by}` : ""}. Highlighted passages are claims the review identified; select one to see its finding.</p>
      <p data-testid="draft-text" className="whitespace-pre-wrap font-serif text-[17px] leading-relaxed">
        {segments.map((seg, i) => {
          if (!seg.findingIds.length) return <span key={i}>{seg.text}</span>;
          const selected = selectedId !== null && seg.findingIds.includes(selectedId);
          return (
            <mark key={i} data-testid={selected ? "claim-mark-selected" : "claim-mark"} onClick={() => onSelect(selected ? seg.findingIds[0] : seg.findingIds[seg.findingIds.length - 1])}
                  className={`cursor-pointer ${selected ? "ring-2 ring-signal" : "bg-signal-wash"}`}>{seg.text}</mark>
          );
        })}
      </p>
    </section>
  );
}

function EvidenceCard({ ev, onOpen }: { ev: Evidence; onOpen: (ev: Evidence) => void }) {
  return (
    <article data-testid="evidence-item" className="border-l-4 border-rule-strong bg-paper px-4 py-3">
      <h4 className="text-sm font-bold text-ink-soft">{ROLE_LABELS[ev.role]}</h4>
      {ev.fact_name && (
        <p className="mt-1"><strong>{ev.fact_name}:</strong> {ev.fact_value}
          {ev.fact_qualifications && <span className="block text-sm text-ink-soft">Conditions: {ev.fact_qualifications}</span>}
          <span className="block text-sm text-ink-soft">Approved fact, state at review: {ev.fact_effective_state}, version {ev.fact_version}</span></p>
      )}
      {ev.source_title ? (
        <p className="mt-2 text-sm"><span className="font-bold">Source:</span> {ev.source_title}{ev.source_page ? `, page ${ev.source_page}` : ""}</p>
      ) : null}
      {ev.excerpt && (
        <blockquote className="mt-2 border-l-2 border-rule-strong pl-3 font-serif">
          {ev.excerpt}
          {ev.excerpt_verified === false && <span className="block text-sm font-bold text-state-unapproved">This passage was not found in the stored source text.</span>}
        </blockquote>
      )}
      {ev.relation_note && <p className="mt-2 text-sm text-ink-soft">{ev.relation_note}</p>}
      {ev.source_document_id && <button className="btn btn-secondary mt-3" onClick={() => onOpen(ev)}>Open source{ev.source_page ? ` (page ${ev.source_page})` : ""}</button>}
    </article>
  );
}

function EvidencePanel({ finding, onOpen }: { finding: Finding | null; onOpen: (ev: Evidence) => void }) {
  if (!finding) return <aside aria-label="Evidence" className="border border-dashed border-rule-strong bg-sheet p-5 text-ink-soft">Select a finding to see its explanation and evidence.</aside>;
  const cited = finding.evidence.filter((e) => e.role !== "related_source");
  return (
    <aside aria-label="Evidence" data-testid="evidence-panel" className="space-y-4 border border-rule bg-sheet p-5">
      <div>
        <div className="flex flex-wrap items-center gap-2"><FindingBadge status={finding.status} /><span className="text-sm font-bold">{SEVERITY_LABELS[finding.severity]}</span>
          <span className="text-sm text-ink-soft">{CLAIM_LABELS[finding.claim_category]}</span></div>
        <h3 className="mt-2 font-serif text-xl">&ldquo;{finding.claim_text}&rdquo;</h3>
        <p className="mt-2">{finding.explanation}</p>
        {finding.recommended_action && <p className="mt-2"><strong>Suggested action:</strong> {finding.recommended_action}</p>}
        {finding.requires_human_review && <p data-testid="needs-review" className="mt-2 font-bold text-state-unapproved">A person must review this finding before the content is published.</p>}
        {finding.method === "ai_assisted" && <p className="mt-1 text-sm text-ink-soft">This finding used an AI-assisted comparison. The cited records are real; the match itself needs human confirmation.</p>}
      </div>
      {cited.length === 0 && (
        <p data-testid="no-evidence" className="border-l-4 border-state-unapproved bg-state-unapproved-wash px-4 py-3 font-bold text-state-unapproved">
          No suitable approved evidence was found. No source is cited because none exists.
        </p>
      )}
      {finding.evidence.map((ev) => <EvidenceCard key={ev.id} ev={ev} onOpen={onOpen} />)}
    </aside>
  );
}

function Summary({ run }: { run: ReviewRun }) {
  return (
    <section aria-label="Review summary">
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {FINDING_ORDER.map((s) => (
          <li key={s} title={FINDING_HELP[s]} className="border border-rule bg-sheet px-3 py-3">
            <span data-testid={`count-${s}`} className="block font-serif text-3xl font-semibold">{run.counts[s] ?? 0}</span>
            <span className="text-sm font-bold">{FINDING_LABELS[s]}</span>
          </li>
        ))}
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

  if (!brand) return <EmptyState title="Create a brand first">Content is reviewed against one brand&rsquo;s approved facts. Use &ldquo;New brand&rdquo; in the sidebar, then add source documents and facts.</EmptyState>;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-semibold">Review content</h1>
        <p className="mt-1 text-ink-soft">Check a draft for <span data-testid="review-brand">{brand.name}</span> against approved facts. Every finding shows the approved evidence behind it, or says plainly that none was found.</p>
      </header>

      {error && <Notice kind="error" action={current && !current.run ? <button className="btn btn-secondary" disabled={busy} onClick={() => runReview(current.item)}>Retry review</button> : undefined}>{error}</Notice>}

      {!current && (
        <form onSubmit={submit} noValidate className="space-y-4 border border-rule bg-sheet p-5" aria-label="Submit content">
          <Field label="Title" htmlFor="draft-title" error={errors.title}>
            <input id="draft-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} aria-invalid={Boolean(errors.title)} autoComplete="off" />
          </Field>
          <Field label="Content to review" htmlFor="draft-content" error={errors.content} hint={`${body.length.toLocaleString()} characters`}>
            <textarea id="draft-content" className="input font-serif" rows={9} value={body} onChange={(e) => setBody(e.target.value)} aria-invalid={Boolean(errors.content)} />
          </Field>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Reviewing" : "Review content"}</button>
        </form>
      )}

      {busy && <Loading label="Reviewing against approved facts" />}

      {current && (
        <div className="space-y-6">
          <div className="flex flex-wrap gap-3">
            <button className="btn btn-secondary" onClick={startOver}>New draft</button>
            <button className="btn btn-secondary" disabled={busy} onClick={() => runReview(current.item)}>Review this draft again</button>
          </div>
          {!current.item.is_latest && (
            <Notice kind="info" action={<button className="btn btn-secondary" onClick={() => openDraft(latestId ?? current.item.id)} disabled={!latestId}>Open the latest revision</button>}>
              This is revision {current.item.revision_number}, kept for the record. A newer revision exists, so this one is read only.
            </Notice>
          )}
          {current.item.is_latest && current.item.workflow_status !== "in_review" && !editing && (
            <div className="flex flex-wrap items-center gap-3">
              <button className="btn btn-primary" onClick={() => setEditing(true)}>Create corrected revision</button>
              <p className="text-sm text-ink-soft">Saves your corrections as revision {current.item.revision_number + 1}. This revision is not changed.</p>
            </div>
          )}
          {editing && (
            <RevisionEditor base={current.item} findings={current.findings} onSaved={revisionSaved} onCancel={() => setEditing(false)}
                            onConflict={(id) => setLatestId(id)} />
          )}
          {current.run ? <RunBanner run={current.run} onRetry={() => runReview(current.item)} busy={busy} /> : !busy && <Notice kind="warning">This draft is saved but has not been reviewed yet.</Notice>}
          {current.run && current.run.status !== "failed" && current.run.status !== "running" && <Summary run={current.run} />}
          <Draft item={current.item} findings={current.findings} selectedId={selectedId} onSelect={setSelectedId} />
          {current.findings.length > 0 && (
            <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
              <section aria-label="Findings">
                <h2 className="mb-3 text-xl font-semibold">Findings ({current.findings.length})</h2>
                <ul className="rule-list border border-rule bg-sheet">
                  {current.findings.map((f) => (
                    <li key={f.id}>
                      <button data-testid="finding-item" aria-pressed={f.id === selectedId} onClick={() => setSelectedId(f.id)}
                              className={`block w-full px-4 py-3 text-left hover:bg-paper ${f.id === selectedId ? "bg-signal-wash" : ""}`}>
                        <span className="flex flex-wrap items-center gap-2"><FindingBadge status={f.status} /><span className="text-sm font-bold">{SEVERITY_LABELS[f.severity]}</span>
                          {f.requires_human_review && <span className="text-sm font-bold text-state-unapproved">Needs human review</span>}</span>
                        <span className="mt-1 block font-serif">&ldquo;{f.claim_text}&rdquo;</span>
                        <span className="mt-1 block text-sm text-ink-soft">{f.explanation}</span>
                        {f.recommended_action && <span className="mt-1 block text-sm"><strong>Suggested action:</strong> {f.recommended_action}</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
              <EvidencePanel finding={selected} onOpen={setOpened} />
            </div>
          )}
        </div>
      )}

      {current && (
        <div className="space-y-6">
          <WorkflowPanel contentId={current.item.id} reviewKey={`${current.run?.id ?? "none"}-${version}`} onChanged={refreshAll} />
          <RevisionHistory contentId={current.item.id} currentId={current.item.id} version={`${version}-${current.run?.id ?? "none"}`} onOpen={openDraft} />
        </div>
      )}

      {!current && (
        <section aria-label="Previous drafts">
          <h2 className="mb-3 text-xl font-semibold">Previous drafts</h2>
          <p className="mb-2 text-sm text-ink-soft">Showing the newest revision of each draft. Open one to see its older revisions.</p>
          {history.loading && <Loading label="Loading drafts" />}
          {history.error && <Notice kind="error" action={<button className="btn btn-secondary" onClick={history.reload}>Try again</button>}>{errorMessage(history.error)}</Notice>}
          {loadingDraft && <Loading label="Opening draft" />}
          {history.data && history.data.items.length === 0 && <EmptyState title="No drafts reviewed yet">Submit a draft above. It is saved with its review so you can reopen the findings later.</EmptyState>}
          {history.data && history.data.items.length > 0 && (
            <ul className="rule-list border border-rule bg-sheet">
              {history.data.items.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                  <div>
                    <button className="btn btn-quiet px-0 font-bold" onClick={() => openDraft(c.id)}>{c.title}</button>
                    <p className="text-sm text-ink-soft"><span data-testid="draft-revision">Revision {c.revision_number}</span> &middot; <WorkflowBadge status={c.workflow_status} /> &middot; {formatDate(c.created_at)} &middot; {c.review_count} review{c.review_count === 1 ? "" : "s"}
                      {c.latest_review ? ` · latest: ${RUN_LABELS[c.latest_review.status]}` : ""}</p>
                  </div>
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
