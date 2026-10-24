"use client";
import { useState } from "react";
import Link from "next/link";
import { EmptyState, Loading, Notice } from "@/components/ui";
import { useBrand } from "@/components/providers";
import { api, errorMessage } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import type { GovernanceInsights } from "@/types/api";

export function InsightsView() {
  const { brand } = useBrand();
  const [period, setPeriod] = useState<"7d" | "30d" | "all">("all");

  const brandId = brand?.id ?? "";

  const insightsResource = useResource(
    () => api.getGovernanceInsights(brandId, period),
    [brandId, period]
  );

  if (insightsResource.loading && !insightsResource.data) {
    return <Loading label="Loading governance insights" />;
  }

  if (insightsResource.error || !insightsResource.data) {
    return (
      <div className="space-y-4">
        <h1 className="font-serif text-3xl font-semibold">Governance Intelligence</h1>
        <Notice
          kind="error"
          action={
            <button className="btn btn-secondary text-xs" onClick={insightsResource.reload}>
              Retry Query
            </button>
          }
        >
          Failed to load governance intelligence metrics: {errorMessage(insightsResource.error)}
        </Notice>
      </div>
    );
  }

  const data = insightsResource.data;
  const { overview, finding_patterns, repeated_issues, governance_recommendations, simulations_summary } = data;

  const hasAnyData =
    overview.completed_reviews > 0 ||
    overview.total_findings > 0 ||
    overview.open_impacts > 0 ||
    overview.rules_summary.total > 0;

  return (
    <div className="space-y-6">
      {/* Header and Period Filter */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-rule pb-4">
        <div>
          <h1 className="font-serif text-3xl font-semibold">Governance Intelligence</h1>
          <p className="text-sm text-ink-soft">
            Evidence-backed analytics and actionable patterns derived from actual brand review records and workflow history.
          </p>
        </div>
        <div className="flex items-center gap-1.5 bg-paper p-1 rounded border border-rule">
          <span className="text-xs font-semibold px-2 text-ink-soft">Period:</span>
          {(["7d", "30d", "all"] as const).map((p) => (
            <button
              key={p}
              type="button"
              className={`px-2.5 py-1 text-xs rounded transition-colors ${
                period === p
                  ? "bg-signal text-white font-semibold"
                  : "text-ink hover:bg-sheet"
              }`}
              onClick={() => setPeriod(p)}
            >
              {p === "7d" ? "Last 7 Days" : p === "30d" ? "Last 30 Days" : "All Time"}
            </button>
          ))}
        </div>
      </header>

      {!hasAnyData ? (
        <EmptyState
          title="No review or governance records found"
          action={
            <Link href="/review" className="btn btn-primary">
              Go to Content Review
            </Link>
          }
        >
          Submit content for review, create guideline rules, or approve facts to generate governance intelligence.
        </EmptyState>
      ) : (
        <div className="space-y-6">
          {/* Overview KPI Cards */}
          <section aria-label="Governance Overview" className="space-y-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-ink-soft">Review & Workflow Overview</h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <div className="border border-rule bg-sheet p-3 rounded">
                <span className="block font-serif text-3xl font-bold">{overview.completed_reviews}</span>
                <span className="text-xs font-semibold text-ink-soft">Completed Reviews</span>
              </div>
              <div className="border border-rule bg-sheet p-3 rounded">
                <span className="block font-serif text-3xl font-bold">{overview.total_findings}</span>
                <span className="text-xs font-semibold text-ink-soft">Total Findings Flagged</span>
              </div>
              <div className="border border-rule bg-sheet p-3 rounded">
                <span className={`block font-serif text-3xl font-bold ${overview.open_impacts > 0 ? "text-amber-700" : ""}`}>
                  {overview.open_impacts}
                </span>
                <span className="text-xs font-semibold text-ink-soft">Open Fact Impacts</span>
              </div>
              <div className="border border-rule bg-sheet p-3 rounded">
                <span className="block font-serif text-3xl font-bold text-emerald-700">{overview.decisions.approved}</span>
                <span className="text-xs font-semibold text-ink-soft">Approved Content</span>
              </div>
              <div className="border border-rule bg-sheet p-3 rounded">
                <span className="block font-serif text-3xl font-bold text-amber-700">{overview.decisions.changes_requested}</span>
                <span className="text-xs font-semibold text-ink-soft">Changes Requested</span>
              </div>
              <div className="border border-rule bg-sheet p-3 rounded">
                <span className="block font-serif text-3xl font-bold">{overview.rules_summary.active}</span>
                <span className="text-xs font-semibold text-ink-soft">Active Guidelines</span>
              </div>
            </div>
          </section>

          {/* Finding Distributions and Top Problematic Terms */}
          <div className="grid gap-6 md:grid-cols-2">
            {/* Finding Status & Severity Distribution */}
            <section className="border border-rule bg-sheet p-4 rounded space-y-4">
              <h3 className="font-serif text-lg font-semibold">Finding Breakdown</h3>
              <div className="space-y-3">
                <div>
                  <h4 className="text-xs font-bold text-ink-soft uppercase tracking-wide mb-1.5">By Verdict Status</h4>
                  <div className="space-y-1">
                    {Object.entries(finding_patterns.by_status).length === 0 ? (
                      <p className="text-xs text-ink-soft">No findings recorded.</p>
                    ) : (
                      Object.entries(finding_patterns.by_status).map(([st, cnt]) => (
                        <div key={st} className="flex justify-between items-center text-xs p-1.5 bg-paper rounded border border-rule">
                          <span className="font-medium capitalize">{st}</span>
                          <span className="font-mono font-semibold">{cnt}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div>
                  <h4 className="text-xs font-bold text-ink-soft uppercase tracking-wide mb-1.5">By Severity Level</h4>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div className="p-2 border border-rose-200 bg-rose-50/50 rounded text-center">
                      <span className="block font-bold text-rose-800 text-lg">{finding_patterns.by_severity.high ?? 0}</span>
                      <span className="text-rose-900 font-semibold text-[11px]">High Risk</span>
                    </div>
                    <div className="p-2 border border-amber-200 bg-amber-50/50 rounded text-center">
                      <span className="block font-bold text-amber-800 text-lg">{finding_patterns.by_severity.medium ?? 0}</span>
                      <span className="text-amber-900 font-semibold text-[11px]">Medium</span>
                    </div>
                    <div className="p-2 border border-blue-200 bg-blue-50/50 rounded text-center">
                      <span className="block font-bold text-blue-800 text-lg">{finding_patterns.by_severity.low ?? 0}</span>
                      <span className="text-blue-900 font-semibold text-[11px]">Low</span>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* Recurring Problematic Terms */}
            <section className="border border-rule bg-sheet p-4 rounded space-y-4">
              <h3 className="font-serif text-lg font-semibold">Frequently Flagged Terms & Claims</h3>
              <p className="text-xs text-ink-soft">
                Non-supported claims that frequently appear across reviewed submissions.
              </p>
              {finding_patterns.top_problematic_terms.length === 0 ? (
                <p className="text-xs text-ink-soft">No repeated problematic terms detected.</p>
              ) : (
                <ul className="space-y-2">
                  {finding_patterns.top_problematic_terms.map((item) => (
                    <li key={item.term} className="p-2.5 border border-rule bg-paper rounded text-xs space-y-1">
                      <div className="flex justify-between items-center">
                        <span className="font-mono font-bold text-ink px-1.5 py-0.5 bg-sheet rounded border border-rule">
                          &ldquo;{item.term}&rdquo;
                        </span>
                        <span className="text-amber-800 font-semibold">Flagged {item.count} time(s)</span>
                      </div>
                      {item.samples.length > 0 && (
                        <p className="text-[11px] text-ink-soft italic truncate">
                          Sample: &ldquo;{item.samples[0]}&rdquo;
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          {/* Actionable Governance Recommendations */}
          <section className="border border-rule bg-sheet p-5 rounded space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-serif text-xl font-semibold">Actionable Governance Recommendations</h3>
                <p className="text-xs text-ink-soft">
                  Evidence-backed opportunities to clarify brand guidelines, resolve recurring content bottlenecks, and mitigate compliance risks.
                </p>
              </div>
              <span className="text-xs text-ink-soft italic">Requires human assessment</span>
            </div>

            {governance_recommendations.length === 0 ? (
              <p className="text-xs text-emerald-700">No pressing governance recommendations at this time.</p>
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {governance_recommendations.map((rec, idx) => (
                  <div key={idx} className="p-3.5 border border-rule rounded bg-paper space-y-2 text-xs flex flex-col justify-between">
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2">
                        <span className="px-1.5 py-0.5 rounded font-mono text-[10px] uppercase font-bold bg-gray-200 text-gray-800">
                          {rec.category.replace("_", " ")}
                        </span>
                        <span className="font-semibold text-ink text-sm">{rec.pattern}</span>
                      </div>
                      <p className="text-ink">
                        <strong className="text-ink-soft">Recommended Action: </strong>
                        {rec.suggested_action}
                      </p>
                    </div>

                    {rec.representative_findings.length > 0 && (
                      <div className="pt-2 border-t border-rule text-[11px] text-ink-soft">
                        <span className="font-semibold">Evidence: </span>
                        &ldquo;{rec.representative_findings[0]}&rdquo;
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Policy Simulations Analytics */}
          <section className="border border-rule bg-sheet p-4 rounded space-y-2">
            <h3 className="font-serif text-lg font-semibold">Policy Sandbox Activity</h3>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="p-3 bg-paper border border-rule rounded text-center">
                <span className="block font-serif text-2xl font-bold">{simulations_summary.total_simulations}</span>
                <span className="text-ink-soft font-semibold">Total Simulations Executed</span>
              </div>
              <div className="p-3 bg-paper border border-rule rounded text-center">
                <span className="block font-serif text-2xl font-bold">{simulations_summary.total_evaluated_content}</span>
                <span className="text-ink-soft font-semibold">Content Pieces Evaluated</span>
              </div>
              <div className="p-3 bg-paper border border-rule rounded text-center">
                <span className="block font-serif text-2xl font-bold text-amber-700">{simulations_summary.total_changed_outcomes}</span>
                <span className="text-amber-800 font-semibold">Projected Outcome Changes</span>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
