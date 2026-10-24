"use client";
import type { ReactNode } from "react";

import { ACTION_LABELS, formatDate, WORKFLOW_LABELS } from "@/lib/format";
import type { WorkflowEvent, WorkflowStatus } from "@/types/api";

const STYLE: Record<WorkflowStatus, string> = {
  draft: "bg-paper text-ink-soft border-rule",
  in_review: "bg-state-pending-wash text-state-pending border-state-pending-border",
  changes_requested: "bg-state-unapproved-wash text-state-unapproved border-state-unapproved-border",
  approved: "bg-state-current-wash text-state-current border-state-current-border",
  rejected: "bg-state-expired-wash text-state-expired border-state-expired-border",
};

export function WorkflowBadge({ status }: { status: WorkflowStatus }) {
  return (
    <span data-testid="workflow-status" className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide ${STYLE[status]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {WORKFLOW_LABELS[status]}
    </span>
  );
}

export function EventList({ events, empty = "No workflow events yet." }: { events: WorkflowEvent[]; empty?: ReactNode }) {
  if (!events.length) return <p className="text-sm text-ink-soft italic">{empty}</p>;
  return (
    <ol data-testid="event-list" className="divide-y divide-rule rounded-xl border border-rule bg-sheet shadow-subtle overflow-hidden">
      {events.map((e) => (
        <li key={e.id} data-testid="event-item" className="p-3.5 text-sm transition-colors hover:bg-paper/40">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-semibold text-ink">
              Revision {e.revision_number}: <span className="text-signal">{ACTION_LABELS[e.action]}</span>
            </p>
            <span className="text-xs text-ink-faint">{formatDate(e.created_at)}</span>
          </div>
          <p className="mt-1 text-xs text-ink-soft">
            By <strong className="text-ink">{e.actor}</strong> ({e.actor_role})
          </p>
          {e.rationale && (
            <p className="mt-2 rounded-lg bg-paper/70 border border-rule/60 p-2 text-xs text-ink-soft italic leading-relaxed">
              &ldquo;{e.rationale}&rdquo;
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
