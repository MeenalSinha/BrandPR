"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useBrand, useToast } from "@/components/providers";
import { api, errorMessage } from "@/lib/api";
import type { Campaign, CampaignStatus } from "@/types/api";
import { EmptyState } from "@/components/ui";

const STATUS_COLORS: Record<CampaignStatus, string> = {
  draft: "bg-surface-200 text-ink-base border-border-base",
  in_review: "bg-amber-100 text-amber-900 border-amber-300",
  blocked: "bg-red-100 text-red-900 border-red-300",
  needs_review: "bg-orange-100 text-orange-900 border-orange-300",
  ready_for_release: "bg-emerald-100 text-emerald-900 border-emerald-300",
  released: "bg-indigo-100 text-indigo-900 border-indigo-300",
  archived: "bg-surface-200 text-ink-muted border-border-base",
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
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border-base pb-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink-base">
            Campaigns & Portfolios
          </h1>
          <p className="text-sm text-ink-muted mt-1">
            Group related marketing content, audit portfolio consistency, and gate releases with evidence-backed decisions.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-brand-primary text-white rounded-md text-sm font-medium hover:bg-brand-primary/90 transition shadow-sm"
          >
            + New Campaign
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2 border-b border-border-base/50">
        <span className="text-xs uppercase tracking-wider font-semibold text-ink-muted mr-2">Status:</span>
        {["all", "draft", "in_review", "blocked", "needs_review", "ready_for_release", "released"].map((st) => (
          <button
            key={st}
            onClick={() => setStatusFilter(st)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition ${
              statusFilter === st
                ? "bg-brand-primary/10 text-brand-primary border-brand-primary/30"
                : "bg-surface-100 text-ink-muted border-border-base hover:bg-surface-200"
            }`}
          >
            {st.replace(/_/g, " ").toUpperCase()}
          </button>
        ))}
      </div>

      {/* Campaign List */}
      {loading ? (
        <div className="p-12 text-center text-sm text-ink-muted">Loading campaigns...</div>
      ) : campaigns.length === 0 ? (
        <EmptyState title="No campaigns found">
          {statusFilter === "all"
            ? "Create your first campaign to audit assets together and gate releases."
            : `No campaigns match status "${statusFilter.replace(/_/g, " ")}".`}
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {campaigns.map((camp) => (
            <Link
              key={camp.id}
              href={`/campaigns/${camp.id}`}
              className="group block p-5 rounded-lg border border-border-base bg-surface-base hover:border-brand-primary/40 hover:shadow-md transition space-y-3"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold text-ink-base group-hover:text-brand-primary transition">
                  {camp.title}
                </h3>
                <span
                  className={`px-2 py-0.5 rounded text-xs font-semibold border ${
                    STATUS_COLORS[camp.status] || "bg-surface-200 text-ink-base border-border-base"
                  }`}
                >
                  {camp.status.replace(/_/g, " ").toUpperCase()}
                </span>
              </div>

              {camp.description && (
                <p className="text-xs text-ink-muted line-clamp-2">{camp.description}</p>
              )}

              <div className="pt-3 border-t border-border-base/50 grid grid-cols-3 gap-2 text-center text-xs text-ink-muted">
                <div>
                  <span className="block font-semibold text-ink-base">{camp.asset_count}</span>
                  <span>Assets</span>
                </div>
                <div>
                  <span className={`block font-semibold ${camp.blocker_count > 0 ? "text-red-600" : "text-ink-base"}`}>
                    {camp.blocker_count}
                  </span>
                  <span>Blockers</span>
                </div>
                <div>
                  <span className={`block font-semibold ${camp.warning_count > 0 ? "text-amber-600" : "text-ink-base"}`}>
                    {camp.warning_count}
                  </span>
                  <span>Warnings</span>
                </div>
              </div>

              {camp.latest_audit_stale && (
                <div className="text-[11px] font-medium text-amber-700 bg-amber-50 px-2 py-1 rounded border border-amber-200">
                  ⚠️ Audit is stale. Needs re-evaluation.
                </div>
              )}
            </Link>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-surface-base border border-border-base rounded-lg shadow-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold text-ink-base">Create New Campaign</h2>
            <form onSubmit={handleCreateCampaign} className="space-y-4">
              <div>
                <label htmlFor="campaign-title" className="block text-xs font-medium text-ink-muted mb-1">
                  Campaign Title *
                </label>
                <input
                  id="campaign-title"
                  type="text"
                  required
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Q4 Global Product Launch"
                  className="w-full px-3 py-2 text-sm border border-border-base rounded-md focus:outline-none focus:border-brand-primary"
                />
              </div>

              <div>
                <label htmlFor="campaign-desc" className="block text-xs font-medium text-ink-muted mb-1">
                  Description
                </label>
                <textarea
                  id="campaign-desc"
                  rows={2}
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Goals, channels, and target markets..."
                  className="w-full px-3 py-2 text-sm border border-border-base rounded-md focus:outline-none focus:border-brand-primary"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-ink-muted mb-1">
                    Owner
                  </label>
                  <input
                    type="text"
                    value={newOwner}
                    onChange={(e) => setNewOwner(e.target.value)}
                    placeholder="e.g. Marketing Lead"
                    className="w-full px-3 py-2 text-sm border border-border-base rounded-md focus:outline-none focus:border-brand-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-ink-muted mb-1">
                    External Ref (Jira/Asana)
                  </label>
                  <input
                    type="text"
                    value={newRef}
                    onChange={(e) => setNewRef(e.target.value)}
                    placeholder="e.g. CAMP-402"
                    className="w-full px-3 py-2 text-sm border border-border-base rounded-md focus:outline-none focus:border-brand-primary"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 border border-border-base rounded-md text-xs font-medium hover:bg-surface-200 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !newTitle.trim()}
                  className="px-4 py-2 bg-brand-primary text-white rounded-md text-xs font-medium hover:bg-brand-primary/90 transition disabled:opacity-50"
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
