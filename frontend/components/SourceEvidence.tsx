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
      {splitByExcerpt(text, excerpt).map((part, i) =>
        part.hit ? (
          <mark key={i} data-testid="excerpt-mark" className="bg-signal-wash text-signal-dark font-semibold px-1 py-0.5 rounded border-b-2 border-signal">
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        )
      )}
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
  if (doc.error || !doc.data) return <Notice kind="error" action={<button className="btn btn-secondary text-xs" onClick={doc.reload}>Try again</button>}>{doc.error ? errorMessage(doc.error) : "Source not found."}</Notice>;
  const d = doc.data;
  if (d.processing_status !== "processed") {
    return <Notice kind="error">{d.title} has no readable text{d.error_message ? `: ${d.error_message}` : "."}</Notice>;
  }

  return (
    <section aria-label="Source evidence" data-testid="source-evidence" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-xl border border-rule bg-paper">
        <div>
          <h3 className="font-serif text-base font-bold text-ink">{d.title}</h3>
          <p className="text-xs text-ink-muted">{d.filename}{d.archived_at ? " (archived)" : ""}</p>
        </div>
        <div className="flex items-center gap-2">
          <ProcessingBadge status={d.processing_status} />
          {isPdf && (
            <a className="btn btn-secondary text-xs" target="_blank" rel="noreferrer" href={api.fileUrl(d.id, true, pageNo)}>
              Open original at page {pageNo}
            </a>
          )}
          <a className="btn btn-secondary text-xs" href={api.fileUrl(d.id)}>Download</a>
        </div>
      </div>

      {isPdf && d.page_count ? (
        <div className="flex items-center gap-3 bg-sheet p-2 rounded-lg border border-rule w-fit" role="group" aria-label="PDF page">
          <button className="btn btn-secondary text-xs py-1 px-2.5" disabled={pageNo <= 1} onClick={() => setPageNo(pageNo - 1)}>Previous page</button>
          <span aria-live="polite" className="text-xs font-semibold text-ink px-1">Page {pageNo} of {d.page_count}</span>
          <button className="btn btn-secondary text-xs py-1 px-2.5" disabled={pageNo >= d.page_count} onClick={() => setPageNo(pageNo + 1)}>Next page</button>
        </div>
      ) : null}

      <div className="space-y-3">
        {sections.loading && <Loading label="Loading text" />}
        {sections.error && <Notice kind="error">{errorMessage(sections.error)}</Notice>}
        {sections.data?.items.length === 0 && <p className="text-xs text-ink-muted italic">No text was extracted for this location.</p>}
        {sections.data?.items.map((s) => (
          <article key={s.id} className="rounded-xl border border-rule bg-sheet p-4 space-y-1.5 shadow-xs">
            <h4 className="text-[11px] font-semibold uppercase tracking-wider text-signal">{sectionLabel(s)}</h4>
            <p className="whitespace-pre-wrap font-serif text-sm leading-relaxed text-ink">
              <Highlighted text={s.text || "(This page has no extractable text.)"} excerpt={excerpt} />
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
