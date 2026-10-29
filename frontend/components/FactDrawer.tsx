"use client";
import { type FormEvent, useEffect, useState } from "react";

import { SourceEvidence } from "@/components/SourceEvidence";
import { Dialog, EffectiveBadge, Loading, Notice } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { CATEGORY_LABELS, formatDate, reviewText, STATUS_LABELS, WARNING_LABELS } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { Fact, FactComparison, FactStatus } from "@/types/api";

const ACTIONS: Record<FactStatus, { to: FactStatus; label: string; danger?: boolean }[]> = {
  proposed: [{ to: "active", label: "Approve fact" }, { to: "rejected", label: "Reject", danger: true }],
  active: [{ to: "expired", label: "Mark expired", danger: true }, { to: "retired", label: "Retire", danger: true }, { to: "proposed", label: "Return to proposed" }],
  rejected: [{ to: "proposed", label: "Return to proposed" }],
  expired: [{ to: "active", label: "Approve again" }, { to: "retired", label: "Retire", danger: true }],
  retired: [],
};
const NEEDS_REASON: FactStatus[] = ["rejected", "expired", "retired"];

export function FactDrawer({ fact, actor, onClose, onEdit, onChanged }: {
  fact: Fact; actor: string; onClose: () => void; onEdit: (f: Fact) => void; onChanged: (f: Fact, message: string) => void;
}) {
  const [pending, setPending] = useState<FactStatus | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<FactComparison | null>(null);
  const history = useResource(() => api.factRevisions(fact.id), [fact.id, fact.version]);

  useEffect(() => {
    if (fact.status === "proposed" || fact.version > 1) {
      api.getFactComparison(fact.id).then(setComparison).catch(() => {});
    }
  }, [fact.id, fact.version, fact.status]);

  async function confirm(e: FormEvent) {
    e.preventDefault();
    if (!pending) return;
    if (NEEDS_REASON.includes(pending) && !reason.trim()) return setError("Give a reason. It is saved in the fact's history.");
    setBusy(true);
    setError(null);
    try {
      let updated: Fact;
      if (pending === "active") {
        updated = await api.approveFact(fact.id, { approval_notes: reason.trim() || "Approved by reviewer", expected_version: fact.version });
      } else if (pending === "rejected") {
        updated = await api.rejectFact(fact.id, { rejection_reason: reason.trim(), expected_version: fact.version });
      } else {
        updated = await api.setFactStatus(fact.id, { status: pending, actor: actor || null, reason: reason.trim() || null, expected_version: fact.version });
      }
      setPending(null);
      setReason("");
      onChanged(updated, `${updated.name} is now ${STATUS_LABELS[updated.status].toLowerCase()}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const dl = "grid grid-cols-[140px_1fr] gap-x-4 gap-y-2 text-xs bg-paper/60 p-4 rounded-xl border border-rule";
  return (
    <Dialog variant="drawer" title={fact.name} onClose={onClose} description={CATEGORY_LABELS[fact.category]}
      footer={<button className="btn btn-secondary text-xs" onClick={() => onEdit(fact)}>Edit fact</button>}>
      <div className="space-y-6">
        <div>
          <p className="font-serif text-3xl font-bold text-ink" data-testid="drawer-value">
            {fact.value}{fact.unit ? <span className="ml-1 text-xl font-normal text-ink-muted">{fact.unit}</span> : null}
          </p>
          {fact.qualifications && <p className="mt-2 max-w-[60ch] text-xs text-ink-muted leading-relaxed">{fact.qualifications}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <EffectiveBadge state={fact.effective_state} />
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-surface-100 text-ink border border-rule">{STATUS_LABELS[fact.status]}</span>
            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-paper text-ink-soft border border-rule">v{fact.version}</span>
          </div>
        </div>

        {fact.status === "proposed" && (
          <Notice kind="warning">
            <strong>Proposed Version:</strong> This fact was modified or proposed. A Compliance Reviewer must review the changes below and approve it before it can be used as active approved evidence.
          </Notice>
        )}

        {comparison && comparison.is_material_change && comparison.previous_approved_snapshot && (
          <div className="rounded-xl border border-signal-border bg-signal-wash/40 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-signal-dark">Version Comparison (v{fact.version} Proposed vs v{fact.version - 1} Approved)</h4>
              {comparison.affected_content_count > 0 && (
                <span className="text-[11px] font-bold text-state-expired bg-sheet px-2 py-0.5 rounded border border-rule">
                  {comparison.affected_content_count} content assets impacted
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 bg-sheet rounded-lg border border-rule space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">Previous Approved Value</span>
                <p className="font-semibold text-ink line-through opacity-70">
                  {String(comparison.previous_approved_snapshot.value ?? "")} {String(comparison.previous_approved_snapshot.unit ?? "")}
                </p>
              </div>
              <div className="p-3 bg-sheet rounded-lg border border-signal-border space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-signal-dark">Proposed New Value</span>
                <p className="font-bold text-signal-dark">
                  {fact.value} {fact.unit ?? ""}
                </p>
              </div>
            </div>
            {comparison.change_reason && (
              <p className="text-xs text-ink-soft italic">
                Reason given: &ldquo;{comparison.change_reason}&rdquo; {comparison.proposed_by ? `(by ${comparison.proposed_by})` : ""}
              </p>
            )}
          </div>
        )}

        {fact.warnings.length > 0 && (
          <div className="space-y-2">
            {fact.warnings.map((w) => <Notice key={w} kind="warning">{WARNING_LABELS[w] ?? w}</Notice>)}
          </div>
        )}

        <section aria-label="Status" className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Reviewer Governance Actions</h3>
          {error && <div className="mb-3"><Notice kind="error">{error}</Notice></div>}
          {pending ? (
            <form onSubmit={confirm} className="space-y-3 border border-rule rounded-xl bg-paper/50 p-4">
              <p className="font-bold text-sm text-ink">{ACTIONS[fact.status].find((a) => a.to === pending)?.label}</p>
              <div>
                <label className="block text-xs font-semibold text-ink mb-1" htmlFor="status-reason">
                  {pending === "active" ? "Approval Notes (optional)" : "Reason *"}
                </label>
                <input id="status-reason" className="input text-xs" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} placeholder={pending === "active" ? "Reviewer justification or notes" : "Why is this proposal being rejected?"} />
              </div>
              <div className="flex gap-2 pt-1">
                <button className="btn btn-primary text-xs" disabled={busy}>{busy ? "Saving..." : "Confirm"}</button>
                <button type="button" className="btn btn-secondary text-xs" onClick={() => { setPending(null); setError(null); }}>Cancel</button>
              </div>
            </form>
          ) : (
            <div className="flex flex-wrap gap-2">
              {ACTIONS[fact.status].map((a) => (
                <button
                  key={a.to}
                  className={`btn text-xs ${a.to === "active" ? "btn-primary" : a.danger ? "btn-danger" : "btn-secondary"}`}
                  onClick={() => { setPending(a.to); setError(null); }}
                >
                  {a.label}
                </button>
              ))}
              {!ACTIONS[fact.status].length && <p className="text-xs text-ink-muted italic">Retired facts cannot change status. Create a new fact instead.</p>}
            </div>
          )}
        </section>

        <dl className={dl}>
          <dt className="font-semibold text-ink-muted uppercase tracking-wider text-[11px]">Valid from</dt><dd className="text-ink font-medium">{formatDate(fact.valid_from)}</dd>
          <dt className="font-semibold text-ink-muted uppercase tracking-wider text-[11px]">Expires on</dt><dd className="text-ink font-medium">{fact.expires_at ? formatDate(fact.expires_at) : "No expiry date recorded"}</dd>
          <dt className="font-semibold text-ink-muted uppercase tracking-wider text-[11px]">Review</dt><dd className="text-ink font-medium">{reviewText(fact.review_state, fact.review_date) || "Not applicable"}</dd>
          <dt className="font-semibold text-ink-muted uppercase tracking-wider text-[11px]">Owner</dt><dd className="text-ink font-medium">{fact.owner ?? "Not set"}</dd>
          <dt className="font-semibold text-ink-muted uppercase tracking-wider text-[11px]">Approved</dt><dd className="text-ink font-medium">{fact.approved_at ? `${formatDate(fact.approved_at)}${fact.approved_by ? ` by ${fact.approved_by}` : ""}` : "Not approved"}</dd>
          <dt className="font-semibold text-ink-muted uppercase tracking-wider text-[11px]">Version</dt><dd className="text-ink font-mono font-bold">v{fact.version}</dd>
        </dl>

        <section aria-label="Source" className="space-y-2">
          <h3 className="text-sm font-serif font-bold text-ink">Source Ground Truth</h3>
          {fact.source_document_id ? (
            <SourceEvidence documentId={fact.source_document_id} page={fact.source_page} excerpt={fact.source_excerpt} />
          ) : (
            <div className="rounded-xl border border-rule bg-paper p-4">
              <p className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Manual source, no document attached</p>
              <p className="mt-1 text-xs text-ink">{fact.source_note}</p>
            </div>
          )}
        </section>

        <section aria-label="History" className="space-y-3">
          <h3 className="text-sm font-serif font-bold text-ink">Version Ledger & Decision Audit</h3>
          {history.loading && <Loading label="Loading history" />}
          {history.error && <Notice kind="error">{errorMessage(history.error)}</Notice>}
          <ol className="divide-y divide-rule border border-rule rounded-xl bg-sheet overflow-hidden">
            {history.data?.slice().reverse().map((r) => (
              <li key={r.id} className="p-3.5 text-xs space-y-1 hover:bg-paper/40 transition">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-ink font-serif">Version {r.revision_number}</span>
                  <span className="text-[11px] text-ink-muted">{formatDate(r.created_at)}</span>
                </div>
                <p className="text-ink-muted">
                  {r.action === "created" ? "Created" : r.action === "status_changed" ? "Status changed" : "Edited"}
                  {r.changed_by ? ` by ${r.changed_by}` : ""}
                </p>
                {Object.entries(r.changes).map(([k, c]) => (
                  <div key={k} className="p-2 bg-paper rounded border border-rule/50 font-mono text-[11px] text-ink">
                    <strong>{k.replace(/_/g, " ")}:</strong> {String(c.old ?? "empty")} &rarr; {String(c.new ?? "empty")}
                  </div>
                ))}
                {r.change_reason && <p className="text-xs text-ink-muted italic pt-0.5">&ldquo;{r.change_reason}&rdquo;</p>}
              </li>
            ))}
          </ol>
        </section>
      </div>
    </Dialog>
  );
}
