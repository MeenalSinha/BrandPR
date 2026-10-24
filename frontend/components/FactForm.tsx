"use client";
import { type FormEvent, useMemo, useState } from "react";

import { Dialog, Field, Notice } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { CATEGORY_LABELS } from "@/lib/format";
import type { Fact, FactCategory, FactCreateInput, FactUpdateInput, SourceDocument } from "@/types/api";

type Errors = Partial<Record<string, string>>;
const MATERIAL = ["name", "value", "category", "qualifications", "unit", "source_document_id", "source_page", "source_excerpt", "source_note"] as const;

interface Form {
  name: string; value: string; category: FactCategory; unit: string; qualifications: string; owner: string;
  valid_from: string; review_date: string; expires_at: string;
  mode: "document" | "manual"; document_id: string; page: string; excerpt: string; note: string;
  approveNow: boolean; reason: string;
}

function initial(f?: Fact): Form {
  return {
    name: f?.name ?? "", value: f?.value ?? "", category: f?.category ?? "general", unit: f?.unit ?? "",
    qualifications: f?.qualifications ?? "", owner: f?.owner ?? "", valid_from: f?.valid_from ?? "",
    review_date: f?.review_date ?? "", expires_at: f?.expires_at ?? "",
    mode: f ? (f.source_document_id ? "document" : "manual") : "manual",
    document_id: f?.source_document_id ?? "", page: f?.source_page ? String(f.source_page) : "",
    excerpt: f?.source_excerpt ?? "", note: f?.source_note ?? "", approveNow: false, reason: "",
  };
}

const nul = (s: string) => (s.trim() === "" ? null : s.trim());

function validate(f: Form, docs: SourceDocument[]): Errors {
  const e: Errors = {};
  if (!f.name.trim()) e.name = "Enter the fact name, for example Battery life.";
  if (!f.value.trim()) e.value = "Enter the approved value or wording.";
  if (f.valid_from && f.expires_at && f.expires_at < f.valid_from) e.expires_at = "Expiry must be on or after the valid-from date.";
  if (f.review_date && f.expires_at && f.review_date > f.expires_at) e.review_date = "Review date must be on or before the expiry date.";
  if (f.mode === "manual" && !f.note.trim()) e.source_note = "Describe how this was verified, because no source document is cited.";
  if (f.mode === "document") {
    const doc = docs.find((d) => d.id === f.document_id);
    if (!f.document_id) e.source_document_id = "Choose the source document.";
    if (f.page.trim()) {
      const n = Number(f.page);
      if (!Number.isInteger(n) || n < 1) e.source_page = "Enter a whole page number, starting at 1.";
      else if (doc?.page_count && n > doc.page_count) e.source_page = `This document has ${doc.page_count} pages.`;
    }
  }
  return e;
}

function toFields(f: Form) {
  const doc = f.mode === "document";
  return {
    name: f.name.trim(), value: f.value.trim(), category: f.category, unit: nul(f.unit), qualifications: nul(f.qualifications),
    owner: nul(f.owner), valid_from: nul(f.valid_from), review_date: nul(f.review_date), expires_at: nul(f.expires_at),
    source_document_id: doc ? f.document_id || null : null,
    source_page: doc && f.page.trim() ? Number(f.page) : null,
    source_excerpt: doc ? nul(f.excerpt) : null,
    source_note: doc ? nul(f.note) ?? null : nul(f.note),
  };
}

