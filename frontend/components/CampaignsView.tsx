"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useBrand, useToast } from "@/components/providers";
import { api, errorMessage } from "@/lib/api";
import type { Campaign, CampaignStatus } from "@/types/api";
import { EmptyState } from "@/components/ui";
import { IconCampaigns, IconPlus, IconAlert, IconCheck } from "@/components/Icons";

const STATUS_CONFIG: Record<CampaignStatus, { label: string; bg: string; text: string; dot: string; border: string }> = {
  draft: { label: "Draft", bg: "bg-surface-100", text: "text-ink-muted", dot: "bg-ink-muted", border: "border-rule" },
  in_review: { label: "In Review", bg: "bg-amber-50", text: "text-amber-800", dot: "bg-amber-500", border: "border-amber-200" },
  blocked: { label: "Blocked", bg: "bg-terracotta-soft", text: "text-terracotta", dot: "bg-terracotta", border: "border-terracotta/30" },
  needs_review: { label: "Needs Review", bg: "bg-amber-50", text: "text-amber-800", dot: "bg-amber-500", border: "border-amber-200" },
  ready_for_release: { label: "Ready for Release", bg: "bg-signal-wash", text: "text-signal-dark", dot: "bg-signal", border: "border-signal/30" },
  released: { label: "Released", bg: "bg-blue-50", text: "text-blue-800", dot: "bg-blue-600", border: "border-blue-200" },
  archived: { label: "Archived", bg: "bg-surface-100", text: "text-ink-muted", dot: "bg-slate-400", border: "border-rule" },
};

