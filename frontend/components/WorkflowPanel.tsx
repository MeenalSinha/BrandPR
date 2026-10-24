"use client";
import { useState } from "react";

import { Loading, Notice } from "@/components/ui";
import { useBrand, useToast } from "@/components/providers";
import { EventList, WorkflowBadge } from "@/components/workflowUi";
import { api, ApiError, errorMessage } from "@/lib/api";
import { FINDING_LABELS, formatDate } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { DecisionAction, Workflow } from "@/types/api";

/**
 * Submission and decision for ONE revision. What the buttons offer comes from the backend (`available_actions`), and the backend
 * checks every action again; hiding a button here is not a security control.
 */
export function WorkflowPanel({ contentId, reviewKey, onChanged }: { contentId: string; reviewKey: string; onChanged: () => void }) {
  const { actor, role } = useBrand();
  const toast = useToast();
  const wf = useResource(() => api.workflow(contentId), [contentId, reviewKey, actor, role]);
  const [rationale, setRationale] = useState("");
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | string | null>(null);

  if (wf.loading && !wf.data) return <Loading label="Loading approval status" />;
  if (wf.error || !wf.data) return <Notice kind="error" action={<button className="btn btn-secondary" onClick={wf.reload}>Try again</button>}>The approval status could not be loaded. {errorMessage(wf.error)}</Notice>;
  const w: Workflow = wf.data;
  const r = w.readiness;
  const can = (a: string) => w.available_actions.includes(a);
  const open = r.blocking_findings.filter((b) => !b.overridden);
  const missingReason = open.some((b) => !(reasons[b.finding_id] ?? "").trim());

  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      toast.push("success", done);
      setRationale("");
      setReasons({});
      wf.reload();
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e : errorMessage(e));
      wf.reload();
    } finally {
      setBusy(false);
    }
  }

  function decide(action: DecisionAction) {
    const label = { approve: "Revision approved.", request_changes: "Changes requested.", reject: "Revision rejected." }[action];
    return run(() => api.decide(contentId, {
      action, review_run_id: r.review?.id ?? null, rationale: rationale.trim() || null,
      overrides: action === "approve" ? open.map((b) => ({ finding_id: b.finding_id, reason: (reasons[b.finding_id] ?? "").trim() })) : [],
    }), label);
  }

  const errorText = error instanceof ApiError ? `${error.message}${error.details.length ? " " + error.details.map((d) => d.message).join(" ") : ""}` : error;
  const decidable = can("approve") || can("reject") || can("request_changes");
  const finalState = w.workflow_status === "approved" || w.workflow_status === "rejected" || w.workflow_status === "changes_requested";

  return (
    <section aria-label="Approval" data-testid="workflow-panel" className="space-y-4 border border-rule bg-sheet p-5">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">Approval of revision {w.revision_number}</h2>
        <WorkflowBadge status={w.workflow_status} />
      </header>

      {!w.is_latest && <Notice kind="info">A newer revision exists. This one is kept for the record and can no longer be submitted or decided.</Notice>}
      {w.workflow_status === "approved" && <Notice kind="success"><span data-testid="approved-note">Approved. This approval applies only to this exact text. Any later revision needs its own review and decision.</span></Notice>}
      {w.workflow_status === "changes_requested" && <Notice kind="warning">A reviewer asked for changes. Create a new revision to make them.</Notice>}
      {w.workflow_status === "rejected" && <Notice kind="error">A reviewer rejected this revision. A new attempt must be a new revision.</Notice>}

      {!finalState && !r.ready_for_decision && <Notice kind="error"><span data-testid="not-ready">Not ready for approval.</span>{r.reasons.map((x) => <span key={x} className="block font-normal">{x}</span>)}</Notice>}
      {r.ready_for_decision && r.limited_mode && <Notice kind="warning"><span data-testid="limited-warning">This review ran in limited mode.</span>{r.limitations.map((l) => <span key={l} className="block font-normal">{l}</span>)}</Notice>}
      {r.ready_for_decision && !finalState && r.counts && Object.keys(r.counts).length > 0 && (
        <p className="text-sm" data-testid="finding-counts">Latest review: {Object.entries(r.counts).map(([k, n]) => `${n} ${k}`).join(", ")}.</p>
      )}

      {r.blocking_findings.length > 0 && (
        <div data-testid="blocking-findings" className="space-y-2">
          <h3 className="font-bold">High-risk findings ({r.blocking_findings.length})</h3>
          <p className="text-sm text-ink-soft">Fix these in a new revision, or a reviewer can accept each one with a reason. Accepting never changes the finding itself.</p>
          <ul className="space-y-2">
            {r.blocking_findings.map((b) => (
              <li key={b.finding_id} className="border-l-4 border-state-unapproved bg-paper p-3">
                <p className="font-serif">&ldquo;{b.claim_text}&rdquo; <span className="text-sm font-bold">({FINDING_LABELS[b.status as keyof typeof FINDING_LABELS] ?? b.status})</span></p>
                <p className="text-sm">{b.explanation}</p>
                {b.overridden ? <p className="text-sm font-bold text-state-current">Accepted by a reviewer. See the reason below.</p>
                  : can("approve") && (
                    <div className="mt-2">
                      <label className="label" htmlFor={`ov-${b.finding_id}`}>Reason for accepting this risk</label>
                      <input id={`ov-${b.finding_id}`} className="input" value={reasons[b.finding_id] ?? ""} onChange={(e) => setReasons((x) => ({ ...x, [b.finding_id]: e.target.value }))} />
                    </div>
                  )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <Notice kind="error">{errorText}</Notice>}

      {can("submit_review") && (
        <div className="flex flex-wrap items-center gap-3">
          <button className="btn btn-primary" disabled={busy} onClick={() => run(() => api.submitForReview(contentId), "Submitted for approval.")}>Submit for approval</button>
          <p className="text-sm text-ink-soft">A reviewer will see the latest review of this exact text.</p>
        </div>
      )}
      {w.workflow_status === "draft" && w.is_latest && !can("submit_review") && <p className="text-sm text-ink-soft">Run a review of this revision, then submit it for approval.</p>}
      {w.workflow_status === "in_review" && !decidable && (
        <p data-testid="waiting" className="text-sm text-ink-soft">{role === "reviewer" ? "You created this revision, so another reviewer has to decide." : "Waiting for a reviewer. Switch the demo role to Reviewer in the sidebar to decide."}</p>
      )}
      {decidable && (
        <div data-testid="decision-form" className="space-y-3 border-t border-rule pt-4">
          <label className="label" htmlFor="decision-rationale">Reason (required to request changes or reject)</label>
          <textarea id="decision-rationale" className="input" rows={2} value={rationale} onChange={(e) => setRationale(e.target.value)} />
          <div className="flex flex-wrap gap-3">
            <button className="btn btn-primary" disabled={busy || !can("approve") || missingReason} onClick={() => decide("approve")}>Approve</button>
            <button className="btn btn-secondary" disabled={busy || !rationale.trim()} onClick={() => decide("request_changes")}>Request changes</button>
            <button className="btn btn-secondary" disabled={busy || !rationale.trim()} onClick={() => decide("reject")}>Reject</button>
          </div>
          {!can("approve") && <p className="text-sm text-ink-soft">Approval is unavailable until the latest review of this text finished.</p>}
          {can("approve") && missingReason && <p className="text-sm text-ink-soft">Give a reason for each high-risk finding you accept, or request changes.</p>}
        </div>
      )}

      {w.overrides.length > 0 && (
        <div data-testid="overrides">
          <h3 className="font-bold">Accepted risks</h3>
          <ul className="text-sm">{w.overrides.map((o) => <li key={o.id}>{o.actor} on {formatDate(o.created_at)}: {o.reason}</li>)}</ul>
        </div>
      )}
      <div>
        <h3 className="mb-2 font-bold">Decision history</h3>
        <EventList events={w.events} />
      </div>
    </section>
  );
}
