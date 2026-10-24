"use client";
import { Loading, Notice } from "@/components/ui";
import { RUN_LABELS, formatDate } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { api, errorMessage } from "@/lib/api";
import { WorkflowBadge } from "@/components/workflowUi";

/** Every revision of one piece of content, oldest first. Earlier revisions can be opened and read; none can be edited. */
export function RevisionHistory({ contentId, currentId, version, onOpen }: { contentId: string; currentId: string; version: number | string; onOpen: (id: string) => void }) {
  const history = useResource(() => api.revisions(contentId), [contentId, version]);
  if (history.loading && !history.data) return <Loading label="Loading revision history" />;
  if (history.error || !history.data) return <Notice kind="error" action={<button className="btn btn-secondary" onClick={history.reload}>Try again</button>}>The revision history could not be loaded. {errorMessage(history.error)}</Notice>;
  return (
    <section aria-label="Revision history" className="space-y-2">
      <h2 className="text-xl font-semibold">Revision history</h2>
      <ol data-testid="revision-list" className="rule-list border border-rule bg-sheet">
        {history.data.items.map((r) => (
          <li key={r.id} data-testid="revision-item" className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
            <div>
              <p className="flex flex-wrap items-center gap-2">
                <strong>Revision {r.revision_number}</strong><WorkflowBadge status={r.workflow_status} />
                {r.id === currentId && <span className="text-sm font-bold text-signal-dark">Open now</span>}
                {r.is_latest && <span className="text-sm text-ink-soft">Latest</span>}
              </p>
              <p className="text-sm text-ink-soft">{formatDate(r.created_at)}{r.created_by ? ` by ${r.created_by}` : ""} &middot; {r.char_count.toLocaleString()} characters &middot; {r.review_count} review{r.review_count === 1 ? "" : "s"}
                {r.latest_review ? ` · latest: ${RUN_LABELS[r.latest_review.status]}` : ""}</p>
              {r.latest_review && r.latest_review.status !== "failed" && (
                <p className="text-sm text-ink-soft">Findings: {Object.entries(r.latest_review.counts).filter(([, n]) => n > 0).map(([k, n]) => `${n} ${k}`).join(", ") || "none"}</p>
              )}
              {r.change_note && <p className="text-sm">Note: {r.change_note}</p>}
              {r.decision && <p className="text-sm" data-testid="revision-decision"><strong>{r.decision.action.replace("_", " ")}</strong> by {r.decision.actor} on {formatDate(r.decision.created_at)}{r.decision.rationale ? `: ${r.decision.rationale}` : ""}</p>}
            </div>
            <button className="btn btn-secondary" disabled={r.id === currentId} onClick={() => onOpen(r.id)}>{r.id === currentId ? "Viewing" : "Open revision"}</button>
          </li>
        ))}
      </ol>
    </section>
  );
}
