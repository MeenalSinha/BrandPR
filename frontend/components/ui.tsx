"use client";
import { type ReactNode, useEffect, useId, useRef } from "react";

import { EFFECTIVE_LABELS, PROCESSING_LABELS } from "@/lib/format";
import type { EffectiveState, ProcessingStatus } from "@/types/api";

export function Dialog({
  title, onClose, children, footer, variant = "modal", description,
}: {
  title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; variant?: "modal" | "drawer"; description?: string;
}) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    opener.current = document.activeElement;
    const first = panel.current?.querySelector<HTMLElement>("input, select, textarea, button:not([data-close])");
    (first ?? panel.current)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && panel.current) {
        const items = Array.from(panel.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'));
        if (!items.length) return;
        const [a, z] = [items[0], items[items.length - 1]];
        if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
        else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      (opener.current as HTMLElement | null)?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const drawer = variant === "drawer";
  return (
    <div className={`fixed inset-0 z-40 flex bg-ink/45 ${drawer ? "justify-end" : "items-start justify-center overflow-y-auto px-4 py-10"}`}
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
           className={drawer ? "drawer-panel flex h-full w-full max-w-[760px] flex-col bg-sheet shadow-xl" : "w-full max-w-[640px] rounded-lg bg-sheet shadow-xl"}>
        <header className="flex items-start justify-between gap-4 border-b border-rule px-6 py-4">
          <div>
            <h2 id={titleId} className="text-xl font-semibold">{title}</h2>
            {description && <p className="mt-1 text-sm text-ink-soft">{description}</p>}
          </div>
          <button type="button" data-close onClick={onClose} className="btn btn-quiet" aria-label="Close dialog">Close</button>
        </header>
        <div className={`px-6 py-5 ${drawer ? "flex-1 overflow-y-auto" : ""}`}>{children}</div>
        {footer && <footer className="flex flex-wrap items-center justify-end gap-3 border-t border-rule px-6 py-4">{footer}</footer>}
      </div>
    </div>
  );
}

const EFFECTIVE_STYLE: Record<EffectiveState, string> = {
  current: "bg-state-current-wash text-state-current",
  pending: "bg-state-pending-wash text-state-pending",
  expired: "bg-state-expired-wash text-state-expired",
  unapproved: "bg-state-unapproved-wash text-state-unapproved",
  retired: "bg-state-retired-wash text-state-retired",
};

export function EffectiveBadge({ state }: { state: EffectiveState }) {
  return <span data-testid="effective-badge" className={`inline-block rounded px-2 py-0.5 text-sm font-bold ${EFFECTIVE_STYLE[state]}`}>{EFFECTIVE_LABELS[state]}</span>;
}

const PROCESSING_STYLE: Record<ProcessingStatus, string> = {
  pending: "bg-state-pending-wash text-state-pending",
  processing: "bg-state-pending-wash text-state-pending",
  processed: "bg-state-current-wash text-state-current",
  failed: "bg-state-expired-wash text-state-expired",
};

export function ProcessingBadge({ status }: { status: ProcessingStatus }) {
  return <span data-testid="processing-badge" className={`inline-block rounded px-2 py-0.5 text-sm font-bold ${PROCESSING_STYLE[status]}`}>{PROCESSING_LABELS[status]}</span>;
}

export function Notice({ kind, children, action }: { kind: "error" | "success" | "info" | "warning"; children: ReactNode; action?: ReactNode }) {
  const style = {
    error: "border-state-expired bg-state-expired-wash text-state-expired",
    success: "border-state-current bg-state-current-wash text-state-current",
    info: "border-signal bg-signal-wash text-signal-dark",
    warning: "border-state-unapproved bg-state-unapproved-wash text-state-unapproved",
  }[kind];
  return (
    <div role={kind === "error" ? "alert" : "status"} className={`flex items-start justify-between gap-4 rounded-md border-l-4 px-4 py-3 text-sm font-bold ${style}`}>
      <div>{children}</div>
      {action}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div data-testid="empty-state" className="border border-dashed border-rule-strong bg-sheet px-6 py-12 text-center">
      <h3 className="text-xl font-semibold">{title}</h3>
      {children && <p className="mx-auto mt-2 max-w-[52ch] text-ink-soft">{children}</p>}
      {action && <div className="mt-5 flex justify-center gap-3">{action}</div>}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return <p role="status" className="px-1 py-8 text-ink-soft">{label}...</p>;
}

export function Field({ label, error, hint, children, htmlFor }: { label: string; error?: string; hint?: string; children: ReactNode; htmlFor: string }) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error && <p className="hint">{hint}</p>}
      {error && <p className="field-error" id={`${htmlFor}-error`}>{error}</p>}
    </div>
  );
}
