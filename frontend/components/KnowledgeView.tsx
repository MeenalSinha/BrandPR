"use client";
import { Fragment, type DragEvent, type FormEvent, useEffect, useRef, useState } from "react";

import { SourceEvidence } from "@/components/SourceEvidence";
import { useBrand, useToast } from "@/components/providers";
import { Dialog, EmptyState, Loading, Notice, ProcessingBadge } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { SourceDocument, TableData } from "@/types/api";
import { IconKnowledge, IconPlus, IconExternalLink, IconAlert } from "@/components/Icons";

const TYPE_LABEL = { pdf: "PDF", text: "Text", csv: "CSV" } as const;

function contentSummary(d: SourceDocument): string {
  if (d.processing_status !== "processed") return "";
  if (d.source_type === "pdf") return `${d.page_count} page${d.page_count === 1 ? "" : "s"}`;
  if (d.source_type === "csv") return `${d.char_count.toLocaleString()} characters`;
  return `${d.section_count} block${d.section_count === 1 ? "" : "s"}`;
}

function UploadPanel({ brandId, onUploaded }: { brandId: string; onUploaded: () => void }) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [result, setResult] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return setResult({ kind: "error", text: "Choose a PDF, text or CSV file first." });
    setBusy(true);
    setResult(null);
    try {
      const doc = await api.uploadDocument(brandId, file, title);
      if (doc.processing_status === "processed") {
        setResult({ kind: "success", text: `${doc.title} was read successfully (${contentSummary(doc)}).` });
        toast.push("success", `Uploaded ${doc.title}.`);
      } else {
        setResult({ kind: "error", text: `${doc.title} was saved but could not be processed: ${doc.error_message ?? "unknown reason"}` });
      }
      setFile(null);
      setTitle("");
      if (input.current) input.current.value = "";
      onUploaded();
    } catch (err) {
      setResult({ kind: "error", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) setFile(f); };

  return (
    <form onSubmit={submit} className="bg-sheet rounded-xl border border-rule shadow-subtle p-6" aria-label="Upload a source document" noValidate>
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-signal mb-1">
        <IconKnowledge className="w-3.5 h-3.5" />
        <span>Source Ingestion</span>
      </div>
      <h2 className="text-xl font-serif font-bold text-ink">Upload a source document</h2>
      <p className="mt-1 text-sm text-ink-muted">PDF, plain text or CSV. Uploading a document does not approve anything in it.</p>
      
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        className={`mt-4 rounded-xl border-2 border-dashed p-6 text-center transition-all ${
          drag ? "border-signal bg-signal-wash" : "border-rule hover:border-signal/40 bg-paper/50"
        }`}
      >
        <div className="flex flex-col items-center justify-center gap-2">
          <label htmlFor="document-file" className="btn btn-secondary cursor-pointer shadow-xs">Choose file</label>
          <input id="document-file" ref={input} type="file" accept=".pdf,.txt,.csv,application/pdf,text/plain,text/csv" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <p className="text-sm text-ink-muted font-medium" data-testid="chosen-file">
            {file ? `${file.name} (${formatBytes(file.size)})` : "or drag and drop your file here"}
          </p>
          <p className="text-xs text-ink-faint">Supports multi-page PDFs, brand spec sheets, and CSV tabular datasets.</p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div className="min-w-[240px] flex-1">
          <label className="block text-xs font-semibold text-ink mb-1" htmlFor="document-title">
            Title
          </label>
          <input
            id="document-title"
            className="input text-sm"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Optional, defaults to the file name"
            maxLength={300}
          />
        </div>
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Uploading and reading..." : "Upload document"}
        </button>
      </div>
      {result && <div className="mt-4"><Notice kind={result.kind}>{result.text}</Notice></div>}
    </form>
  );
}

