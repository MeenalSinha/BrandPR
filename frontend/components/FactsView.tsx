"use client";
import Link from "next/link";
import { useState } from "react";

import { FactDrawer } from "@/components/FactDrawer";
import { FactForm } from "@/components/FactForm";
import { useBrand, useToast } from "@/components/providers";
import { EffectiveBadge, EmptyState, Loading, Notice } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { CATEGORY_LABELS, formatDate, reviewText, STATUS_LABELS } from "@/lib/format";
import { useDebounced, useResource } from "@/lib/hooks";
import type { EffectiveState, Fact } from "@/types/api";

const PAGE = 25;
type Quick = "all" | "current" | "review" | "expired" | "unapproved";
const BAR: Record<EffectiveState, string> = {
  current: "border-state-current", pending: "border-state-pending", expired: "border-state-expired", unapproved: "border-state-unapproved", retired: "border-state-retired",
};

export function FactsView() {
  const { brand, actor } = useBrand();
  const toast = useToast();
  const [quick, setQuick] = useState<Quick>("all");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<Fact | null>(null);
  const [editing, setEditing] = useState<Fact | "new" | null>(null);
  const q = useDebounced(search);
  const brandId = brand?.id;

  const summary = useResource(brandId ? () => api.factSummary(brandId) : null, [brandId]);
  const params: Record<string, string | number | undefined> = {
    limit: PAGE, offset, q: q.trim() || undefined, category: category || undefined, sort: "name",
    ...(quick === "current" || quick === "expired" || quick === "unapproved" ? { effective_state: quick } : {}),
    ...(quick === "review" ? { review_within_days: summary.data?.review_warning_days ?? 30 } : {}),
  };
  const facts = useResource(brandId ? () => api.listFacts(brandId, params) : null, [brandId, quick, q, category, offset, quick === "review" ? summary.data?.review_warning_days : 0]);
  const docs = useResource(brandId && editing ? () => api.listDocuments(brandId) : null, [brandId, Boolean(editing)]);

  if (!brand) return <EmptyState title="Create a brand to begin">Approved facts belong to a brand. Use New brand in the sidebar.</EmptyState>;

  const s = summary.data;
  const counts: Record<Quick, number | undefined> = {
    all: s?.total, current: s?.by_effective_state.current, expired: s?.by_effective_state.expired, unapproved: s?.by_effective_state.unapproved,
    review: s ? (s.by_review_state.overdue ?? 0) + (s.by_review_state.due_soon ?? 0) : undefined,
  };
  const labels: Record<Quick, string> = { all: "All", current: "Current", review: "Review due", expired: "Expired", unapproved: "Unapproved" };
  const filtered = quick !== "all" || q.trim() !== "" || category !== "";
  const refresh = () => { facts.reload(); summary.reload(); };
  const changed = (f: Fact, message: string) => { setOpen(f); toast.push("success", message); refresh(); };

  return (
    <div>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-semibold">Approved facts</h1>
          <p className="mt-1 text-ink-soft">What {brand.name} has approved BrandPR to treat as true, with the source behind each fact.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setEditing("new")}>New fact</button>
      </header>

      <div className="mt-6 flex flex-wrap gap-2" role="group" aria-label="Filter by state">
        {(Object.keys(labels) as Quick[]).map((k) => (
          <button key={k} aria-pressed={quick === k} onClick={() => { setQuick(k); setOffset(0); }}
                  className={`rounded-md border px-3 py-1.5 text-sm font-bold ${quick === k ? "border-signal bg-signal text-white" : "border-rule-strong bg-sheet hover:bg-paper"}`}>
            {labels[k]}{counts[k] !== undefined ? ` (${counts[k]})` : ""}
          </button>
        ))}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_240px]">
        <div><label className="label" htmlFor="fact-search">Search facts</label><input id="fact-search" type="search" className="input" placeholder="Name, value, qualification or owner" value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} /></div>
        <div><label className="label" htmlFor="fact-category">Category</label>
          <select id="fact-category" className="input" value={category} onChange={(e) => { setCategory(e.target.value); setOffset(0); }}>
            <option value="">All categories</option>
            {Object.entries(CATEGORY_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
      </div>

      <div className="mt-6">
        {facts.error ? (
          <Notice kind="error" action={<button className="btn btn-secondary" onClick={refresh}>Try again</button>}>{errorMessage(facts.error)}</Notice>
        ) : facts.loading && !facts.data ? <Loading label="Loading facts" /> : facts.data && facts.data.total === 0 ? (
          filtered ? (
            <EmptyState title="No facts match these filters" action={<button className="btn btn-secondary" onClick={() => { setQuick("all"); setSearch(""); setCategory(""); }}>Clear filters</button>} />
          ) : (
            <EmptyState title="No approved facts yet" action={<><button className="btn btn-primary" onClick={() => setEditing("new")}>Create the first fact</button><Link className="btn btn-secondary" href="/knowledge">Upload a source document</Link></>}>
              Add the product specifications, claims and terminology {brand.name} has signed off. Each fact keeps the source it came from.
            </EmptyState>
          )
        ) : facts.data ? (
          <>
            <div className="overflow-x-auto bg-sheet">
              <table className="w-full min-w-[820px] text-left">
                <thead><tr className="border-b border-rule-strong text-sm text-ink-soft">
                  <th className="px-4 py-3 font-bold">Fact</th><th className="px-4 py-3 font-bold">Source</th><th className="px-4 py-3 font-bold">Validity</th><th className="px-4 py-3"><span className="sr-only">Actions</span></th>
                </tr></thead>
                <tbody>
                  {facts.data.items.map((f) => (
                    <tr key={f.id} data-testid="fact-row" className="border-b border-rule align-top">
                      <td className={`border-l-4 px-4 py-4 ${BAR[f.effective_state]}`}>
                        <button className="text-left font-serif text-lg font-semibold text-signal-dark hover:underline" onClick={() => setOpen(f)}>{f.name}</button>
                        <p className="font-serif text-2xl">{f.value}{f.unit ? <span className="ml-1 text-base text-ink-soft">{f.unit}</span> : null}</p>
                        {f.qualifications && <p className="mt-1 max-w-[46ch] text-sm text-ink-soft">{f.qualifications}</p>}
                        <p className="mt-1 text-sm text-ink-faint">{CATEGORY_LABELS[f.category]}</p>
                      </td>
                      <td className="px-4 py-4 text-sm">
                        {f.source ? (
                          <button className="text-left font-bold text-signal underline-offset-2 hover:underline" onClick={() => setOpen(f)}>{f.source.title}{f.source_page ? `, page ${f.source_page}` : ""}</button>
                        ) : <span className="text-ink-soft">Manual: {f.source_note}</span>}
                        {f.source_excerpt_verified === false && <p className="mt-1 font-bold text-state-unapproved">Passage not found in source</p>}
                      </td>
                      <td className="px-4 py-4 text-sm">
                        <EffectiveBadge state={f.effective_state} />
                        {f.status !== "active" && <p className="mt-1 font-bold">{STATUS_LABELS[f.status]}</p>}
                        <p className="mt-1">{f.expires_at ? `Valid until ${formatDate(f.expires_at)}` : <span className="font-bold text-state-unapproved">No expiry date recorded</span>}</p>
                        {reviewText(f.review_state, f.review_date) && <p className={f.review_state === "overdue" ? "font-bold text-state-expired" : f.review_state === "due_soon" ? "font-bold text-state-unapproved" : "text-ink-soft"}>{reviewText(f.review_state, f.review_date)}</p>}
                      </td>
                      <td className="whitespace-nowrap px-4 py-4 text-right">
                        <button className="btn btn-quiet" onClick={() => setEditing(f)} aria-label={`Edit ${f.name}`}>Edit</button>
                        <button className="btn btn-quiet" onClick={() => setOpen(f)} aria-label={`Details for ${f.name}`}>Details</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex items-center justify-between text-sm">
              <p>Showing {offset + 1} to {Math.min(offset + PAGE, facts.data.total)} of {facts.data.total}</p>
              <div className="flex gap-2">
                <button className="btn btn-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                <button className="btn btn-secondary" disabled={offset + PAGE >= facts.data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
              </div>
            </div>
          </>
        ) : null}
      </div>

      {open && !editing && <FactDrawer fact={open} actor={actor} onClose={() => setOpen(null)} onEdit={(f) => setEditing(f)} onChanged={changed} />}
      {editing && (
        docs.loading && !docs.data ? <Loading label="Loading documents" /> : (
          <FactForm brandId={brand.id} fact={editing === "new" ? undefined : editing} documents={docs.data?.items ?? []} actor={actor} onClose={() => setEditing(null)}
            onSaved={(saved) => {
              const wasNew = editing === "new";
              setEditing(null);
              setOpen(wasNew ? null : saved);
              toast.push("success", wasNew ? `Fact "${saved.name}" saved as ${STATUS_LABELS[saved.status].toLowerCase()}.` : `Changes to "${saved.name}" saved.`);
              refresh();
            }} />
        )
      )}
    </div>
  );
}
