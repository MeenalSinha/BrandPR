"use client";
import type { ReactNode } from "react";

import { ACTION_LABELS, formatDate, WORKFLOW_LABELS } from "@/lib/format";
import type { WorkflowEvent, WorkflowStatus } from "@/types/api";

const STYLE: Record<WorkflowStatus, string> = {
  draft: "bg-paper text-ink-soft",
  in_review: "bg-state-pending-wash text-state-pending",
  changes_requested: "bg-state-unapproved-wash text-state-unapproved",
  approved: "bg-state-current-wash text-state-current",
  rejected: "bg-state-expired-wash text-state-expired",
};

export function WorkflowBadge({ status }: { status: WorkflowStatus }) {
  return <span data-testid="workflow-status" className={`inline-block rounded px-2 py-0.5 text-sm font-bold ${STYLE[status]}`}>{WORKFLOW_LABELS[status]}</span>;
}

export function EventList({ events, empty = "No workflow events yet." }: { events: WorkflowEvent[]; empty?: ReactNode }) {
  if (!events.length) return <p className="text-sm text-ink-soft">{empty}</p>;
  return (
    <ol data-testid="event-list" className="rule-list border border-rule bg-sheet">
      {events.map((e) => (
        <li key={e.id} data-testid="event-item" className="px-4 py-2 text-sm">
          <p><strong>Revision {e.revision_number}: {ACTION_LABELS[e.action]}</strong> by {e.actor} ({e.actor_role}) &middot; {formatDate(e.created_at)}</p>
          {e.rationale && <p className="mt-1 text-ink-soft">&ldquo;{e.rationale}&rdquo;</p>}
        </li>
      ))}
    </ol>
  );
}