export function CampaignsView() {
  const { brand } = useBrand();
  const toast = useToast();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [showCreateModal, setShowCreateModal] = useState(false);

  // New campaign form state
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newRef, setNewRef] = useState("");
  const [newOwner, setNewOwner] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!brand) return;
    loadCampaigns();
  }, [brand, statusFilter]);

  async function loadCampaigns() {
    if (!brand) return;
    setLoading(true);
    try {
      const data = await api.listCampaigns(
        brand.id,
        statusFilter === "all" ? undefined : statusFilter
      );
      setCampaigns(data);
    } catch (e) {
      toast.push("error", errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateCampaign(e: React.FormEvent) {
    e.preventDefault();
    if (!brand || !newTitle.trim()) return;
    setSubmitting(true);
    try {
      const created = await api.createCampaign(brand.id, {
        title: newTitle.trim(),
        description: newDesc.trim() || undefined,
        external_reference: newRef.trim() || undefined,
        owner: newOwner.trim() || undefined,
      });
      toast.push("success", `Campaign "${created.title}" created successfully.`);
      setShowCreateModal(false);
      setNewTitle("");
      setNewDesc("");
      setNewRef("");
      setNewOwner("");
      await loadCampaigns();
    } catch (err) {
      toast.push("error", errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-rule pb-5">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-signal mb-1">
            <IconCampaigns className="w-3.5 h-3.5" />
            <span>Campaign Intelligence & Release Gate</span>
          </div>
          <h1 className="text-2xl font-serif font-bold tracking-tight text-ink">
            Campaigns & Portfolios
          </h1>
          <p className="text-sm text-ink-muted mt-1 max-w-2xl">
            Audit multi-channel content for consistency, detect cross-asset claim conflicts, and enforce release readiness with evidence-backed verification.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn btn-primary shadow-subtle flex items-center gap-1.5"
          >
            <IconPlus className="w-3.5 h-3.5" />
            <span>+ New Campaign</span>
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2 border-b border-rule/60">
        <span className="text-xs uppercase tracking-wider font-semibold text-ink-muted mr-1">Status:</span>
        {["all", "draft", "in_review", "blocked", "needs_review", "ready_for_release", "released"].map((st) => (
          <button
            key={st}
            onClick={() => setStatusFilter(st)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
              statusFilter === st
                ? "bg-signal text-white border-signal shadow-xs"
                : "bg-sheet text-ink-muted border-rule hover:border-rule-strong hover:text-ink"
            }`}
          >
            {st.replace(/_/g, " ").toUpperCase()}
          </button>
        ))}
      </div>

      {/* Campaign List */}
      {loading ? (
        <div className="p-12 text-center text-sm text-ink-muted rounded-xl border border-rule bg-sheet">Loading campaigns...</div>
      ) : campaigns.length === 0 ? (
        <EmptyState title="No campaigns found">
          {statusFilter === "all"
            ? "Create your first campaign to audit assets together and gate releases."
            : `No campaigns match status "${statusFilter.replace(/_/g, " ")}".`}
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {campaigns.map((camp) => {
            const conf = STATUS_CONFIG[camp.status] || STATUS_CONFIG.draft;
            return (
              <Link
                key={camp.id}
                href={`/campaigns/${camp.id}`}
                className="group block p-5 rounded-xl border border-rule bg-sheet hover:border-signal/50 hover:shadow-subtle transition-all space-y-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-serif font-bold text-base text-ink group-hover:text-signal transition line-clamp-1">
                    {camp.title}
                  </h3>
                  <span
                    className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${conf.bg} ${conf.text} ${conf.border}`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${conf.dot}`} />
                    {conf.label}
                  </span>
                </div>

                {camp.description ? (
                  <p className="text-xs text-ink-muted line-clamp-2 leading-relaxed">{camp.description}</p>
                ) : (
                  <p className="text-xs text-ink-faint italic">No description provided</p>
                )}

                <div className="pt-3 border-t border-rule/60 grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="bg-paper p-2 rounded-lg border border-rule/50">
                    <span className="block font-serif font-bold text-base text-ink">{camp.asset_count}</span>
                    <span className="text-[11px] text-ink-muted font-medium">Assets</span>
                  </div>
                  <div className={`p-2 rounded-lg border ${camp.blocker_count > 0 ? "bg-terracotta-soft border-terracotta/20 text-terracotta" : "bg-paper border-rule/50 text-ink"}`}>
                    <span className="block font-serif font-bold text-base">{camp.blocker_count}</span>
                    <span className="text-[11px] text-ink-muted font-medium">Blockers</span>
                  </div>
                  <div className={`p-2 rounded-lg border ${camp.warning_count > 0 ? "bg-amber-50/70 border-amber-200/50 text-amber-800" : "bg-paper border-rule/50 text-ink"}`}>
                    <span className="block font-serif font-bold text-base">{camp.warning_count}</span>
                    <span className="text-[11px] text-ink-muted font-medium">Warnings</span>
                  </div>
                </div>

                {camp.latest_audit_stale && (
                  <div className="flex items-center gap-2 text-[11px] font-medium text-amber-900 bg-amber-50 px-2.5 py-1.5 rounded-lg border border-amber-200">
                    <IconAlert className="w-3.5 h-3.5 text-amber-600 flex-shrink-0" />
                    <span>Audit is stale. Asset revisions updated since last check.</span>
                  </div>
                )}
              </Link>
            );
          })}
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-md bg-sheet border border-rule rounded-xl shadow-overlay p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div>
              <h2 className="text-lg font-serif font-bold text-ink">Create New Campaign</h2>
              <p className="text-xs text-ink-muted mt-0.5">Define a portfolio of marketing assets to govern jointly before publication.</p>
            </div>
            <form onSubmit={handleCreateCampaign} className="space-y-4">
              <div>
                <label htmlFor="campaign-title" className="block text-xs font-semibold text-ink mb-1">
                  Campaign Title *
                </label>
                <input
                  id="campaign-title"
                  type="text"
                  required
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Q4 Global Product Launch"
                  className="input text-sm"
                />
              </div>

              <div>
                <label htmlFor="campaign-desc" className="block text-xs font-semibold text-ink mb-1">
                  Description
                </label>
                <textarea
                  id="campaign-desc"
                  rows={2}
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Goals, channels, and target markets..."
                  className="input text-sm"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    Owner
                  </label>
                  <input
                    type="text"
                    value={newOwner}
                    onChange={(e) => setNewOwner(e.target.value)}
                    placeholder="e.g. Marketing Lead"
                    className="input text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-ink mb-1">
                    External Ref (Jira/Asana)
                  </label>
                  <input
                    type="text"
                    value={newRef}
                    onChange={(e) => setNewRef(e.target.value)}
                    placeholder="e.g. CAMP-402"
                    className="input text-sm"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-rule">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="btn btn-secondary text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !newTitle.trim()}
                  className="btn btn-primary text-xs disabled:opacity-50"
                >
                  {submitting ? "Creating..." : "Create Campaign"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
