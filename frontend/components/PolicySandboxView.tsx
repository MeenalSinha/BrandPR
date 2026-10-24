"use client";
import { useState } from "react";
import { Dialog, EmptyState, Loading, Notice, Field } from "@/components/ui";
import { useBrand, useToast } from "@/components/providers";
import { api, errorMessage } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import type { GuidelineRule, PolicySimulation, PolicySimulationDetail } from "@/types/api";
import { IconSandbox, IconAlert, IconCheck } from "@/components/Icons";

export function PolicySandboxView() {
  const { brand } = useBrand();
  const toast = useToast();

  const brandId = brand?.id ?? "";

  const [selectedRuleId, setSelectedRuleId] = useState<string>("");
  const [proposedText, setProposedText] = useState<string>("");
  const [simulating, setSimulating] = useState(false);
  const [activeSimulation, setActiveSimulation] = useState<PolicySimulationDetail | null>(null);

  const rulesResource = useResource(
    () => api.listGuidelines(brandId),
    [brandId]
  );

  const contentResource = useResource(
    () => api.listContent(brandId),
    [brandId]
  );

  const simulationsResource = useResource(
    () => api.listPolicySimulations(brandId),
    [brandId]
  );

  const rules = rulesResource.data?.items ?? [];
  const selectedRule = rules.find((r) => r.id === selectedRuleId);

  function handleSelectRule(ruleId: string) {
    setSelectedRuleId(ruleId);
    const r = rules.find((x) => x.id === ruleId);
    if (r) {
      setProposedText(r.rule_text);
    }
  }

  async function handleRunSimulation(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedRuleId || !proposedText.trim()) {
      toast.push("error", "Please select a rule and enter proposed rule text.");
      return;
    }
    setSimulating(true);
    try {
      const res = await api.createPolicySimulation(brandId, {
        rule_id: selectedRuleId,
        proposed_rule_text: proposedText.trim(),
      });
      setActiveSimulation(res);
      toast.push("success", `Simulation complete: ${res.summary.changed} outcome(s) changed out of ${res.summary.total_evaluated} evaluated.`);
      simulationsResource.reload();
    } catch (err) {
      toast.push("error", `Simulation failed: ${errorMessage(err)}`);
    } finally {
      setSimulating(false);
    }
  }

  async function handleViewPastSimulation(id: string) {
    try {
      const sim = await api.getPolicySimulation(id);
      setActiveSimulation(sim);
    } catch (err) {
      toast.push("error", `Failed to load simulation: ${errorMessage(err)}`);
    }
  }

  if (rulesResource.loading && !rulesResource.data) {
    return <Loading label="Loading policy sandbox" />;
  }

  return (
    <div className="space-y-6">
      <header className="border-b border-rule pb-5">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-signal mb-1">
          <IconSandbox className="w-3.5 h-3.5" />
          <span>Counterfactual Impact Replay</span>
        </div>
        <h1 className="font-serif text-3xl font-bold tracking-tight text-ink">Policy Sandbox</h1>
        <p className="text-sm text-ink-muted mt-1 max-w-3xl leading-relaxed">
          Test proposed guideline modifications against historical content submissions to preview impact before activating changes.
        </p>
      </header>

      {/* Safety Notice */}
      <div className="p-4 bg-paper rounded-xl border border-rule shadow-xs text-xs space-y-1">
        <p className="font-bold text-signal flex items-center gap-2 text-xs uppercase tracking-wider">
          <IconCheck className="w-4 h-4 text-signal flex-shrink-0" />
          Historical Integrity Guarantee
        </p>
        <p className="text-ink-muted leading-relaxed">
          Simulations are isolated predictions under the proposed rule. Running a simulation leaves all historical review findings, evidence snapshots, content revisions, approval decisions, and fact-change impacts completely unchanged.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Main Simulation Workspace */}
        <div className="space-y-6">
          <form onSubmit={handleRunSimulation} className="border border-rule bg-sheet p-6 rounded-xl shadow-subtle space-y-4">
            <h2 className="font-serif text-lg font-bold text-ink">Configure Policy Simulation</h2>

            <Field label="1. Select Active or Proposed Rule" htmlFor="sim-rule">
              <select
                id="sim-rule"
                className="input w-full text-xs"
                value={selectedRuleId}
                onChange={(e) => handleSelectRule(e.target.value)}
              >
                <option value="">-- Choose a guideline rule --</option>
                {rules.map((r) => (
                  <option key={r.id} value={r.id}>
                    [{r.status.toUpperCase()}] {r.title} (v{r.current_version})
                  </option>
                ))}
              </select>
            </Field>

            {selectedRule && (
              <div className="grid md:grid-cols-2 gap-4">
                <div className="p-3.5 bg-paper rounded-xl border border-rule text-xs space-y-1">
                  <span className="font-bold text-ink-muted uppercase tracking-wider text-[10px]">Current Rule (v{selectedRule.current_version})</span>
                  <p className="text-ink font-medium leading-relaxed">{selectedRule.rule_text}</p>
                  <p className="text-ink-faint text-[11px] pt-1">Category: {selectedRule.category} &bull; Scope: {selectedRule.scope || "all"}</p>
                </div>
                <div className="p-3.5 bg-paper rounded-xl border border-rule text-xs space-y-1">
                  <span className="font-bold text-ink-muted uppercase tracking-wider text-[10px]">Replay Content Scope</span>
                  <p className="text-ink font-medium">
                    {contentResource.data?.total ?? 0} historical submission revision(s) available for simulation replay.
                  </p>
                  <p className="text-ink-faint text-[11px] pt-1">Will evaluate rules against historical claim sentences.</p>
                </div>
              </div>
            )}

            <Field label="2. Proposed Rule Text / Condition" htmlFor="proposed-text">
              <textarea
                id="proposed-text"
                className="input w-full text-xs font-mono leading-relaxed"
                rows={3}
                value={proposedText}
                onChange={(e) => setProposedText(e.target.value)}
                placeholder="Enter proposed revised wording (e.g., relaxing or adding specific conditions)..."
              />
            </Field>

            <button
              type="submit"
              className="btn btn-primary text-xs shadow-subtle"
              disabled={simulating || !selectedRuleId || !proposedText.trim()}
            >
              {simulating ? "Simulating on Historical Content..." : "⚡ Run Policy Simulation"}
            </button>
          </form>

          {/* Active Simulation Results Display */}
          {activeSimulation && (
            <section className="border border-rule bg-sheet p-6 rounded-xl shadow-subtle space-y-5 animate-in fade-in duration-150" aria-label="Simulation Results">
              <div className="flex items-center justify-between border-b border-rule pb-3">
                <div>
                  <h3 className="font-serif text-xl font-bold text-ink">Simulation Report</h3>
                  <p className="text-xs text-ink-muted mt-0.5">
                    Evaluated Rule v{activeSimulation.base_rule_version} vs. Proposed Rule v{activeSimulation.proposed_rule_version}
                  </p>
                </div>
                <span className="text-xs font-mono bg-paper px-2.5 py-1 rounded-md border border-rule text-ink-muted">
                  {new Date(activeSimulation.created_at).toLocaleTimeString()}
                </span>
              </div>

              {/* Metrics summary cards */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="p-3.5 border border-rule bg-paper rounded-xl text-center">
                  <span className="block font-serif text-2xl font-bold text-ink">{activeSimulation.summary.total_evaluated}</span>
                  <span className="text-xs text-ink-muted font-semibold">Total Evaluated</span>
                </div>
                <div className={`p-3.5 border rounded-xl text-center ${activeSimulation.summary.changed > 0 ? "border-amber-200 bg-amber-50" : "border-rule bg-paper"}`}>
                  <span className={`block font-serif text-2xl font-bold ${activeSimulation.summary.changed > 0 ? "text-amber-800" : "text-ink"}`}>
                    {activeSimulation.summary.changed}
                  </span>
                  <span className="text-xs font-semibold text-amber-900">Outcomes Changed</span>
                </div>
                <div className="p-3.5 border border-rule bg-signal-wash rounded-xl text-center">
                  <span className="block font-serif text-2xl font-bold text-signal-dark">{activeSimulation.summary.unchanged}</span>
                  <span className="text-xs text-signal-dark font-semibold">Unchanged</span>
                </div>
                <div className="p-3.5 border border-rule bg-surface-100 rounded-xl text-center">
                  <span className="block font-serif text-2xl font-bold text-ink-muted">{activeSimulation.summary.not_evaluable}</span>
                  <span className="text-xs text-ink-muted font-semibold">Not Evaluable</span>
                </div>
              </div>

              {/* Detailed Result Rows */}
              <div className="space-y-3">
                <h4 className="font-serif font-bold text-xs uppercase tracking-wider text-ink">Evaluated Content Revisions</h4>
                {activeSimulation.results.length === 0 ? (
                  <p className="text-xs text-ink-muted">No content submissions available to simulate.</p>
                ) : (
                  <div className="space-y-2.5">
                    {activeSimulation.results.map((res) => (
                      <div
                        key={res.id}
                        className={`p-4 border rounded-xl text-xs space-y-2.5 transition ${
                          res.outcome_changed ? "border-amber-300 bg-amber-50/50" : "border-rule bg-sheet"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-serif font-bold text-sm text-ink">{res.content_title}</span>
                          <div className="flex items-center gap-2">
                            {res.outcome_changed ? (
                              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-amber-200 text-amber-900 border border-amber-300">
                                OUTCOME CHANGED
                              </span>
                            ) : (
                              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-surface-100 text-ink-muted border border-rule">
                                UNCHANGED
                              </span>
                            )}
                            <span className="font-mono text-[10px] text-ink-muted">
                              Status: {res.evaluation_status}
                            </span>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-3 text-xs">
                          <div className="p-2.5 rounded-lg bg-paper border border-rule">
                            <span className="font-bold text-ink-muted text-[10px] uppercase tracking-wider block mb-1">Baseline Outcome:</span>
                            <span className="font-mono font-semibold text-ink">{res.baseline_outcome}</span>
                          </div>
                          <div className={`p-2.5 rounded-lg border ${res.outcome_changed ? "bg-amber-100/60 border-amber-300" : "bg-paper border-rule"}`}>
                            <span className="font-bold text-ink-muted text-[10px] uppercase tracking-wider block mb-1">Simulated Outcome:</span>
                            <span className={`font-mono font-semibold ${res.outcome_changed ? "text-amber-900" : "text-ink"}`}>
                              {res.simulated_outcome}
                            </span>
                          </div>
                        </div>

                        {res.explanation && (
                          <p className="text-xs text-ink bg-paper p-3 rounded-lg border border-rule leading-relaxed">
                            {res.explanation}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}
        </div>

        {/* Sidebar: Past Simulations History */}
        <aside className="border border-rule bg-sheet p-5 rounded-xl shadow-subtle space-y-4 h-fit">
          <div>
            <h3 className="font-serif text-lg font-bold text-ink">Simulation History</h3>
            <p className="text-xs text-ink-muted mt-1 leading-relaxed">
              Past policy simulations for this brand. Click to inspect saved comparative outcomes.
            </p>
          </div>

          {simulationsResource.loading && !simulationsResource.data ? (
            <p className="text-xs text-ink-muted">Loading history...</p>
          ) : simulationsResource.data?.items.length === 0 ? (
            <p className="text-xs text-ink-muted italic">No simulations recorded yet.</p>
          ) : (
            <ul className="space-y-2">
              {simulationsResource.data?.items.map((sim) => (
                <li
                  key={sim.id}
                  onClick={() => handleViewPastSimulation(sim.id)}
                  className={`p-3 border rounded-xl cursor-pointer transition-all text-xs space-y-1.5 ${
                    activeSimulation?.id === sim.id
                      ? "border-signal bg-signal-wash shadow-xs"
                      : "border-rule bg-paper hover:border-rule-strong"
                  }`}
                >
                  <div className="flex justify-between font-semibold text-ink">
                    <span>Sim v{sim.base_rule_version} &rarr; v{sim.proposed_rule_version}</span>
                    <span className="text-[11px] font-normal text-ink-muted">
                      {new Date(sim.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="flex justify-between text-ink-muted text-[11px]">
                    <span>Evaluated: {sim.summary?.total_evaluated ?? 0}</span>
                    <span className="text-amber-700 font-semibold">
                      Changed: {sim.summary?.changed ?? 0}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  );
}
