"use client";
import { type FormEvent, useState } from "react";

import { SourceEvidence } from "@/components/SourceEvidence";
import { Dialog, EffectiveBadge, Loading, Notice } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { CATEGORY_LABELS, formatDate, reviewText, STATUS_LABELS, WARNING_LABELS } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { Fact, FactStatus } from "@/types/api";

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
  const history = useResource(() => api.factRevisions(fact.id), [fact.id, fact.version]);

  async function confirm(e: FormEvent) {
    e.preventDefault();
    if (!pending) return;
    if (NEEDS_REASON.includes(pending) && !reason.trim()) return setError("Give a reason. It is saved in the fact's history.");
    setBusy(true);
    setError(null);
    try {
      const updated = await api.setFactStatus(fact.id, { status: pending, actor: actor || null, reason: reason.trim() || null, expected_version: fact.version });
      setPending(null);
      setReason("");
      onChanged(updated, `${updated.name} is now ${STATUS_LABELS[updated.status].toLowerCase()}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const dl = "grid grid-cols-[150px_1fr] gap-x-4 gap-y-2 text-[15px]";
  return (
    <Dialog variant="drawer" title={fact.name} onClose={onClose} description={CATEGORY_LABELS[fact.category]}
      footer={<button className="btn btn-secondary" onClick={() => onEdit(fact)}>Edit fact</button>}>
      <div className="space-y-8">
        <div>
          <p className="font-serif text-3xl font-semibold" data-testid="drawer-value">{fact.value}{fact.unit ? <span className="ml-1 text-xl text-ink-soft">{fact.unit}</span> : null}</p>
          {fact.qualifications && <p className="mt-2 max-w-[60ch] text-ink-soft">{fact.qualifications}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-3"><EffectiveBadge state={fact.effective_state} /><span className="text-sm font-bold">{STATUS_LABELS[fact.status]}</span></div>
        </div>

        {fact.warnings.length > 0 && <div className="space-y-2">{fact.warnings.map((w) => <Notice key={w} kind="warning">{WARNING_LABELS[w] ?? w}</Notice>)}</div>}

        <section aria-label="Status">
          {error && <div className="mb-3"><Notice kind="error">{error}</Notice></div>}
          {pending ? (
            <form onSubmit={confirm} className="space-y-3 border border-rule-strong p-4">
              <p className="font-bold">{ACTIONS[fact.status].find((a) => a.to === pending)?.label}</p>
              <label className="label" htmlFor="status-reason">Reason{NEEDS_REASON.includes(pending) ? "" : " (optional)"}</label>
              <input id="status-reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} />
              <div className="flex gap-3"><button className="btn btn-primary" disabled={busy}>{busy ? "Saving" : "Confirm"}</button><button type="button" className="btn btn-secondary" onClick={() => { setPending(null); setError(null); }}>Cancel</button></div>
            </form>
          ) : (
            <div className="flex flex-wrap gap-3">
              {ACTIONS[fact.status].map((a) => (
                <button key={a.to} className={`btn ${a.to === "active" ? "btn-primary" : a.danger ? "btn-danger" : "btn-secondary"}`} onClick={() => { setPending(a.to); setError(null); }}>{a.label}</button>
              ))}
              {!ACTIONS[fact.status].length && <p className="text-ink-soft">Retired facts cannot change status. Create a new fact instead.</p>}
            </div>
          )}
        </section>

        <dl className={dl}>
          <dt className="font-bold">Valid from</dt><dd>{formatDate(fact.valid_from)}</dd>
          <dt className="font-bold">Expires on</dt><dd>{fact.expires_at ? formatDate(fact.expires_at) : "No expiry date recorded"}</dd>
          <dt className="font-bold">Review</dt><dd>{reviewText(fact.review_state, fact.review_date) || "Not applicable"}</dd>
          <dt className="font-bold">Owner</dt><dd>{fact.owner ?? "Not set"}</dd>
          <dt className="font-bold">Approved</dt><dd>{fact.approved_at ? `${formatDate(fact.approved_at)}${fact.approved_by ? ` by ${fact.approved_by}` : ""}` : "Not approved"}</dd>
          <dt className="font-bold">Version</dt><dd>{fact.version}</dd>
        </dl>

        <section aria-label="Source">
          <h3 className="mb-3 text-xl font-semibold">Source</h3>
          {fact.source_document_id ? (
            <SourceEvidence documentId={fact.source_document_id} page={fact.source_page} excerpt={fact.source_excerpt} />
          ) : (
            <div className="border-l-4 border-rule-strong bg-paper px-4 py-3"><p className="text-sm font-bold text-ink-soft">Manual source, no document</p><p className="mt-1">{fact.source_note}</p></div>
          )}
        </section>

        <section aria-label="History">
          <h3 className="mb-3 text-xl font-semibold">History</h3>
          {history.loading && <Loading label="Loading history" />}
          {history.error && <Notice kind="error">{errorMessage(history.error)}</Notice>}
          <ol className="rule-list">
            {history.data?.slice().reverse().map((r) => (
              <li key={r.id} className="py-3 text-[15px]">
                <p className="font-bold">Version {r.revision_number}: {r.action === "created" ? "Created" : r.action === "status_changed" ? "Status changed" : "Edited"}{r.changed_by ? ` by ${r.changed_by}` : ""}</p>
                <p className="text-sm text-ink-soft">{formatDate(r.created_at)}</p>
                {Object.entries(r.changes).map(([k, c]) => <p key={k} className="text-sm">{k.replace(/_/g, " ")}: {String(c.old ?? "empty")} to {String(c.new ?? "empty")}</p>)}
                {r.change_reason && <p className="text-sm italic">{r.change_reason}</p>}
              </li>
            ))}
          </ol>
        </section>
      </div>
    </Dialog>
  );
}