export function FactForm({
  brandId, fact, documents, actor, onSaved, onClose,
}: {
  brandId: string; fact?: Fact; documents: SourceDocument[]; actor: string; onSaved: (f: Fact) => void; onClose: () => void;
}) {
  const [form, setForm] = useState<Form>(() => initial(fact));
  const [errors, setErrors] = useState<Errors>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((p) => ({ ...p, [k]: v }));

  const choices = useMemo(() => {
    const usable = documents.filter((d) => d.processing_status === "processed" && !d.archived_at);
    if (fact?.source && !usable.some((d) => d.id === fact.source!.document_id)) {
      return [...usable, { id: fact.source.document_id, title: `${fact.source.title} (archived)`, page_count: fact.source.page_count, source_type: fact.source.source_type } as SourceDocument];
    }
    return usable;
  }, [documents, fact]);
  const selectedDoc = choices.find((d) => d.id === form.document_id);

  const changes = useMemo(() => {
    if (!fact) return {};
    const next = toFields(form) as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(next)) {
      const before = (fact as unknown as Record<string, unknown>)[k === "source_document_id" ? "source_document_id" : k] ?? null;
      if (v !== before) out[k] = v;
    }
    return out;
  }, [fact, form]);
  const demotes = Boolean(fact && fact.status === "active" && MATERIAL.some((k) => k in changes));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBanner(null);
    const found = validate(form, documents);
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      let saved: Fact;
      if (fact) {
        if (!Object.keys(changes).length) { onClose(); return; }
        const body: FactUpdateInput = { ...changes, actor: actor || null, change_reason: nul(form.reason), expected_version: fact.version };
        saved = await api.updateFact(fact.id, body);
      } else {
        const body: FactCreateInput = { ...toFields(form), status: form.approveNow ? "active" : "proposed", actor: actor || null };
        saved = await api.createFact(brandId, body);
      }
      onSaved(saved);
    } catch (err) {
      if (err instanceof ApiError && err.details.length) {
        const mapped: Errors = {};
        for (const d of err.details) if (d.field) mapped[d.field] = d.message;
        setErrors(mapped);
        setBanner(Object.keys(mapped).length ? "Fix the highlighted fields and save again." : err.message);
        if (!Object.keys(mapped).length) setBanner(err.message);
      } else {
        setBanner(errorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  }

  const err = (k: string) => errors[k];
  const aria = (k: string) => ({ "aria-invalid": err(k) ? true : undefined, "aria-describedby": err(k) ? `${k}-error` : undefined });

  return (
    <Dialog title={fact ? "Edit fact" : "New fact"} onClose={onClose}
      description={fact ? `Version ${fact.version}` : "Facts start as proposed. Approving is a separate, explicit step."}
      footer={<><button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button><button form="fact-form" className="btn btn-primary" disabled={busy}>{busy ? "Saving" : fact ? "Save changes" : "Save fact"}</button></>}>
      <form id="fact-form" onSubmit={submit} noValidate className="space-y-5">
        {banner && <Notice kind="error">{banner}</Notice>}
        {demotes && <Notice kind="warning">This fact is approved. Saving changes to its wording, value, qualifications or source returns it to proposed until someone approves it again.</Notice>}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" htmlFor="name" error={err("name")}><input id="name" className="input" value={form.name} onChange={(e) => set("name", e.target.value)} maxLength={200} {...aria("name")} /></Field>
          <Field label="Category" htmlFor="category">
            <select id="category" className="input" value={form.category} onChange={(e) => set("category", e.target.value as FactCategory)}>
              {Object.entries(CATEGORY_LABELS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </Field>
          <Field label="Approved value" htmlFor="value" error={err("value")}><input id="value" className="input" value={form.value} onChange={(e) => set("value", e.target.value)} maxLength={2000} {...aria("value")} /></Field>
          <Field label="Unit" htmlFor="unit" hint="Optional, for example hours or %."><input id="unit" className="input" value={form.unit} onChange={(e) => set("unit", e.target.value)} maxLength={50} /></Field>
        </div>
        <Field label="Qualifications" htmlFor="qualifications" error={err("qualifications")} hint="Conditions the value depends on, for example the test method.">
          <textarea id="qualifications" className="input" rows={2} value={form.qualifications} onChange={(e) => set("qualifications", e.target.value)} maxLength={2000} />
        </Field>

        <fieldset className="space-y-4 border-t border-rule pt-4">
          <legend className="font-serif text-lg font-semibold">Validity and ownership</legend>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Valid from" htmlFor="valid_from" error={err("valid_from")}><input id="valid_from" type="date" className="input" value={form.valid_from} onChange={(e) => set("valid_from", e.target.value)} {...aria("valid_from")} /></Field>
            <Field label="Review date" htmlFor="review_date" error={err("review_date")}><input id="review_date" type="date" className="input" value={form.review_date} onChange={(e) => set("review_date", e.target.value)} {...aria("review_date")} /></Field>
            <Field label="Expires on" htmlFor="expires_at" error={err("expires_at")} hint="Last valid day."><input id="expires_at" type="date" className="input" value={form.expires_at} onChange={(e) => set("expires_at", e.target.value)} {...aria("expires_at")} /></Field>
          </div>
          <Field label="Owner" htmlFor="owner"><input id="owner" className="input" value={form.owner} onChange={(e) => set("owner", e.target.value)} maxLength={200} /></Field>
        </fieldset>

        <fieldset className="space-y-4 border-t border-rule pt-4">
          <legend className="font-serif text-lg font-semibold">Source</legend>
          <div className="flex flex-wrap gap-5" role="radiogroup" aria-label="Source type">
            <label className="flex items-center gap-2"><input type="radio" name="mode" checked={form.mode === "document"} onChange={() => set("mode", "document")} /> Cite a source document</label>
            <label className="flex items-center gap-2"><input type="radio" name="mode" checked={form.mode === "manual"} onChange={() => set("mode", "manual")} /> No document</label>
          </div>
          {form.mode === "document" ? (
            <>
              <div className="grid gap-4 sm:grid-cols-[1fr_160px]">
                <Field label="Source document" htmlFor="source_document_id" error={err("source_document_id")}>
                  <select id="source_document_id" className="input" value={form.document_id} onChange={(e) => set("document_id", e.target.value)} {...aria("source_document_id")}>
                    <option value="">Choose a document</option>
                    {choices.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
                  </select>
                </Field>
                <Field label="Page" htmlFor="source_page" error={err("source_page")} hint={selectedDoc?.source_type === "pdf" && selectedDoc.page_count ? `1 to ${selectedDoc.page_count}` : "PDF only"}>
                  <input id="source_page" inputMode="numeric" className="input" value={form.page} onChange={(e) => set("page", e.target.value)} disabled={Boolean(selectedDoc) && selectedDoc?.source_type !== "pdf"} {...aria("source_page")} />
                </Field>
              </div>
              {!choices.length && <Notice kind="info">No processed documents yet. Upload one on the Brand knowledge page, or choose No document.</Notice>}
              <Field label="Supporting passage" htmlFor="source_excerpt" error={err("source_excerpt")} hint="Paste the sentence from the document that supports this fact. BrandPR checks that it appears there.">
                <textarea id="source_excerpt" className="input" rows={3} value={form.excerpt} onChange={(e) => set("excerpt", e.target.value)} maxLength={4000} />
              </Field>
            </>
          ) : (
            <Field label="How was this verified?" htmlFor="source_note" error={err("source_note")} hint="Required when no document is cited, for example who confirmed it and when.">
              <textarea id="source_note" className="input" rows={2} value={form.note} onChange={(e) => set("note", e.target.value)} maxLength={1000} {...aria("source_note")} />
            </Field>
          )}
        </fieldset>

        {fact ? (
          <Field label="Reason for change" htmlFor="reason" hint="Optional. Saved in the fact's history."><input id="reason" className="input" value={form.reason} onChange={(e) => set("reason", e.target.value)} maxLength={1000} /></Field>
        ) : (
          <label className="flex items-start gap-3 border-t border-rule pt-4">
            <input type="checkbox" className="mt-1" checked={form.approveNow} onChange={(e) => set("approveNow", e.target.checked)} />
            <span><span className="block font-bold">Approve this fact now</span><span className="hint">Approved facts are used to check content. Leave unchecked to save it as proposed.</span></span>
          </label>
        )}
      </form>
    </Dialog>
  );
}
