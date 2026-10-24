"use client";
import { Fragment, type DragEvent, type FormEvent, useEffect, useRef, useState } from "react";

import { SourceEvidence } from "@/components/SourceEvidence";
import { useBrand, useToast } from "@/components/providers";
import { Dialog, EmptyState, Loading, Notice, ProcessingBadge } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { SourceDocument, TableData } from "@/types/api";

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
    <form onSubmit={submit} className="bg-sheet p-5" aria-label="Upload a source document" noValidate>
      <h2 className="text-xl font-semibold">Upload a source document</h2>
      <p className="mt-1 text-sm text-ink-soft">PDF, plain text or CSV. Uploading a document does not approve anything in it.</p>
      <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
           className={`mt-4 border-2 border-dashed px-4 py-6 text-center ${drag ? "border-signal bg-signal-wash" : "border-rule-strong"}`}>
        <label htmlFor="document-file" className="btn btn-secondary cursor-pointer">Choose file</label>
        <input id="document-file" ref={input} type="file" accept=".pdf,.txt,.csv,application/pdf,text/plain,text/csv" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <p className="mt-2 text-sm" data-testid="chosen-file">{file ? `${file.name} (${formatBytes(file.size)})` : "or drop a file here"}</p>
      </div>
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div className="min-w-[240px] flex-1"><label className="label" htmlFor="document-title">Title</label><input id="document-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Optional, defaults to the file name" maxLength={300} /></div>
        <button className="btn btn-primary" disabled={busy}>{busy ? "Uploading and reading" : "Upload document"}</button>
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
    <div className="overflow-x-auto">
      <p className="mb-2 text-sm text-ink-soft">Showing {t.data.rows.length} of {t.data.total_rows} rows</p>
      <table className="w-full text-left text-sm">
        <thead><tr className="border-b border-rule-strong"><th className="px-2 py-2">Row</th>{t.data.headers.map((h) => <th key={h} className="px-2 py-2 font-bold">{h}</th>)}</tr></thead>
        <tbody>{t.data.rows.map((r) => <tr key={r.row_number} className="border-b border-rule"><td className="px-2 py-2 text-ink-soft">{r.row_number}</td>{t.data!.headers.map((h) => <td key={h} className="px-2 py-2">{r.cells[h]}</td>)}</tr>)}</tbody>
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
        {doc.processing_status === "processed" && <a className="btn btn-secondary" href={api.fileUrl(doc.id)}>Download original</a>}
        {!doc.archived_at && <button className="btn btn-secondary" onClick={() => setConfirm("archive")}>Archive</button>}
        <button className="btn btn-danger" onClick={() => setConfirm("delete")}>Delete</button>
      </>}>
      <div className="space-y-6">
        <div className="flex items-center gap-3"><ProcessingBadge status={doc.processing_status} />{doc.archived_at && <span className="text-sm font-bold text-state-retired">Archived {formatDate(doc.archived_at)}</span>}</div>
        {error && <Notice kind="error">{error}</Notice>}
        {doc.error_message && <Notice kind="error">{doc.error_message}</Notice>}
        {confirm && (
          <Notice kind="warning" action={<div className="flex gap-2"><button className="btn btn-secondary" disabled={busy} onClick={() => run(confirm)}>{busy ? "Working" : confirm === "archive" ? "Confirm archive" : "Confirm delete"}</button><button className="btn btn-quiet" onClick={() => setConfirm(null)}>Cancel</button></div>}>
            {confirm === "archive" ? "Archived documents stay attached to the facts that cite them but cannot be cited again." : "Deleting removes the document and its extracted text permanently. Documents cited by facts cannot be deleted."}
          </Notice>
        )}
        <dl className="grid grid-cols-[130px_1fr] gap-x-4 gap-y-2 text-[15px]">{meta.map(([k, v]) => <Fragment key={k}><dt className="font-bold">{k}</dt><dd className="break-all">{v}</dd></Fragment>)}</dl>
        {doc.processing_status === "processed" && (doc.source_type === "csv" ? <><h3 className="text-xl font-semibold">Table</h3><CsvTable id={doc.id} /></> : <SourceEvidence documentId={doc.id} />)}
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
      <header>
        <h1 className="text-4xl font-semibold">Brand knowledge</h1>
        <div className="mt-2 max-w-[70ch]">
          <p className="font-serif text-xl font-semibold" data-testid="brand-name">{brand.name}</p>
          <p className="text-ink-soft">{brand.description ?? "No description yet."}</p>
          <p className="mt-1 text-sm text-ink-soft">{docs.data ? `${docs.data.total} source document${docs.data.total === 1 ? "" : "s"}` : ""}{facts.data ? `, ${facts.data.total} approved fact${facts.data.total === 1 ? "" : "s"}` : ""}</p>
        </div>
      </header>

      <UploadPanel brandId={brand.id} onUploaded={() => { docs.reload(); facts.reload(); }} />

      <section aria-label="Source documents">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-2xl font-semibold">Source documents</h2>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Show archived</label>
        </div>
        {docs.error ? <Notice kind="error" action={<button className="btn btn-secondary" onClick={docs.reload}>Try again</button>}>{errorMessage(docs.error)}</Notice>
        : docs.loading && !docs.data ? <Loading label="Loading documents" />
        : docs.data && docs.data.total === 0 ? <EmptyState title="No source documents yet">Upload a PDF, text or CSV file above to start this brand&apos;s source library. Facts can then cite exact pages.</EmptyState>
        : docs.data ? (
          <div className="overflow-x-auto bg-sheet">
            <table className="w-full min-w-[760px] text-left">
              <thead><tr className="border-b border-rule-strong text-sm text-ink-soft"><th className="px-4 py-3 font-bold">Document</th><th className="px-4 py-3 font-bold">Status</th><th className="px-4 py-3 font-bold">Content</th><th className="px-4 py-3 font-bold">Cited by</th><th className="px-4 py-3 font-bold">Uploaded</th><th className="px-4 py-3"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {docs.data.items.map((d) => (
                  <tr key={d.id} data-testid="document-row" className="border-b border-rule align-top">
                    <td className="px-4 py-3"><button className="text-left font-bold text-signal-dark hover:underline" onClick={() => setOpen(d)}>{d.title}</button><p className="text-sm text-ink-soft">{d.filename} ({TYPE_LABEL[d.source_type]}, {formatBytes(d.size_bytes)}){d.archived_at ? ", archived" : ""}</p></td>
                    <td className="px-4 py-3"><ProcessingBadge status={d.processing_status} />{d.error_message && <p className="mt-1 max-w-[34ch] text-sm font-bold text-state-expired">{d.error_message}</p>}</td>
                    <td className="px-4 py-3 text-sm">{contentSummary(d) || "No content"}</td>
                    <td className="px-4 py-3 text-sm">{d.fact_count} fact{d.fact_count === 1 ? "" : "s"}</td>
                    <td className="px-4 py-3 text-sm">{formatDate(d.uploaded_at)}</td>
                    <td className="px-4 py-3 text-right"><button className="btn btn-quiet" onClick={() => setOpen(d)} aria-label={`Inspect ${d.title}`}>Inspect</button></td>
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
