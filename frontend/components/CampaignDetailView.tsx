"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useBrand, useToast } from "@/components/providers";
import { api, errorMessage, getIdentity } from "@/lib/api";
import type {
  Campaign,
  CampaignAsset,
  CampaignAudit,
  CampaignAuditFinding,
  ChannelRole,
  ContentSummary,
  ReleaseEvaluation,
} from "@/types/api";
import { EmptyState } from "@/components/ui";

const CHANNEL_ROLES: { id: ChannelRole; label: string }[] = [
  { id: "landing_page", label: "Landing Page" },
  { id: "advertisement", label: "Advertisement" },
  { id: "email", label: "Email Campaign" },
  { id: "social_post", label: "Social Media Post" },
  { id: "product_description", label: "Product Description" },
  { id: "press_release", label: "Press Release" },
  { id: "other", label: "Other" },
];

export function CampaignDetailView({ campaignId }: { campaignId: string }) {
  const { brand } = useBrand();
  const toast = useToast();
  const identity = getIdentity();

  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [assets, setAssets] = useState<CampaignAsset[]>([]);
  const [latestAudit, setLatestAudit] = useState<CampaignAudit | null>(null);
  const [evaluation, setEvaluation] = useState<ReleaseEvaluation | null>(null);
  const [loading, setLoading] = useState(true);
  const [auditing, setAuditing] = useState(false);

  // Add Asset modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [availableContent, setAvailableContent] = useState<ContentSummary[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [selectedRole, setSelectedRole] = useState<ChannelRole>("landing_page");
  const [addingAsset, setAddingAsset] = useState(false);

  // Release modal
  const [showReleaseModal, setShowReleaseModal] = useState(false);
  const [releaseNotes, setReleaseNotes] = useState("");
  const [releasing, setReleasing] = useState(false);

  useEffect(() => {
    loadAll();
  }, [campaignId]);

  async function loadAll() {
    setLoading(true);
    try {
      const camp = await api.getCampaign(campaignId);
      setCampaign(camp);
      setAssets(camp.assets || []);

      if (camp.latest_audit_id) {
        const audit = await api.getCampaignAudit(camp.latest_audit_id);
        setLatestAudit(audit);
      } else {
        setLatestAudit(null);
      }

      const evalData = await api.getReleaseEvaluation(campaignId);
      setEvaluation(evalData);
    } catch (e) {
      toast.push("error", errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleRunAudit() {
    setAuditing(true);
    try {
      const audit = await api.runCampaignAudit(campaignId);
      toast.push("success", `Audit #${audit.audit_number} completed: ${audit.readiness_outcome.replace(/_/g, " ").toUpperCase()}`);
      await loadAll();
    } catch (e) {
      toast.push("error", errorMessage(e));
    } finally {
      setAuditing(false);
    }
  }

  async function openAddModal() {
    if (!brand) return;
    try {
      const res = await api.listContent(brand.id);
      setAvailableContent(res.items || []);
      if (res.items && res.items.length > 0) {
        setSelectedAssetId(res.items[0].asset_id);
      }
      setShowAddModal(true);
    } catch (e) {
      toast.push("error", errorMessage(e));
    }
  }

  async function handleAddAsset(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedAssetId) return;
    setAddingAsset(true);
    try {
      await api.addCampaignAsset(campaignId, {
        asset_id: selectedAssetId,
        channel_role: selectedRole,
      });
      toast.push("success", "Asset added to campaign. Prior audit marked stale.");
      setShowAddModal(false);
      await loadAll();
    } catch (e) {
      toast.push("error", errorMessage(e));
    } finally {
      setAddingAsset(false);
    }
  }

  async function handleRemoveAsset(assetId: string) {
    if (!confirm("Are you sure you want to remove this asset from the campaign?")) return;
    try {
      await api.removeCampaignAsset(campaignId, assetId);
      toast.push("success", "Asset removed from campaign.");
      await loadAll();
    } catch (e) {
      toast.push("error", errorMessage(e));
    }
  }

  async function handleReleaseCampaign(e: React.FormEvent) {
    e.preventDefault();
    setReleasing(true);
    try {
      await api.releaseCampaign(campaignId, {
        release_notes: releaseNotes.trim() || undefined,
      });
      toast.push("success", "Campaign officially released!");
      setShowReleaseModal(false);
      await loadAll();
    } catch (e) {
      toast.push("error", errorMessage(e));
    } finally {
      setReleasing(false);
    }
  }

  if (loading) {
    return <div className="p-12 text-center text-sm text-ink-muted">Loading campaign details...</div>;
  }

  if (!campaign) {
    return <div className="p-12 text-center text-sm text-red-600">Campaign not found.</div>;
  }

  return (
    <div className="space-y-6">
      {/* Back Link & Header */}
      <div className="space-y-2">
        <Link href="/campaigns" className="text-xs text-brand-primary hover:underline font-medium">
          ← Back to Campaigns
        </Link>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border-base pb-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-ink-base">
                {campaign.title}
              </h1>
              <span className="px-2.5 py-0.5 rounded text-xs font-semibold uppercase tracking-wider border bg-surface-200 text-ink-base border-border-base">
                {campaign.status.replace(/_/g, " ")}
              </span>
            </div>
            {campaign.description && (
              <p className="text-sm text-ink-muted mt-1">{campaign.description}</p>
            )}
            <div className="flex items-center gap-4 text-xs text-ink-muted mt-2">
              {campaign.owner && <span>Owner: <strong>{campaign.owner}</strong></span>}
              {campaign.external_reference && <span>Ref: <strong>{campaign.external_reference}</strong></span>}
              <span>Created: {new Date(campaign.created_at).toLocaleDateString()}</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleRunAudit}
              disabled={auditing}
              className="px-4 py-2 bg-brand-primary text-white rounded-md text-xs font-medium hover:bg-brand-primary/90 transition shadow-sm disabled:opacity-50"
            >
              {auditing ? "Auditing Portfolio..." : "⚡ Run Campaign Audit"}
            </button>
            {evaluation?.can_release && campaign.status !== "released" && (
              <button
                onClick={() => setShowReleaseModal(true)}
                className="px-4 py-2 bg-emerald-600 text-white rounded-md text-xs font-semibold hover:bg-emerald-700 transition shadow-sm"
              >
                🚀 Release Campaign
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Release Readiness Banner */}
      {evaluation && (
        <div
          className={`p-4 rounded-lg border text-sm space-y-2 ${
            campaign.status === "released"
              ? "bg-indigo-50 border-indigo-200 text-indigo-900"
              : evaluation.can_release
              ? "bg-emerald-50 border-emerald-200 text-emerald-950"
              : evaluation.is_stale
              ? "bg-amber-50 border-amber-200 text-amber-950"
              : "bg-red-50 border-red-200 text-red-950"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="font-semibold text-base flex items-center gap-2">
              {campaign.status === "released" && "✓ Campaign Released"}
              {campaign.status !== "released" && evaluation.can_release && "✓ Release Ready"}
              {campaign.status !== "released" && evaluation.is_stale && "⚠️ Audit Stale"}
              {campaign.status !== "released" && !evaluation.can_release && !evaluation.is_stale && "⛔ Release Blocked"}
            </span>
            <span className="text-xs">
              {latestAudit ? `Audit #${latestAudit.audit_number} on ${new Date(latestAudit.created_at).toLocaleTimeString()}` : "Never audited"}
            </span>
          </div>

          {evaluation.blockers.length > 0 ? (
            <div className="space-y-1 pt-1">
              <span className="text-xs font-medium uppercase tracking-wider">Release Blockers:</span>
              <ul className="list-disc pl-5 text-xs space-y-0.5">
                {evaluation.blockers.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
          ) : campaign.status === "released" ? (
            <p className="text-xs">
              Released by {campaign.released_by} on {new Date(campaign.released_at!).toLocaleString()}.
            </p>
          ) : (
            <p className="text-xs">
              All portfolio consistency, fact integrity, and approval checks have passed for this campaign.
            </p>
          )}
        </div>
      )}

      {/* Assets Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink-base">
            Campaign Assets ({assets.length})
          </h2>
          <button
            onClick={openAddModal}
            className="px-3 py-1.5 border border-border-base rounded-md text-xs font-medium hover:bg-surface-200 transition"
          >
            + Add Asset
          </button>
        </div>

        {assets.length === 0 ? (
          <EmptyState title="No assets added">
            Add marketing content assets (landing page, ad, email, etc.) to evaluate consistency and release readiness.
          </EmptyState>
        ) : (
          <div className="border border-border-base rounded-lg overflow-hidden bg-surface-base">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-100 text-ink-muted uppercase border-b border-border-base">
                <tr>
                  <th className="py-2.5 px-4 font-medium">Asset Title</th>
                  <th className="py-2.5 px-4 font-medium">Channel / Role</th>
                  <th className="py-2.5 px-4 font-medium">Revision</th>
                  <th className="py-2.5 px-4 font-medium">Workflow Status</th>
                  <th className="py-2.5 px-4 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-base">
                {assets.map((a) => (
                  <tr key={a.id} className="hover:bg-surface-50 transition">
                    <td className="py-3 px-4 font-medium text-ink-base">
                      <Link href={`/review?content_id=${a.selected_submission_id}`} className="hover:text-brand-primary">
                        {a.asset_title || "Untitled Asset"}
                      </Link>
                    </td>
                    <td className="py-3 px-4 capitalize text-ink-muted">
                      {a.channel_role.replace(/_/g, " ")}
                    </td>
                    <td className="py-3 px-4 font-mono text-ink-muted">
                      v{a.revision_number}
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wider ${
                          a.workflow_status === "approved"
                            ? "bg-emerald-100 text-emerald-800"
                            : a.workflow_status === "in_review"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-surface-200 text-ink-muted"
                        }`}
                      >
                        {a.workflow_status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleRemoveAsset(a.asset_id)}
                        className="text-red-600 hover:text-red-800 font-medium text-xs"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Latest Audit Findings */}
      {latestAudit && latestAudit.findings && latestAudit.findings.length > 0 && (
        <div className="space-y-3 pt-4 border-t border-border-base">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-ink-base">
              Audit Findings ({latestAudit.findings.length})
            </h2>
            <div className="flex items-center gap-3 text-xs text-ink-muted">
              <span>Blockers: <strong className="text-red-600">{latestAudit.blocker_count}</strong></span>
              <span>Warnings: <strong className="text-amber-600">{latestAudit.warning_count}</strong></span>
              <span>Passed: <strong className="text-emerald-600">{latestAudit.passed_checks_count}</strong></span>
            </div>
          </div>

          <div className="space-y-3">
            {latestAudit.findings.map((f) => (
              <div
                key={f.id}
                className={`p-4 rounded-lg border text-xs space-y-2 ${
                  f.severity === "hard_blocker"
                    ? "border-red-200 bg-red-50/50"
                    : f.severity === "warning"
                    ? "border-amber-200 bg-amber-50/50"
                    : "border-border-base bg-surface-50"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded font-semibold text-[10px] uppercase tracking-wider ${
                        f.severity === "hard_blocker"
                          ? "bg-red-200 text-red-900"
                          : f.severity === "warning"
                          ? "bg-amber-200 text-amber-900"
                          : "bg-surface-200 text-ink-base"
                      }`}
                    >
                      {f.severity.replace(/_/g, " ")}
                    </span>
                    <span className="font-semibold text-ink-base">
                      {f.finding_type.replace(/_/g, " ").toUpperCase()}
                    </span>
                    {f.asset_title && (
                      <span className="text-ink-muted">
                        • Asset: <strong>{f.asset_title}</strong> (v{f.revision_number})
                      </span>
                    )}
                  </div>
                  <span className="text-ink-muted capitalize text-[11px] font-mono">
                    {f.confidence}
                  </span>
                </div>

                {f.claim_text && (
                  <div className="p-2 bg-surface-base rounded border border-border-base/70 font-mono text-[11px]">
                    "{f.claim_text}"
                  </div>
                )}

                <p className="text-ink-base font-medium">{f.explanation}</p>

                <div className="pt-2 border-t border-border-base/40 flex items-center justify-between text-ink-muted text-[11px]">
                  <span>Action: {f.recommended_action}</span>
                  {f.source_page && (
                    <span>Source Page: {f.source_page}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Add Asset Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-surface-base border border-border-base rounded-lg shadow-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold text-ink-base">Add Asset to Campaign</h2>
            <form onSubmit={handleAddAsset} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-ink-muted mb-1">
                  Select Brand Content Asset *
                </label>
                <select
                  required
                  value={selectedAssetId}
                  onChange={(e) => setSelectedAssetId(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-border-base rounded-md focus:outline-none focus:border-brand-primary"
                >
                  {availableContent.map((c) => (
                    <option key={c.id} value={c.asset_id}>
                      {c.title} (v{c.revision_number} - {c.workflow_status})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-ink-muted mb-1">
                  Channel / Role
                </label>
                <select
                  value={selectedRole}
                  onChange={(e) => setSelectedRole(e.target.value as ChannelRole)}
                  className="w-full px-3 py-2 text-sm border border-border-base rounded-md focus:outline-none focus:border-brand-primary"
                >
                  {CHANNEL_ROLES.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 border border-border-base rounded-md text-xs font-medium hover:bg-surface-200 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addingAsset || !selectedAssetId}
                  className="px-4 py-2 bg-brand-primary text-white rounded-md text-xs font-medium hover:bg-brand-primary/90 transition disabled:opacity-50"
                >
                  {addingAsset ? "Adding..." : "Add Asset"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Release Modal */}
      {showReleaseModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-surface-base border border-border-base rounded-lg shadow-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold text-ink-base">Release Campaign</h2>
            <p className="text-xs text-ink-muted">
              You are certifying that all marketing assets in this campaign are approved, consistent, and ready for publication.
            </p>
            <form onSubmit={handleReleaseCampaign} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-ink-muted mb-1">
                  Release Notes
                </label>
                <textarea
                  rows={3}
                  value={releaseNotes}
                  onChange={(e) => setReleaseNotes(e.target.value)}
                  placeholder="e.g. Q4 Global Release certified by Brand Reviewer."
                  className="w-full px-3 py-2 text-sm border border-border-base rounded-md focus:outline-none focus:border-brand-primary"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowReleaseModal(false)}
                  className="px-4 py-2 border border-border-base rounded-md text-xs font-medium hover:bg-surface-200 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={releasing}
                  className="px-4 py-2 bg-emerald-600 text-white rounded-md text-xs font-semibold hover:bg-emerald-700 transition disabled:opacity-50"
                >
                  {releasing ? "Releasing..." : "Confirm Release"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
