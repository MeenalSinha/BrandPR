"use client";
import { useState } from "react";

import { Loading, Notice, ProcessingBadge } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { splitByExcerpt } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { DocumentSection } from "@/types/api";

function Highlighted({ text, excerpt }: { text: string; excerpt?: string | null }) {
  return (
    <>
      {splitByExcerpt(text, excerpt).map((part, i) => (part.hit ? <mark key={i} data-testid="excerpt-mark">{part.text}</mark> : <span key={i}>{part.text}</span>))}
    </>
  );
}

function sectionLabel(s: DocumentSection): string {
  if (s.kind === "page") return `Page ${s.page_number}`;
  if (s.kind === "text_block") return `Lines ${s.line_start} to ${s.line_end}`;
  return `Rows ${s.row_start} to ${s.row_end}`;
}

/**
 * Shows the extracted text of a source document with the supporting passage marked.
 * For PDFs it shows one page at a time and links to the original file at that page.
 */
export function SourceEvidence({ documentId, page, excerpt }: { documentId: string; page?: number | null; excerpt?: string | null }) {
  const [pageNo, setPageNo] = useState<number>(page ?? 1);
  const doc = useResource(() => api.getDocument(documentId), [documentId]);
  const isPdf = doc.data?.source_type === "pdf";
  const sections = useResource(
    doc.data ? () => api.getSections(documentId, isPdf ? pageNo : undefined) : null,
    [documentId, pageNo, doc.data?.id, isPdf],
  );

  if (doc.loading) return <Loading label="Loading source" />;
  if (doc.error || !doc.data) return <Notice kind="error" action={<button className="btn btn-secondary" onClick={doc.reload}>Try again</button>}>{doc.error ? errorMessage(doc.error) : "Source not found."}</Notice>;
  const d = doc.data;
  if (d.processing_status !== "processed") {
    return <Notice kind="error">{d.title} has no readable text{d.error_message ? `: ${d.error_message}` : "."}</Notice>;
  }

  return (
    <section aria-label="Source evidence" data-testid="source-evidence">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">{d.title}</h3>
          <p className="text-sm text-ink-soft">{d.filename}{d.archived_at ? " (archived)" : ""}</p>
        </div>
        <div className="flex items-center gap-2">
          <ProcessingBadge status={d.processing_status} />
          {isPdf && <a className="btn btn-secondary" target="_blank" rel="noreferrer" href={api.fileUrl(d.id, true, pageNo)}>Open original at page {pageNo}</a>}
          <a className="btn btn-secondary" href={api.fileUrl(d.id)}>Download</a>
        </div>
      </div>

      {isPdf && d.page_count ? (
        <div className="mt-4 flex items-center gap-3" role="group" aria-label="PDF page">
          <button className="btn btn-secondary" disabled={pageNo <= 1} onClick={() => setPageNo(pageNo - 1)}>Previous page</button>
          <span aria-live="polite" className="text-sm font-bold">Page {pageNo} of {d.page_count}</span>
          <button className="btn btn-secondary" disabled={pageNo >= d.page_count} onClick={() => setPageNo(pageNo + 1)}>Next page</button>
        </div>
      ) : null}

      <div className="mt-4 space-y-4">
        {sections.loading && <Loading label="Loading text" />}
        {sections.error && <Notice kind="error">{errorMessage(sections.error)}</Notice>}
        {sections.data?.items.length === 0 && <p className="text-ink-soft">No text was extracted for this location.</p>}
        {sections.data?.items.map((s) => (
          <article key={s.id} className="border-l-4 border-rule-strong bg-paper px-4 py-3">
            <h4 className="mb-1 text-sm font-bold text-ink-soft">{sectionLabel(s)}</h4>
            <p className="whitespace-pre-wrap font-serif text-[17px] leading-relaxed"><Highlighted text={s.text || "(This page has no extractable text.)"} excerpt={excerpt} /></p>
          </article>
        ))}
      </div>
    </section>
  );
}
