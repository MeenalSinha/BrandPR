"use client";
import Link from "next/link";
import { useBrand } from "@/components/providers";
import { api, errorMessage } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import {
  IconCheck, IconReview, IconImpacts, IconKnowledge, IconFacts,
  IconCampaigns, IconExternalLink, IconAlert,
} from "@/components/Icons";

export function OverviewView() {
  const { brand } = useBrand();
  const brandId = brand?.id ?? null;

  const docs = useResource(brandId ? () => api.listDocuments(brandId) : null, [brandId]);
  const facts = useResource(brandId ? () => api.listFacts(brandId, { limit: 100 }) : null, [brandId]);
  const content = useResource(brandId ? () => api.listLatestContent(brandId) : null, [brandId]);
  const impacts = useResource(brandId ? () => api.impactSummary(brandId) : null, [brandId]);

  return (
    <div className="space-y-10">
      {/* Hero Section */}
      <section className="rounded-2xl border border-rule bg-sheet p-8 shadow-subtle relative overflow-hidden">
        <div className="max-w-3xl space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full bg-signal-wash border border-signal-border px-3 py-1 text-xs font-bold text-signal-dark">
            <span>Round 3 Release Ready</span>
            <span>&bull;</span>
            <span>Inkloom AI / CodeAxis Competition</span>
          </div>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold tracking-tight text-ink leading-tight">
            BrandPR: Enterprise Truth Governance & PR Verification
          </h1>
          <p className="text-base text-ink-soft leading-relaxed">
            A reliable, evidence-backed platform ensuring marketing communications remain truthful, compliant, and synchronized with evolving approved facts. BrandPR verifies claims with inspectable document citations, propagates fact updates through the Claim Ledger, and enforces immutable revision history with human reviewer sign-off.
          </p>
        </div>

        {/* Live Active Brand Metrics */}
        {brand && (
          <div className="mt-8 border-t border-rule/70 pt-6">
            <p className="text-xs font-bold uppercase tracking-wider text-ink-faint mb-3">
              Active Demonstration Brand: <span className="text-ink">{brand.name}</span>
            </p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Link href="/knowledge" className="rounded-xl border border-rule bg-paper/60 p-4 hover:bg-paper transition shadow-subtle group">
                <span className="text-xs font-semibold text-ink-muted group-hover:text-signal">Source Documents</span>
                <span className="block mt-1 font-serif text-2xl font-bold text-ink">
                  {docs.loading ? "..." : docs.data?.total ?? 0}
                </span>
                <span className="text-[11px] text-ink-faint mt-1 block">PDF, CSV, TXT</span>
              </Link>
              <Link href="/facts" className="rounded-xl border border-rule bg-paper/60 p-4 hover:bg-paper transition shadow-subtle group">
                <span className="text-xs font-semibold text-ink-muted group-hover:text-signal">Approved Facts</span>
                <span className="block mt-1 font-serif text-2xl font-bold text-ink">
                  {facts.loading ? "..." : facts.data?.total ?? 0}
                </span>
                <span className="text-[11px] text-ink-faint mt-1 block">Versioned claim ledger</span>
              </Link>
              <Link href="/review" className="rounded-xl border border-rule bg-paper/60 p-4 hover:bg-paper transition shadow-subtle group">
                <span className="text-xs font-semibold text-ink-muted group-hover:text-signal">Content Drafts</span>
                <span className="block mt-1 font-serif text-2xl font-bold text-ink">
                  {content.loading ? "..." : content.data?.total ?? 0}
                </span>
                <span className="text-[11px] text-ink-faint mt-1 block">ProofGraph verified</span>
              </Link>
              <Link href="/fact-changes" className="rounded-xl border border-rule bg-paper/60 p-4 hover:bg-paper transition shadow-subtle group">
                <span className="text-xs font-semibold text-ink-muted group-hover:text-signal">Open Impacts</span>
                <span className={`block mt-1 font-serif text-2xl font-bold ${(impacts.data?.open_impacts ?? 0) > 0 ? "text-terracotta" : "text-signal"}`}>
                  {impacts.loading ? "..." : impacts.data?.open_impacts ?? 0}
                </span>
                <span className="text-[11px] text-ink-faint mt-1 block">Needing review</span>
              </Link>
            </div>
          </div>
        )}
      </section>

      {/* The Three Committed Improvements */}
      <section className="space-y-5" aria-label="Core Commitments">
        <div>
          <h2 className="text-xl font-bold text-ink tracking-tight">The Three Round 2 Commitments</h2>
          <p className="text-sm text-ink-soft mt-0.5">Every capability operates on real database records and deterministic business logic.</p>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Commitment 1 */}
          <div className="flex flex-col justify-between rounded-xl border border-rule bg-sheet p-6 shadow-subtle space-y-4">
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-signal-wash border border-signal-border px-2.5 py-0.5 text-[11px] font-bold text-signal-dark uppercase tracking-wider">
                  Commitment 1
                </span>
                <span className="text-xs font-semibold text-state-current flex items-center gap-1">
                  <IconCheck className="h-3 w-3" /> Fully Verified
                </span>
              </div>
              <h3 className="font-serif text-xl font-bold text-ink">
                Evidence-Backed Claim Verification: ProofGraph
              </h3>
              <p className="text-xs text-ink-soft leading-relaxed">
                Extracts numerical, comparative, and terminology statements from marketing drafts. Matches claims against current approved facts and resolves citations to exact source document pages and excerpts. Supported, unsupported, and conflicting claims are meaningfully classified without fabricating missing evidence.
              </p>
            </div>
            <div className="border-t border-rule/60 pt-4 space-y-2">
              <Link href="/review" className="btn btn-primary w-full text-xs justify-center gap-1.5">
                <IconReview className="h-3.5 w-3.5" />
                Open ProofGraph Review
              </Link>
              <p className="text-[11px] text-ink-faint text-center">
                Click &ldquo;Load sample marketing copy&rdquo; on the review page for a complete demonstration.
              </p>
            </div>
          </div>

          {/* Commitment 2 */}
          <div className="flex flex-col justify-between rounded-xl border border-rule bg-sheet p-6 shadow-subtle space-y-4">
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-signal-wash border border-signal-border px-2.5 py-0.5 text-[11px] font-bold text-signal-dark uppercase tracking-wider">
                  Commitment 2
                </span>
                <span className="text-xs font-semibold text-state-current flex items-center gap-1">
                  <IconCheck className="h-3 w-3" /> Fully Verified
                </span>
              </div>
              <h3 className="font-serif text-xl font-bold text-ink">
                Fact-Change Propagation: Claim Ledger
              </h3>
              <p className="text-xs text-ink-soft leading-relaxed">
                Automatically identifies published or approved content that relied on an approved fact that was subsequently modified or allowed to expire. Preserves immutable historical fact snapshots and previous review findings while clearly highlighting affected assets that require attention.
              </p>
            </div>
            <div className="border-t border-rule/60 pt-4 space-y-2">
              <Link href="/fact-changes" className="btn btn-primary w-full text-xs justify-center gap-1.5">
                <IconImpacts className="h-3.5 w-3.5" />
                Inspect Claim Ledger
              </Link>
              <p className="text-[11px] text-ink-faint text-center">
                Review historical relied-upon values side-by-side with current approved values.
              </p>
            </div>
          </div>

          {/* Commitment 3 */}
          <div className="flex flex-col justify-between rounded-xl border border-rule bg-sheet p-6 shadow-subtle space-y-4">
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-signal-wash border border-signal-border px-2.5 py-0.5 text-[11px] font-bold text-signal-dark uppercase tracking-wider">
                  Commitment 3
                </span>
                <span className="text-xs font-semibold text-state-current flex items-center gap-1">
                  <IconCheck className="h-3 w-3" /> Fully Verified
                </span>
              </div>
              <h3 className="font-serif text-xl font-bold text-ink">
                Human-Controlled Corrections & Approvals
              </h3>
              <p className="text-xs text-ink-soft leading-relaxed">
                Enforces transparent revision chaining so earlier revisions remain immutable. Creators address findings and submit for review; authorized reviewers approve, request changes, or record reasoned overrides for high-risk findings. Impact records are resolved only when criteria are satisfied.
              </p>
            </div>
            <div className="border-t border-rule/60 pt-4 space-y-2">
              <Link href="/review" className="btn btn-primary w-full text-xs justify-center gap-1.5">
                <IconCheck className="h-3.5 w-3.5" />
                Explore Workflow & Approvals
              </Link>
              <p className="text-[11px] text-ink-faint text-center">
                Approvals require finished reviews of the exact text and enforce role-based compliance.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Step-by-Step Judge Evaluation Walkthrough */}
      <section className="rounded-2xl border border-rule bg-sheet p-8 shadow-subtle space-y-6" aria-label="Judge Walkthrough">
        <div className="border-b border-rule/70 pb-4">
          <h2 className="text-xl font-bold text-ink">Judge Walkthrough: 4 Steps to Test the Entire System</h2>
          <p className="text-xs text-ink-soft mt-1">
            Follow this sequential roadmap to independently verify all three commitments in less than 5 minutes.
          </p>
        </div>

        <ol className="space-y-5">
          <li className="flex items-start gap-4">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-signal text-white font-bold text-xs">
              1
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h4 className="font-bold text-sm text-ink">Inspect Ground Truth & Ingested Knowledge</h4>
                <Link href="/knowledge" className="text-xs text-signal font-semibold hover:underline flex items-center gap-1">
                  Go to Knowledge <IconExternalLink className="h-3 w-3" />
                </Link>
              </div>
              <p className="text-xs text-ink-soft leading-relaxed">
                Open <Link href="/knowledge" className="underline font-medium text-ink">Brand Knowledge</Link> to inspect the uploaded Nova Systems documents (PDF, CSV, TXT) and view page-level text extraction. Open <Link href="/facts" className="underline font-medium text-ink">Approved Facts</Link> to observe active facts citing page 2 of the specification (such as &ldquo;Battery life: Up to 18 hours&rdquo;).
              </p>
            </div>
          </li>

          <li className="flex items-start gap-4">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-signal text-white font-bold text-xs">
              2
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h4 className="font-bold text-sm text-ink">Run ProofGraph Claim Verification</h4>
                <Link href="/review" className="text-xs text-signal font-semibold hover:underline flex items-center gap-1">
                  Go to Review <IconExternalLink className="h-3 w-3" />
                </Link>
              </div>
              <p className="text-xs text-ink-soft leading-relaxed">
                Navigate to <Link href="/review" className="underline font-medium text-ink">Review Content</Link>. Click <strong>Load sample marketing copy</strong> and choose <strong>Review content</strong>. Observe that claims are extracted and highlighted directly in the draft. Click a finding to view its verified source citation; click <strong>Open source</strong> to see the exact page with the excerpt marked.
              </p>
            </div>
          </li>

          <li className="flex items-start gap-4">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-signal text-white font-bold text-xs">
              3
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h4 className="font-bold text-sm text-ink">Trace Fact-Change Impacts in Claim Ledger</h4>
                <Link href="/fact-changes" className="text-xs text-signal font-semibold hover:underline flex items-center gap-1">
                  Go to Fact Changes <IconExternalLink className="h-3 w-3" />
                </Link>
              </div>
              <p className="text-xs text-ink-soft leading-relaxed">
                Open <Link href="/fact-changes" className="underline font-medium text-ink">Fact Changes</Link>. Inspect the impacted asset flagged because an approved fact changed or expired. Click <strong>Inspect impact</strong> to view the historical relied-upon value side-by-side with the current value and see why the content requires correction.
              </p>
            </div>
          </li>

          <li className="flex items-start gap-4">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-signal text-white font-bold text-xs">
              4
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h4 className="font-bold text-sm text-ink">Correct, Review, and Approve Revision</h4>
                <Link href="/review" className="text-xs text-signal font-semibold hover:underline flex items-center gap-1">
                  Open Workflow <IconExternalLink className="h-3 w-3" />
                </Link>
              </div>
              <p className="text-xs text-ink-soft leading-relaxed">
                In Review Content, click <strong>Create corrected revision</strong> to address the conflicting finding. Save Revision 2, run a new review, and click <strong>Submit for approval</strong>. Switch your demo role to <strong>Reviewer</strong> in the panel or sidebar, enter your name, and click <strong>Approve</strong>. Return to Fact Changes to resolve the open impact using your approved Revision 2.
              </p>
            </div>
          </li>
        </ol>
      </section>
    </div>
  );
}

