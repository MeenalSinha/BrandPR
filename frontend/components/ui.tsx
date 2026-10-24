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
    <div className={`fixed inset-0 z-40 flex bg-ink/40 backdrop-blur-sm transition-opacity duration-150 ${drawer ? "justify-end" : "items-start justify-center overflow-y-auto px-4 py-12"}`}
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
           className={drawer ? "drawer-panel flex h-full w-full max-w-[760px] flex-col border-l border-rule bg-sheet shadow-dialog" : "w-full max-w-[620px] rounded-xl border border-rule bg-sheet shadow-dialog"}>
        <header className="flex items-start justify-between gap-4 border-b border-rule/80 px-6 py-4.5 bg-paper/40">
          <div>
            <h2 id={titleId} className="text-xl font-semibold text-ink">{title}</h2>
            {description && <p className="mt-1 text-sm text-ink-soft">{description}</p>}
          </div>
          <button type="button" data-close onClick={onClose} className="btn btn-quiet text-xs uppercase tracking-wider font-semibold" aria-label="Close dialog">Close</button>
        </header>
        <div className={`px-6 py-5 ${drawer ? "flex-1 overflow-y-auto" : ""}`}>{children}</div>
        {footer && <footer className="flex flex-wrap items-center justify-end gap-3 border-t border-rule/80 px-6 py-4 bg-paper/30">{footer}</footer>}
      </div>
    </div>
  );
}

const EFFECTIVE_STYLE: Record<EffectiveState, string> = {
  current: "bg-state-current-wash text-state-current border-state-current-border",
  pending: "bg-state-pending-wash text-state-pending border-state-pending-border",
  expired: "bg-state-expired-wash text-state-expired border-state-expired-border",
  unapproved: "bg-state-unapproved-wash text-state-unapproved border-state-unapproved-border",
  retired: "bg-state-retired-wash text-state-retired border-state-retired-border",
};

export function EffectiveBadge({ state }: { state: EffectiveState }) {
  return <span data-testid="effective-badge" className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide ${EFFECTIVE_STYLE[state]}`}><span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />{EFFECTIVE_LABELS[state]}</span>;
}

const PROCESSING_STYLE: Record<ProcessingStatus, string> = {
  pending: "bg-state-pending-wash text-state-pending border-state-pending-border",
  processing: "bg-state-pending-wash text-state-pending border-state-pending-border",
  processed: "bg-state-current-wash text-state-current border-state-current-border",
  failed: "bg-state-expired-wash text-state-expired border-state-expired-border",
};

export function ProcessingBadge({ status }: { status: ProcessingStatus }) {
  return <span data-testid="processing-badge" className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide ${PROCESSING_STYLE[status]}`}><span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />{PROCESSING_LABELS[status]}</span>;
}

export function Notice({ kind, children, action }: { kind: "error" | "success" | "info" | "warning"; children: ReactNode; action?: ReactNode }) {
  const style = {
    error: "border-state-expired bg-state-expired-wash text-state-expired",
    success: "border-state-current bg-state-current-wash text-state-current",
    info: "border-signal bg-signal-wash text-signal-dark",
    warning: "border-state-unapproved bg-state-unapproved-wash text-state-unapproved",
  }[kind];
  return (
    <div role={kind === "error" ? "alert" : "status"} className={`flex items-start justify-between gap-4 rounded-lg border-l-4 px-4 py-3 text-sm font-semibold shadow-subtle ${style}`}>
      <div className="flex-1">{children}</div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div data-testid="empty-state" className="rounded-xl border border-dashed border-rule bg-sheet px-6 py-12 text-center shadow-subtle">
      <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-paper text-ink-faint">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
      </div>
      <h3 className="text-lg font-semibold text-ink">{title}</h3>
      {children && <p className="mx-auto mt-2 max-w-[50ch] text-sm text-ink-soft leading-relaxed">{children}</p>}
      {action && <div className="mt-5 flex justify-center gap-3">{action}</div>}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 px-1 py-8 text-sm text-ink-soft">
      <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-signal border-t-transparent" aria-hidden />
      <span>{label}...</span>
    </div>
  );
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
