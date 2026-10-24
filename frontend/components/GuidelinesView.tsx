"use client";
import { useState } from "react";
import Link from "next/link";
import { Dialog, EmptyState, Loading, Notice, Field } from "@/components/ui";
import { useBrand, useToast } from "@/components/providers";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import type { GuidelineRule, GuidelineLintIssue, GuidelineRuleVersion } from "@/types/api";

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "bg-emerald-100 text-emerald-800 border-emerald-300",
    proposed: "bg-amber-100 text-amber-800 border-amber-300",
    retired: "bg-gray-100 text-gray-700 border-gray-300",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded border ${styles[status] || "bg-gray-100"}`}>
      {status.toUpperCase()}
    </span>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const styles: Record<string, string> = {
    high: "bg-rose-100 text-rose-800 border-rose-300",
    medium: "bg-amber-100 text-amber-800 border-amber-300",
    low: "bg-blue-100 text-blue-800 border-blue-300",
  };
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 text-xs rounded border ${styles[severity] || "bg-gray-100"}`}>
      {severity}
    </span>
  );
}

export function GuidelinesView() {
  const { brand, role } = useBrand();
  const toast = useToast();

  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [linting, setLinting] = useState(false);
  const [lintIssues, setLintIssues] = useState<GuidelineLintIssue[] | null>(null);
  const [activeRuleModal, setActiveRuleModal] = useState<GuidelineRule | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showExtractModal, setShowExtractModal] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState("");
  const [ruleVersions, setRuleVersions] = useState<GuidelineRuleVersion[] | null>(null);
  const [editingText, setEditingText] = useState("");
  const [editingReason, setEditingReason] = useState("");
  const [busyAction, setBusyAction] = useState(false);

  // Form states for manual creation
  const [newTitle, setNewTitle] = useState("");
  const [newText, setNewText] = useState("");
  const [newCategory, setNewCategory] = useState("general");
  const [newSeverity, setNewSeverity] = useState("medium");
  const [newScope, setNewScope] = useState("");
  const [newExcerpt, setNewExcerpt] = useState("");
  const [newOwner, setNewOwner] = useState("");

  const brandId = brand?.id ?? "";

  const rulesResource = useResource(
    () => api.listGuidelines(brandId, statusFilter === "all" ? undefined : statusFilter),
    [brandId, statusFilter]
  );

  const docsResource = useResource(
    () => api.listDocuments(brandId),
    [brandId]
  );

  async function handleRunLint() {
    if (!brandId) return;
    setLinting(true);
    try {
      const res = await api.runGuidelineLint(brandId);
      setLintIssues(res.issues);
      toast.push("success", `Lint check complete: ${res.total_issues} potential issue(s) identified.`);
    } catch (err) {
      toast.push("error", `Lint check failed: ${errorMessage(err)}`);
    } finally {
      setLinting(false);
    }
  }

  async function handleExtractRules() {
    if (!brandId || !selectedDocId) {
      toast.push("error", "Please select a source document.");
      return;
    }
    setBusyAction(true);
    try {
      const res = await api.extractGuidelines(brandId, { source_document_id: selectedDocId });
      toast.push("success", `Extracted ${res.extracted_count} proposed rule(s). Rules remain proposed until approved.`);
      setShowExtractModal(false);
      rulesResource.reload();
    } catch (err) {
      toast.push("error", `Extraction failed: ${errorMessage(err)}`);
    } finally {
      setBusyAction(false);
    }
  }

  async function handleCreateRule(e: React.FormEvent) {
    e.preventDefault();
    if (!newTitle.trim() || !newText.trim()) {
      toast.push("error", "Rule title and rule text are required.");
      return;
    }
    setBusyAction(true);
    try {
      await api.createGuideline(brandId, {
        title: newTitle.trim(),
        rule_text: newText.trim(),
        category: newCategory,
        severity: newSeverity,
        scope: newScope.trim() || null,
        source_excerpt: newExcerpt.trim() || null,
        owner: newOwner.trim() || null,
        status: "proposed",
      });
      toast.push("success", "Guideline rule created in proposed status.");
      setShowCreateModal(false);
      setNewTitle("");
      setNewText("");
      setNewScope("");
      setNewExcerpt("");
      rulesResource.reload();
    } catch (err) {
      toast.push("error", `Failed to create rule: ${errorMessage(err)}`);
    } finally {
      setBusyAction(false);
    }
  }

  async function openRuleDetails(rule: GuidelineRule) {
    setActiveRuleModal(rule);
    setEditingText(rule.rule_text);
    setEditingReason("");
    try {
      const v = await api.getGuidelineVersions(rule.id);
      setRuleVersions(v);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleUpdateStatus(newStatus: "active" | "retired") {
    if (!activeRuleModal) return;
    if (role !== "reviewer") {
      toast.push("error", "Only authorized reviewers can approve or retire rules.");
      return;
    }
    setBusyAction(true);
    try {
      const updated = await api.updateGuideline(activeRuleModal.id, {
        status: newStatus,
        change_reason: `Status changed to ${newStatus} by reviewer`,
      });
      toast.push("success", `Rule "${updated.title}" marked as ${newStatus}.`);
      setActiveRuleModal(updated);
      rulesResource.reload();
    } catch (err) {
      toast.push("error", `Failed to update status: ${errorMessage(err)}`);
    } finally {
      setBusyAction(false);
    }
  }

  async function handleProposeEdit() {
    if (!activeRuleModal || !editingText.trim()) return;
    if (!editingReason.trim()) {
      toast.push("error", "Please provide a reason for proposing a new version.");
      return;
    }
    setBusyAction(true);
    try {
      await api.proposeGuidelineVersion(activeRuleModal.id, {
        rule_text: editingText.trim(),
        change_reason: editingReason.trim(),
      });
      toast.push("success", "New rule version proposed. Awaiting authorized approval.");
      const v = await api.getGuidelineVersions(activeRuleModal.id);
      setRuleVersions(v);
      setEditingReason("");
      rulesResource.reload();
    } catch (err) {
      toast.push("error", `Failed to propose version: ${errorMessage(err)}`);
    } finally {
      setBusyAction(false);
    }
  }

  if (rulesResource.loading && !rulesResource.data) {
    return <Loading label="Loading brand guidelines" />;
  }

  const rules = rulesResource.data?.items ?? [];

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-rule pb-4">
        <div>
          <h1 className="font-serif text-3xl font-semibold">Guideline Lint & Rule Management</h1>
          <p className="text-sm text-ink-soft">
            Manage source-linked brand policies, detect potential ambiguities or conflicts, and review version history.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-secondary text-sm"
            onClick={handleRunLint}
            disabled={linting}
          >
            {linting ? "Linting rules..." : "Run Guideline Lint"}
          </button>
          <button
            type="button"
            className="btn btn-secondary text-sm"
            onClick={() => setShowExtractModal(true)}
          >
            Extract from Document
          </button>
          <button
            type="button"
            className="btn btn-primary text-sm"
            onClick={() => setShowCreateModal(true)}
          >
            + New Guideline Rule
          </button>
        </div>
      </header>

      {/* Lint Issues Box */}
      {lintIssues && (
        <section className="border border-rule-strong bg-paper p-4 rounded space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-base flex items-center gap-2">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-500" />
              Guideline Lint Results ({lintIssues.length} candidate issues identified)
            </h3>
            <button
              type="button"
              className="text-xs text-ink-soft hover:underline"
              onClick={() => setLintIssues(null)}
            >
              Dismiss
            </button>
          </div>
          <p className="text-xs text-ink-soft">
            Note: Issues flagged below require human assessment and do not automatically alter active guidelines.
          </p>
          {lintIssues.length === 0 ? (
            <p className="text-sm text-emerald-700">No rule ambiguities or cross-rule conflicts detected.</p>
          ) : (
            <ul className="space-y-2">
              {lintIssues.map((issue) => (
                <li key={issue.id} className="p-3 border border-rule bg-sheet rounded text-sm space-y-1">
                  <div className="flex items-center gap-2 font-medium">
                    <span className="font-mono text-xs px-1.5 py-0.5 bg-gray-200 rounded">{issue.issue_category}</span>
                    <span className="text-rose-700 font-semibold">{issue.explanation}</span>
                  </div>
                  {issue.conflicting_rule_id && (
                    <p className="text-xs text-ink-soft">
                      Potential conflict with Rule ID: <code className="text-xs bg-gray-100 px-1 py-0.5">{issue.conflicting_rule_id}</code>
                    </p>
                  )}
                  {issue.suggested_action && (
                    <p className="text-xs text-ink">
                      <span className="font-semibold">Suggested Action:</span> {issue.suggested_action}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* Status Filters */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-ink-soft uppercase tracking-wider">Status:</span>
        {(["all", "active", "proposed", "retired"] as const).map((st) => (
          <button
            key={st}
            type="button"
            className={`px-3 py-1 text-xs rounded border ${
              statusFilter === st
                ? "bg-signal text-white border-signal font-semibold"
                : "bg-sheet border-rule text-ink hover:bg-paper"
            }`}
            onClick={() => setStatusFilter(st)}
          >
            {st.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Rules List */}
      {rules.length === 0 ? (
        <EmptyState
          title="No guideline rules found"
          action={
            <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
              Create Guideline Rule
            </button>
          }
        >
          Create a guideline rule manually or extract rules from an approved brand document.
        </EmptyState>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {rules.map((rule) => (
            <div
              key={rule.id}
              className="border border-rule bg-sheet p-4 rounded space-y-3 flex flex-col justify-between hover:border-rule-strong transition-colors"
            >
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-serif text-lg font-semibold">{rule.title}</h3>
                  <StatusBadge status={rule.status} />
                </div>
                <p className="text-sm text-ink">{rule.rule_text}</p>
                <div className="flex flex-wrap items-center gap-2 text-xs text-ink-soft">
                  <span className="capitalize px-1.5 py-0.5 bg-paper rounded border border-rule">{rule.category}</span>
                  <SeverityBadge severity={rule.severity} />
                  <span>v{rule.current_version}</span>
                  {rule.scope && <span>Scope: {rule.scope}</span>}
                </div>
                {rule.source_excerpt && (
                  <blockquote className="border-l-2 border-rule-strong pl-2 text-xs italic text-ink-soft line-clamp-2">
                    &ldquo;{rule.source_excerpt}&rdquo;
                  </blockquote>
                )}
              </div>
              <div className="pt-2 border-t border-rule flex items-center justify-between">
                <span className="text-xs text-ink-soft">
                  {rule.owner ? `Owner: ${rule.owner}` : "No assigned owner"}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary text-xs"
                  onClick={() => openRuleDetails(rule)}
                >
                  View Details & History
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Rule Detail & Version History Dialog */}
      {activeRuleModal && (
        <Dialog
          title={`Guideline Rule: ${activeRuleModal.title}`}
          onClose={() => setActiveRuleModal(null)}
          footer={
            <div className="flex items-center justify-between w-full">
              <div className="flex gap-2">
                {activeRuleModal.status === "proposed" && (
                  <button
                    type="button"
                    className="btn btn-primary text-xs"
                    disabled={busyAction}
                    onClick={() => handleUpdateStatus("active")}
                  >
                    Approve Rule (Make Active)
                  </button>
                )}
                {activeRuleModal.status === "active" && (
                  <button
                    type="button"
                    className="btn btn-secondary text-xs text-rose-700"
                    disabled={busyAction}
                    onClick={() => handleUpdateStatus("retired")}
                  >
                    Retire Rule
                  </button>
                )}
              </div>
              <button
                type="button"
                className="btn btn-secondary text-xs"
                onClick={() => setActiveRuleModal(null)}
              >
                Close
              </button>
            </div>
          }
        >
          <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <StatusBadge status={activeRuleModal.status} />
                <span className="text-xs font-semibold">Version {activeRuleModal.current_version}</span>
              </div>
              <p className="font-semibold text-sm">{activeRuleModal.rule_text}</p>
            </div>

            {activeRuleModal.source_excerpt && (
              <div className="p-3 bg-paper rounded border border-rule text-xs space-y-1">
                <span className="font-bold text-ink-soft">Source Excerpt</span>
                <p className="italic text-ink">&ldquo;{activeRuleModal.source_excerpt}&rdquo;</p>
                {activeRuleModal.source_page && <p className="text-ink-soft">Page: {activeRuleModal.source_page}</p>}
              </div>
            )}

            {/* Propose a New Version Form */}
            <div className="border border-rule rounded p-3 space-y-3 bg-sheet">
              <h4 className="font-bold text-xs uppercase tracking-wide text-ink-soft">Propose Revised Rule Text</h4>
              <textarea
                className="input text-sm w-full"
                rows={3}
                value={editingText}
                onChange={(e) => setEditingText(e.target.value)}
                placeholder="Adjust wording or executable conditions..."
              />
              <input
                className="input text-xs w-full"
                value={editingReason}
                onChange={(e) => setEditingReason(e.target.value)}
                placeholder="Reason for proposal (required)..."
              />
              <button
                type="button"
                className="btn btn-secondary text-xs"
                disabled={busyAction}
                onClick={handleProposeEdit}
              >
                Propose New Version
              </button>
            </div>

            {/* Version History Table */}
            <div className="space-y-2">
              <h4 className="font-bold text-xs uppercase tracking-wide text-ink-soft">Version History</h4>
              {!ruleVersions ? (
                <p className="text-xs text-ink-soft">Loading versions...</p>
              ) : ruleVersions.length === 0 ? (
                <p className="text-xs text-ink-soft">No previous versions.</p>
              ) : (
                <div className="space-y-2">
                  {ruleVersions.map((v) => (
                    <div key={v.id} className="p-2 border border-rule rounded bg-paper text-xs space-y-1">
                      <div className="flex justify-between font-medium">
                        <span>Version {v.version_number}</span>
                        <span className="text-ink-soft">{new Date(v.created_at).toLocaleString()}</span>
                      </div>
                      <p className="text-ink">{v.rule_text}</p>
                      {v.change_reason && <p className="text-ink-soft italic">Reason: {v.change_reason}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </Dialog>
      )}

      {/* Create Rule Modal */}
      {showCreateModal && (
        <Dialog
          title="New Guideline Rule"
          onClose={() => setShowCreateModal(false)}
          footer={
            <>
              <button type="button" className="btn btn-secondary text-xs" onClick={() => setShowCreateModal(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary text-xs"
                disabled={busyAction}
                onClick={handleCreateRule}
              >
                Create Proposed Rule
              </button>
            </>
          }
        >
          <form className="space-y-3">
            <Field label="Rule Title" htmlFor="rule-title">
              <input
                id="rule-title"
                className="input w-full text-sm"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="e.g. Comparative Claims Limitation"
              />
            </Field>
            <Field label="Rule Statement / Text" htmlFor="rule-text">
              <textarea
                id="rule-text"
                className="input w-full text-sm"
                rows={3}
                value={newText}
                onChange={(e) => setNewText(e.target.value)}
                placeholder="e.g. Comparative claims must not be used unless backed by verified lab specs."
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Category" htmlFor="rule-cat">
                <select
                  id="rule-cat"
                  className="input w-full text-xs"
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                >
                  <option value="general">General</option>
                  <option value="terminology">Terminology</option>
                  <option value="claim">Claim</option>
                  <option value="tone">Tone</option>
                  <option value="compliance">Compliance</option>
                </select>
              </Field>
              <Field label="Severity" htmlFor="rule-sev">
                <select
                  id="rule-sev"
                  className="input w-full text-xs"
                  value={newSeverity}
                  onChange={(e) => setNewSeverity(e.target.value)}
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </Field>
            </div>
            <Field label="Scope" htmlFor="rule-scope">
              <input
                id="rule-scope"
                className="input w-full text-xs"
                value={newScope}
                onChange={(e) => setNewScope(e.target.value)}
                placeholder="e.g. all marketing campaigns, digital ads"
              />
            </Field>
            <Field label="Source Excerpt (Optional)" htmlFor="rule-excerpt">
              <textarea
                id="rule-excerpt"
                className="input w-full text-xs"
                rows={2}
                value={newExcerpt}
                onChange={(e) => setNewExcerpt(e.target.value)}
                placeholder="Direct quotation from source document..."
              />
            </Field>
            <Field label="Owner" htmlFor="rule-owner">
              <input
                id="rule-owner"
                className="input w-full text-xs"
                value={newOwner}
                onChange={(e) => setNewOwner(e.target.value)}
                placeholder="e.g. Legal & Brand Strategy Team"
              />
            </Field>
          </form>
        </Dialog>
      )}

      {/* Extract Rules Modal */}
      {showExtractModal && (
        <Dialog
          title="Extract Rules from Source Document"
          onClose={() => setShowExtractModal(false)}
          footer={
            <>
              <button type="button" className="btn btn-secondary text-xs" onClick={() => setShowExtractModal(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary text-xs"
                disabled={busyAction || !selectedDocId}
                onClick={handleExtractRules}
              >
                {busyAction ? "Extracting..." : "Extract Proposed Rules"}
              </button>
            </>
          }
        >
          <div className="space-y-4">
            <p className="text-xs text-ink-soft">
              Select an uploaded brand document. Extracted rules will remain in <strong>proposed</strong> status until explicitly approved by an authorized reviewer.
            </p>
            <Field label="Source Document" htmlFor="select-doc">
              <select
                id="select-doc"
                className="input w-full text-sm"
                value={selectedDocId}
                onChange={(e) => setSelectedDocId(e.target.value)}
              >
                <option value="">-- Choose a document --</option>
                {docsResource.data?.items.map((doc) => (
                  <option key={doc.id} value={doc.id}>
                    {doc.title || doc.filename} ({doc.source_type.toUpperCase()})
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </Dialog>
      )}
    </div>
  );
}