function CsvTable({ id }: { id: string }) {
  const t = useResource<TableData>(() => api.getTable(id, 0, 100), [id]);
  if (t.loading) return <Loading label="Loading table" />;
  if (t.error || !t.data) return <Notice kind="error">{errorMessage(t.error)}</Notice>;
  return (
    <div className="overflow-x-auto rounded-xl border border-rule bg-sheet">
      <div className="p-3 bg-paper border-b border-rule flex items-center justify-between text-xs text-ink-muted">
        <span>Showing {t.data.rows.length} of {t.data.total_rows} rows</span>
        <span className="font-mono">CSV Matrix</span>
      </div>
      <table className="w-full text-left text-xs">
        <thead className="bg-paper text-ink-muted uppercase border-b border-rule">
          <tr>
            <th className="px-3 py-2.5 font-semibold">Row</th>
            {t.data.headers.map((h) => <th key={h} className="px-3 py-2.5 font-semibold">{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-rule font-mono">
          {t.data.rows.map((r) => (
            <tr key={r.row_number} className="hover:bg-paper/50">
              <td className="px-3 py-2 text-ink-muted">{r.row_number}</td>
              {t.data!.headers.map((h) => <td key={h} className="px-3 py-2 text-ink">{r.cells[h]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentDrawer({ doc, onClose, onChanged }: { doc: SourceDocument; onClose: () => void; onChanged: (message: string) => void }) {
  const [confirm, setConfirm] = useState<"archive" | "delete" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(kind: "archive" | "delete") {
    setBusy(true);
    setError(null);
    try {
      if (kind === "archive") await api.archiveDocument(doc.id); else await api.deleteDocument(doc.id);
      onChanged(kind === "archive" ? `${doc.title} was archived.` : `${doc.title} was deleted.`);
    } catch (err) {
      setError(errorMessage(err));
      setConfirm(null);
    } finally {
      setBusy(false);
    }
  }
  const meta: [string, string][] = [
    ["File name", doc.filename], ["Type", TYPE_LABEL[doc.source_type]], ["Size", formatBytes(doc.size_bytes)], ["Uploaded", formatDate(doc.uploaded_at)],
    ["Processed", doc.processed_at ? formatDate(doc.processed_at) : "Not processed"], ["Cited by", `${doc.fact_count} fact${doc.fact_count === 1 ? "" : "s"}`],
    ["Content hash", doc.content_hash.slice(0, 16)],
  ];
  return (
    <Dialog variant="drawer" title={doc.title} onClose={onClose}
      footer={<>
        {doc.processing_status === "processed" && <a className="btn btn-secondary text-xs" href={api.fileUrl(doc.id)}>Download original</a>}
        {!doc.archived_at && <button className="btn btn-secondary text-xs" onClick={() => setConfirm("archive")}>Archive</button>}
        <button className="btn btn-danger text-xs" onClick={() => setConfirm("delete")}>Delete</button>
      </>}>
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <ProcessingBadge status={doc.processing_status} />
          {doc.archived_at && <span className="text-xs font-semibold px-2 py-0.5 rounded bg-surface-100 text-ink-muted border border-rule">Archived {formatDate(doc.archived_at)}</span>}
        </div>
        {error && <Notice kind="error">{error}</Notice>}
        {doc.error_message && <Notice kind="error">{doc.error_message}</Notice>}
        {confirm && (
          <Notice kind="warning" action={<div className="flex gap-2"><button className="btn btn-secondary text-xs" disabled={busy} onClick={() => run(confirm)}>{busy ? "Working..." : confirm === "archive" ? "Confirm archive" : "Confirm delete"}</button><button className="btn btn-quiet text-xs" onClick={() => setConfirm(null)}>Cancel</button></div>}>
            {confirm === "archive" ? "Archived documents stay attached to the facts that cite them but cannot be cited again." : "Deleting removes the document and its extracted text permanently. Documents cited by facts cannot be deleted."}
          </Notice>
        )}
        <dl className="grid grid-cols-[130px_1fr] gap-x-4 gap-y-2 text-sm bg-paper/60 p-4 rounded-xl border border-rule">
          {meta.map(([k, v]) => (
            <Fragment key={k}>
              <dt className="font-semibold text-ink-muted text-xs uppercase tracking-wider">{k}</dt>
              <dd className="break-all text-ink font-medium">{v}</dd>
            </Fragment>
          ))}
        </dl>
        {doc.processing_status === "processed" && (
          doc.source_type === "csv" ? (
            <div className="space-y-2">
              <h3 className="text-base font-serif font-bold text-ink">Extracted Table Data</h3>
              <CsvTable id={doc.id} />
            </div>
          ) : (
            <SourceEvidence documentId={doc.id} />
          )
        )}
      </div>
    </Dialog>
  );
}

export function KnowledgeView() {
  const { brand } = useBrand();
  const toast = useToast();
  const [showArchived, setShowArchived] = useState(false);
  const [open, setOpen] = useState<SourceDocument | null>(null);
  const brandId = brand?.id;
  const docs = useResource(brandId ? () => api.listDocuments(brandId, { includeArchived: showArchived }) : null, [brandId, showArchived]);
  const facts = useResource(brandId ? () => api.factSummary(brandId) : null, [brandId]);

  const busy = docs.data?.items.some((d) => d.processing_status === "pending" || d.processing_status === "processing");
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(docs.reload, 2000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy]);

  if (!brand) return <EmptyState title="Create a brand to begin">Source documents belong to a brand. Use New brand in the sidebar.</EmptyState>;

  return (
    <div className="space-y-8">
      <header className="border-b border-rule pb-5">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-signal mb-1">
          <IconKnowledge className="w-3.5 h-3.5" />
          <span>Verified Knowledge Base</span>
        </div>
        <h1 className="text-3xl font-serif font-bold tracking-tight text-ink">Brand Knowledge</h1>
        <div className="mt-2 max-w-2xl">
          <p className="font-serif text-lg font-semibold text-ink" data-testid="brand-name">{brand.name}</p>
          <p className="text-sm text-ink-muted leading-relaxed">{brand.description ?? "No description yet."}</p>
          <p className="mt-1 text-xs text-signal font-medium">
            {docs.data ? `${docs.data.total} source document${docs.data.total === 1 ? "" : "s"}` : ""}
            {facts.data ? ` • ${facts.data.total} approved fact${facts.data.total === 1 ? "" : "s"}` : ""}
          </p>
        </div>
      </header>

      <UploadPanel brandId={brand.id} onUploaded={() => { docs.reload(); facts.reload(); }} />

      <section aria-label="Source documents" className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-serif font-bold text-ink">Source Documents</h2>
            <p className="text-xs text-ink-muted">Raw verified documents providing evidence ground truth.</p>
          </div>
          <label className="flex items-center gap-2 text-xs font-medium text-ink cursor-pointer">
            <input type="checkbox" className="rounded border-rule text-signal focus:ring-signal" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
            <span>Show archived</span>
          </label>
        </div>
        {docs.error ? (
          <Notice kind="error" action={<button className="btn btn-secondary text-xs" onClick={docs.reload}>Try again</button>}>
            {errorMessage(docs.error)}
          </Notice>
        ) : docs.loading && !docs.data ? (
          <Loading label="Loading documents" />
        ) : docs.data && docs.data.total === 0 ? (
          <EmptyState title="No source documents yet">
            Upload a PDF, text or CSV file above to start this brand&apos;s source library. Facts can then cite exact pages.
          </EmptyState>
        ) : docs.data ? (
          <div className="overflow-x-auto rounded-xl border border-rule bg-sheet shadow-subtle">
            <table className="w-full min-w-[760px] text-left text-xs">
              <thead className="bg-paper text-ink-muted uppercase border-b border-rule">
                <tr>
                  <th className="px-4 py-3 font-semibold tracking-wider">Document</th>
                  <th className="px-4 py-3 font-semibold tracking-wider">Status</th>
                  <th className="px-4 py-3 font-semibold tracking-wider">Content</th>
                  <th className="px-4 py-3 font-semibold tracking-wider">Cited by</th>
                  <th className="px-4 py-3 font-semibold tracking-wider">Uploaded</th>
                  <th className="px-4 py-3 font-semibold tracking-wider text-right"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {docs.data.items.map((d) => (
                  <tr key={d.id} data-testid="document-row" className="hover:bg-paper/40 transition align-top">
                    <td className="px-4 py-3.5">
                      <button className="text-left font-semibold text-signal hover:text-signal-dark hover:underline transition" onClick={() => setOpen(d)}>
                        {d.title}
                      </button>
                      <p className="text-[11px] text-ink-muted mt-0.5">
                        {d.filename} ({TYPE_LABEL[d.source_type]}, {formatBytes(d.size_bytes)}){d.archived_at ? " • archived" : ""}
                      </p>
                    </td>
                    <td className="px-4 py-3.5">
                      <ProcessingBadge status={d.processing_status} />
                      {d.error_message && <p className="mt-1 max-w-[34ch] text-[11px] font-semibold text-terracotta">{d.error_message}</p>}
                    </td>
                    <td className="px-4 py-3.5 text-xs text-ink">{contentSummary(d) || "No content"}</td>
                    <td className="px-4 py-3.5 text-xs text-ink-muted font-medium">{d.fact_count} fact{d.fact_count === 1 ? "" : "s"}</td>
                    <td className="px-4 py-3.5 text-xs text-ink-muted">{formatDate(d.uploaded_at)}</td>
                    <td className="px-4 py-3.5 text-right">
                      <button className="btn btn-quiet text-xs" onClick={() => setOpen(d)} aria-label={`Inspect ${d.title}`}>
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
      {open && <DocumentDrawer doc={open} onClose={() => setOpen(null)} onChanged={(m) => { setOpen(null); toast.push("success", m); docs.reload(); facts.reload(); }} />}
    </div>
  );
}
