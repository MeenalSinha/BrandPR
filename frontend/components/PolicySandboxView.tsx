"use client";
import { useState } from "react";
import { Dialog, EmptyState, Loading, Notice, Field } from "@/components/ui";
import { useBrand, useToast } from "@/components/providers";
import { api, errorMessage } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import type { GuidelineRule, PolicySimulation, PolicySimulationDetail } from "@/types/api";

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
      <header className="border-b border-rule pb-4">
        <h1 className="font-serif text-3xl font-semibold">Policy Sandbox</h1>
        <p className="text-sm text-ink-soft">
          Test proposed guideline modifications against historical content submissions to preview impact before activating changes.
        </p>
      </header>

      {/* Safety Notice */}
      <div className="p-3 bg-paper rounded border border-rule-strong text-xs text-ink space-y-1">
        <p className="font-semibold text-ink-soft flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-blue-500" />
          Historical Integrity Guarantee
        </p>
        <p className="text-ink-soft">
          Simulations are isolated predictions under the proposed rule. Running a simulation leaves all historical review findings, evidence snapshots, content revisions, approval decisions, and fact-change impacts completely unchanged.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Main Simulation Workspace */}
        <div className="space-y-6">
          <form onSubmit={handleRunSimulation} className="border border-rule bg-sheet p-5 rounded space-y-4">
            <h2 className="font-serif text-xl font-semibold">Configure Policy Simulation</h2>

            <Field label="1. Select Active or Proposed Rule" htmlFor="sim-rule">
              <select
                id="sim-rule"
                className="input w-full text-sm"
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
                <div className="p-3 bg-paper rounded border border-rule text-xs space-y-1">
                  <span className="font-bold text-ink-soft">Current Rule Text (v{selectedRule.current_version})</span>
                  <p className="text-ink font-medium">{selectedRule.rule_text}</p>
                  <p className="text-ink-soft text-[11px]">Category: {selectedRule.category} | Scope: {selectedRule.scope || "all"}</p>
                </div>
                <div className="p-3 bg-paper rounded border border-rule text-xs space-y-1">
                  <span className="font-bold text-ink-soft">Historical Content Scope</span>
                  <p className="text-ink">
                    {contentResource.data?.total ?? 0} historical submission revision(s) available for replay.
                  </p>
                </div>
              </div>
            )}

            <Field label="2. Proposed Rule Text / Condition" htmlFor="proposed-text">
              <textarea
                id="proposed-text"
                className="input w-full text-sm font-mono"
                rows={3}
                value={proposedText}
                onChange={(e) => setProposedText(e.target.value)}
                placeholder="Enter proposed revised wording (e.g., relaxing or adding specific conditions)..."
              />
            </Field>

            <button
              type="submit"
              className="btn btn-primary text-sm"
              disabled={simulating || !selectedRuleId || !proposedText.trim()}
            >
              {simulating ? "Simulating on Historical Content..." : "Run Policy Simulation"}
            </button>
          </form>

          {/* Active Simulation Results Display */}
          {activeSimulation && (
            <section className="border border-rule bg-sheet p-5 rounded space-y-4" aria-label="Simulation Results">
              <div className="flex items-center justify-between border-b border-rule pb-3">
                <div>
                  <h3 className="font-serif text-xl font-semibold">Simulation Report</h3>
                  <p className="text-xs text-ink-soft">
                    Evaluated Rule v{activeSimulation.base_rule_version} vs. Proposed Rule v{activeSimulation.proposed_rule_version}
                  </p>
                </div>
                <span className="text-xs font-mono bg-paper px-2 py-1 rounded border border-rule">
                  {new Date(activeSimulation.created_at).toLocaleTimeString()}
                </span>
              </div>

              {/* Metrics summary cards */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="p-3 border border-rule bg-paper rounded text-center">
                  <span className="block font-serif text-2xl font-bold">{activeSimulation.summary.total_evaluated}</span>
                  <span className="text-xs text-ink-soft font-semibold">Total Evaluated</span>
                </div>
                <div className="p-3 border border-rule bg-amber-50 rounded text-center">
                  <span className="block font-serif text-2xl font-bold text-amber-700">{activeSimulation.summary.changed}</span>
                  <span className="text-xs text-amber-800 font-semibold">Outcomes Changed</span>
                </div>
                <div className="p-3 border border-rule bg-emerald-50 rounded text-center">
                  <span className="block font-serif text-2xl font-bold text-emerald-700">{activeSimulation.summary.unchanged}</span>
                  <span className="text-xs text-emerald-800 font-semibold">Unchanged</span>
                </div>
                <div className="p-3 border border-rule bg-gray-50 rounded text-center">
                  <span className="block font-serif text-2xl font-bold text-gray-600">{activeSimulation.summary.not_evaluable}</span>
                  <span className="text-xs text-gray-600 font-semibold">Not Evaluable</span>
                </div>
              </div>

              {/* Detailed Result Rows */}
              <div className="space-y-3">
                <h4 className="font-bold text-xs uppercase tracking-wide text-ink-soft">Evaluated Content Revisions</h4>
                {activeSimulation.results.length === 0 ? (
                  <p className="text-xs text-ink-soft">No content submissions available to simulate.</p>
                ) : (
                  <div className="space-y-2">
                    {activeSimulation.results.map((res) => (
                      <div
                        key={res.id}
                        className={`p-3 border rounded text-xs space-y-2 ${
                          res.outcome_changed ? "border-amber-300 bg-amber-50/40" : "border-rule bg-paper"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-sm text-ink">{res.content_title}</span>
                          <div className="flex items-center gap-2">
                            {res.outcome_changed ? (
                              <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-200 text-amber-900 border border-amber-300">
                                OUTCOME CHANGED
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded text-[11px] bg-gray-200 text-gray-700">
                                UNCHANGED
                              </span>
                            )}
                            <span className="font-mono text-[10px] text-ink-soft">
                              Status: {res.evaluation_status}
                            </span>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div>
                            <span className="font-bold text-ink-soft">Baseline Outcome: </span>
                            <span className="font-mono">{res.baseline_outcome}</span>
                          </div>
                          <div>
                            <span className="font-bold text-ink-soft">Simulated Outcome: </span>
                            <span className="font-mono font-semibold">{res.simulated_outcome}</span>
                          </div>
                        </div>

                        {res.explanation && (
                          <p className="text-xs text-ink bg-sheet p-2 rounded border border-rule">
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
        <aside className="border border-rule bg-sheet p-4 rounded space-y-4 h-fit">
          <h3 className="font-serif text-lg font-semibold">Simulation History</h3>
          <p className="text-xs text-ink-soft">
            Past policy simulations for this brand. Click to inspect saved comparative outcomes.
          </p>

          {simulationsResource.loading && !simulationsResource.data ? (
            <p className="text-xs text-ink-soft">Loading history...</p>
          ) : simulationsResource.data?.items.length === 0 ? (
            <p className="text-xs text-ink-soft">No simulations recorded yet.</p>
          ) : (
            <ul className="space-y-2">
              {simulationsResource.data?.items.map((sim) => (
                <li
                  key={sim.id}
                  onClick={() => handleViewPastSimulation(sim.id)}
                  className={`p-2.5 border rounded cursor-pointer transition-colors text-xs space-y-1 ${
                    activeSimulation?.id === sim.id
                      ? "border-signal bg-signal-wash"
                      : "border-rule bg-paper hover:border-rule-strong"
                  }`}
                >
                  <div className="flex justify-between font-medium">
                    <span>Sim v{sim.base_rule_version} &rarr; v{sim.proposed_rule_version}</span>
                    <span className="text-[11px] text-ink-soft">
                      {new Date(sim.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="flex justify-between text-ink-soft text-[11px]">
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
