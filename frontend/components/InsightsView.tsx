"use client";
import { useState } from "react";
import Link from "next/link";
import { EmptyState, Loading, Notice } from "@/components/ui";
import { useBrand } from "@/components/providers";
import { api, errorMessage } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { IconInsights, IconCheck, IconAlert, IconCampaigns, IconSandbox, IconFacts } from "@/components/Icons";
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
        <h1 className="font-serif text-3xl font-bold tracking-tight text-ink">Governance Intelligence</h1>
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
    <div className="space-y-8">
      {/* Header and Period Filter */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-rule/70 pb-5">
        <div>
          <h1 className="font-serif text-3xl font-bold tracking-tight text-ink">Governance Intelligence</h1>
          <p className="mt-1 text-sm text-ink-soft">
            Evidence-backed analytics and actionable patterns derived from actual brand review records and workflow history.
          </p>
        </div>
        <div className="flex items-center gap-1 bg-sheet p-1 rounded-lg border border-rule shadow-subtle">
          <span className="text-xs font-semibold px-2 text-ink-soft">Period:</span>
          {(["7d", "30d", "all"] as const).map((p) => (
            <button
              key={p}
              type="button"
              className={`px-3 py-1 text-xs rounded-md font-semibold transition-all duration-150 ${
                period === p
                  ? "bg-signal text-white shadow-subtle"
                  : "text-ink-soft hover:text-ink hover:bg-paper"
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
        <div className="space-y-8">
          {/* Overview KPI Cards */}
          <section aria-label="Governance Overview" className="space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-ink-soft">Review & Workflow Overview</h2>
            <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-3 lg:grid-cols-6">
              <div className="rounded-xl border border-rule bg-sheet p-4 shadow-subtle hover:border-rule-strong transition-all">
                <span className="block font-serif text-3xl font-bold text-ink">{overview.completed_reviews}</span>
                <span className="mt-1 block text-xs font-semibold text-ink-soft">Completed Reviews</span>
              </div>
              <div className="rounded-xl border border-rule bg-sheet p-4 shadow-subtle hover:border-rule-strong transition-all">
                <span className="block font-serif text-3xl font-bold text-ink">{overview.total_findings}</span>
                <span className="mt-1 block text-xs font-semibold text-ink-soft">Total Findings Flagged</span>
              </div>
              <div className={`rounded-xl border p-4 shadow-subtle transition-all ${
                overview.open_impacts > 0 ? "border-state-unapproved-border bg-state-unapproved-wash/50" : "border-rule bg-sheet"
              }`}>
                <span className={`block font-serif text-3xl font-bold ${overview.open_impacts > 0 ? "text-terracotta" : "text-ink"}`}>
                  {overview.open_impacts}
                </span>
                <span className="mt-1 block text-xs font-semibold text-ink-soft">Open Fact Impacts</span>
              </div>
              <div className="rounded-xl border border-rule bg-sheet p-4 shadow-subtle hover:border-rule-strong transition-all">
                <span className="block font-serif text-3xl font-bold text-state-current">{overview.decisions.approved}</span>
                <span className="mt-1 block text-xs font-semibold text-ink-soft">Approved Content</span>
              </div>
              <div className="rounded-xl border border-rule bg-sheet p-4 shadow-subtle hover:border-rule-strong transition-all">
                <span className="block font-serif text-3xl font-bold text-terracotta">{overview.decisions.changes_requested}</span>
                <span className="mt-1 block text-xs font-semibold text-ink-soft">Changes Requested</span>
              </div>
              <div className="rounded-xl border border-rule bg-sheet p-4 shadow-subtle hover:border-rule-strong transition-all">
                <span className="block font-serif text-3xl font-bold text-signal">{overview.rules_summary.active}</span>
                <span className="mt-1 block text-xs font-semibold text-ink-soft">Active Guidelines</span>
              </div>
            </div>
          </section>

          {/* Finding Distributions and Top Problematic Terms */}
          <div className="grid gap-6 md:grid-cols-2">
            {/* Finding Status & Severity Distribution */}
            <section className="rounded-xl border border-rule bg-sheet p-5 shadow-subtle space-y-4">
              <h3 className="font-serif text-lg font-bold text-ink">Finding Breakdown</h3>
              <div className="space-y-4">
                <div>
                  <h4 className="text-xs font-bold text-ink-soft uppercase tracking-wider mb-2">By Verdict Status</h4>
                  <div className="space-y-1.5">
                    {Object.entries(finding_patterns.by_status).length === 0 ? (
                      <p className="text-xs text-ink-faint">No findings recorded.</p>
                    ) : (
                      Object.entries(finding_patterns.by_status).map(([st, cnt]) => (
                        <div key={st} className="flex justify-between items-center text-xs p-2.5 bg-paper/60 rounded-lg border border-rule/70">
                          <span className="font-semibold text-ink capitalize">{st}</span>
                          <span className="font-mono font-bold text-ink bg-sheet px-2 py-0.5 rounded border border-rule">{cnt}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="pt-2 border-t border-rule/60">
                  <h4 className="text-xs font-bold text-ink-soft uppercase tracking-wider mb-2">By Severity Level</h4>
                  <div className="grid grid-cols-3 gap-2.5 text-xs">
                    <div className="p-3 border border-state-expired-border bg-state-expired-wash/70 rounded-lg text-center">
                      <span className="block font-serif font-bold text-state-expired text-xl">{finding_patterns.by_severity.high ?? 0}</span>
                      <span className="text-state-expired font-bold text-[11px] uppercase tracking-wider">High Risk</span>
                    </div>
                    <div className="p-3 border border-state-unapproved-border bg-state-unapproved-wash/70 rounded-lg text-center">
                      <span className="block font-serif font-bold text-terracotta text-xl">{finding_patterns.by_severity.medium ?? 0}</span>
                      <span className="text-terracotta font-bold text-[11px] uppercase tracking-wider">Medium</span>
                    </div>
                    <div className="p-3 border border-state-pending-border bg-state-pending-wash/70 rounded-lg text-center">
                      <span className="block font-serif font-bold text-state-pending text-xl">{finding_patterns.by_severity.low ?? 0}</span>
                      <span className="text-state-pending font-bold text-[11px] uppercase tracking-wider">Low</span>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* Recurring Problematic Terms */}
            <section className="rounded-xl border border-rule bg-sheet p-5 shadow-subtle space-y-4">
              <h3 className="font-serif text-lg font-bold text-ink">Frequently Flagged Terms & Claims</h3>
              <p className="text-xs text-ink-soft">
                Non-supported claims that frequently appear across reviewed submissions.
              </p>
              {finding_patterns.top_problematic_terms.length === 0 ? (
                <div className="rounded-lg border border-dashed border-rule p-8 text-center text-xs text-ink-faint">
                  No repeated problematic terms detected.
                </div>
              ) : (
                <ul className="space-y-2.5">
                  {finding_patterns.top_problematic_terms.map((item) => (
                    <li key={item.term} className="p-3 border border-rule bg-paper/60 rounded-lg text-xs space-y-1.5">
                      <div className="flex justify-between items-center">
                        <span className="font-mono font-bold text-ink px-2 py-0.5 bg-sheet rounded border border-rule shadow-subtle">
                          &ldquo;{item.term}&rdquo;
                        </span>
                        <span className="text-terracotta font-bold">Flagged {item.count} time(s)</span>
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
          <section className="rounded-xl border border-rule bg-sheet p-6 shadow-subtle space-y-4">
            <div className="flex items-center justify-between border-b border-rule/60 pb-3">
              <div>
                <h3 className="font-serif text-xl font-bold text-ink">Actionable Governance Recommendations</h3>
                <p className="text-xs text-ink-soft mt-0.5">
                  Evidence-backed opportunities to clarify brand guidelines, resolve recurring content bottlenecks, and mitigate compliance risks.
                </p>
              </div>
              <span className="text-xs font-semibold text-terracotta bg-state-unapproved-wash px-2 py-0.5 rounded border border-state-unapproved-border">
                Human assessment required
              </span>
            </div>

            {governance_recommendations.length === 0 ? (
              <p className="text-xs text-state-current font-medium">No pressing governance recommendations at this time.</p>
            ) : (
              <div className="grid gap-3.5 md:grid-cols-2">
                {governance_recommendations.map((rec, idx) => (
                  <div key={idx} className="p-4 border border-rule rounded-xl bg-paper/50 space-y-2.5 text-xs flex flex-col justify-between shadow-subtle hover:bg-paper transition-all">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded-full font-mono text-[10px] uppercase font-bold bg-ink/10 text-ink">
                          {rec.category.replace("_", " ")}
                        </span>
                        <span className="font-bold text-ink text-sm">{rec.pattern}</span>
                      </div>
                      <p className="text-ink text-xs leading-relaxed">
                        <strong className="text-ink-soft">Recommended Action: </strong>
                        {rec.suggested_action}
                      </p>
                    </div>

                    {rec.representative_findings.length > 0 && (
                      <div className="pt-2.5 border-t border-rule text-[11px] text-ink-soft">
                        <span className="font-semibold text-ink">Evidence: </span>
                        &ldquo;{rec.representative_findings[0]}&rdquo;
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Policy Simulations Analytics */}
          <section className="rounded-xl border border-rule bg-sheet p-5 shadow-subtle space-y-3">
            <h3 className="font-serif text-lg font-bold text-ink">Policy Sandbox Activity</h3>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="p-3.5 bg-paper/60 border border-rule rounded-xl text-center">
                <span className="block font-serif text-2xl font-bold text-ink">{simulations_summary.total_simulations}</span>
                <span className="mt-0.5 block text-ink-soft font-semibold">Total Simulations Executed</span>
              </div>
              <div className="p-3.5 bg-paper/60 border border-rule rounded-xl text-center">
                <span className="block font-serif text-2xl font-bold text-ink">{simulations_summary.total_evaluated_content}</span>
                <span className="mt-0.5 block text-ink-soft font-semibold">Content Pieces Evaluated</span>
              </div>
              <div className="p-3.5 bg-paper/60 border border-rule rounded-xl text-center">
                <span className="block font-serif text-2xl font-bold text-terracotta">{simulations_summary.total_changed_outcomes}</span>
                <span className="mt-0.5 block text-terracotta font-semibold">Projected Outcome Changes</span>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
