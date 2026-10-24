"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useBrand, useToast } from "@/components/providers";
import { api, errorMessage, getIdentity } from "@/lib/api";
import type {
  Campaign,
  CampaignAsset,
  CampaignAudit,
  ChannelRole,
  ContentSummary,
  ReleaseEvaluation,
} from "@/types/api";
import { EmptyState } from "@/components/ui";
import { IconCheck, IconAlert, IconCampaigns, IconPlus, IconExternalLink } from "@/components/Icons";

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
    return <div className="p-12 text-center text-sm text-ink-muted rounded-xl border border-rule bg-sheet">Loading campaign details...</div>;
  }

  if (!campaign) {
    return <div className="p-12 text-center text-sm text-terracotta rounded-xl border border-terracotta/30 bg-terracotta-soft">Campaign not found.</div>;
  }

  return (
    <div className="space-y-6">
      {/* Back Link & Header */}
      <div className="space-y-3">
        <Link href="/campaigns" className="inline-flex items-center gap-1.5 text-xs text-signal hover:text-signal-dark font-medium transition">
          <span>&larr; Back to Campaigns</span>
        </Link>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between border-b border-rule pb-5">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-serif font-bold tracking-tight text-ink">
                {campaign.title}
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider border bg-surface-100 text-ink border-rule">
                {campaign.status.replace(/_/g, " ")}
              </span>
            </div>
            {campaign.description && (
              <p className="text-sm text-ink-muted max-w-3xl leading-relaxed">{campaign.description}</p>
            )}
            <div className="flex flex-wrap items-center gap-4 text-xs text-ink-muted pt-1">
              {campaign.owner && <span>Owner: <strong className="text-ink font-semibold">{campaign.owner}</strong></span>}
              {campaign.external_reference && <span>Ref: <strong className="text-ink font-semibold font-mono">{campaign.external_reference}</strong></span>}
              <span>Created: {new Date(campaign.created_at).toLocaleDateString()}</span>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-shrink-0">
            <button
              onClick={handleRunAudit}
              disabled={auditing}
              className="btn btn-primary text-xs shadow-subtle flex items-center gap-1.5 disabled:opacity-50"
            >
              <span>{auditing ? "Auditing Portfolio..." : "⚡ Run Campaign Audit"}</span>
            </button>
            {evaluation?.can_release && campaign.status !== "released" && (
              <button
                onClick={() => setShowReleaseModal(true)}
                className="btn bg-signal text-white hover:bg-signal-dark text-xs font-semibold shadow-subtle flex items-center gap-1.5"
              >
                <span>🚀 Release Campaign</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Release Readiness Banner */}
      {evaluation && (
        <div
          className={`p-5 rounded-xl border text-sm space-y-3 shadow-subtle transition-all ${
            campaign.status === "released"
              ? "bg-blue-50/70 border-blue-200 text-blue-950"
              : evaluation.can_release
              ? "bg-signal-wash border-signal/30 text-signal-dark"
              : evaluation.is_stale
              ? "bg-amber-50/80 border-amber-200 text-amber-950"
              : "bg-terracotta-soft border-terracotta/30 text-terracotta"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="font-serif font-bold text-base flex items-center gap-2">
              {campaign.status === "released" && "✓ Campaign Released"}
              {campaign.status !== "released" && evaluation.can_release && "✓ Release Ready — All Checks Passed"}
              {campaign.status !== "released" && evaluation.is_stale && "⚠️ Audit Stale — Re-evaluation Required"}
              {campaign.status !== "released" && !evaluation.can_release && !evaluation.is_stale && "⛔ Release Blocked — Integrity Checks Failed"}
            </span>
            <span className="text-xs font-mono opacity-80">
              {latestAudit ? `Audit #${latestAudit.audit_number} • ${new Date(latestAudit.created_at).toLocaleTimeString()}` : "Never audited"}
            </span>
          </div>

          {evaluation.blockers.length > 0 ? (
            <div className="space-y-1.5 pt-1">
              <span className="text-xs font-semibold uppercase tracking-wider">Release Blockers:</span>
              <ul className="list-disc pl-5 text-xs space-y-1">
                {evaluation.blockers.map((b, i) => (
                  <li key={i} className="font-medium">{b}</li>
                ))}
              </ul>
            </div>
          ) : campaign.status === "released" ? (
            <p className="text-xs opacity-90">
              Released by <strong className="font-semibold">{campaign.released_by}</strong> on {new Date(campaign.released_at!).toLocaleString()}.
            </p>
          ) : (
            <p className="text-xs opacity-90 leading-relaxed">
              All portfolio consistency, fact integrity, and approval checks have passed for this campaign. The portfolio is certified for external publication.
            </p>
          )}
        </div>
      )}

      {/* Assets Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-serif font-bold text-ink">
              Campaign Assets ({assets.length})
            </h2>
            <p className="text-xs text-ink-muted">Assets included in this campaign for cross-channel consistency audit.</p>
          </div>
          <button
            onClick={openAddModal}
            className="btn btn-secondary text-xs flex items-center gap-1.5"
          >
            <IconPlus className="w-3.5 h-3.5" />
            <span>+ Add Asset</span>
          </button>
        </div>

        {assets.length === 0 ? (
          <EmptyState title="No assets added">
            Add marketing content assets (landing page, ad, email, etc.) to evaluate consistency and release readiness.
          </EmptyState>
        ) : (
          <div className="border border-rule rounded-xl overflow-hidden bg-sheet shadow-subtle">
            <table className="w-full text-left text-xs">
              <thead className="bg-paper text-ink-muted uppercase border-b border-rule">
                <tr>
                  <th className="py-3 px-4 font-semibold tracking-wider">Asset Title</th>
                  <th className="py-3 px-4 font-semibold tracking-wider">Channel / Role</th>
                  <th className="py-3 px-4 font-semibold tracking-wider">Revision</th>
                  <th className="py-3 px-4 font-semibold tracking-wider">Workflow Status</th>
                  <th className="py-3 px-4 font-semibold tracking-wider text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {assets.map((a) => (
                  <tr key={a.id} className="hover:bg-paper/50 transition">
                    <td className="py-3.5 px-4 font-medium text-ink">
                      <Link href={`/review?content_id=${a.selected_submission_id}`} className="hover:text-signal transition font-semibold">
                        {a.asset_title || "Untitled Asset"}
                      </Link>
                    </td>
                    <td className="py-3.5 px-4 capitalize text-ink-muted font-medium">
                      <span className="inline-flex items-center px-2 py-0.5 rounded bg-surface-100 border border-rule text-ink">
                        {a.channel_role.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-ink-muted font-semibold">
                      v{a.revision_number}
                    </td>
                    <td className="py-3.5 px-4">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wider border ${
                          a.workflow_status === "approved"
                            ? "bg-signal-wash text-signal-dark border-signal/30"
                            : a.workflow_status === "in_review"
                            ? "bg-amber-50 text-amber-800 border-amber-200"
                            : "bg-surface-100 text-ink-muted border-rule"
                        }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          a.workflow_status === "approved" ? "bg-signal" : a.workflow_status === "in_review" ? "bg-amber-500" : "bg-ink-muted"
                        }`} />
                        {a.workflow_status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => handleRemoveAsset(a.asset_id)}
                        className="text-terracotta hover:underline font-semibold text-xs"
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
        <div className="space-y-4 pt-4 border-t border-rule">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
              <h2 className="text-lg font-serif font-bold text-ink">
                Audit Findings ({latestAudit.findings.length})
              </h2>
              <p className="text-xs text-ink-muted">Detailed cross-asset claims, conflicts, and verification checks.</p>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="px-2.5 py-1 rounded-md bg-terracotta-soft text-terracotta border border-terracotta/20 font-medium">
                Blockers: <strong className="font-bold">{latestAudit.blocker_count}</strong>
              </span>
              <span className="px-2.5 py-1 rounded-md bg-amber-50 text-amber-900 border border-amber-200 font-medium">
                Warnings: <strong className="font-bold">{latestAudit.warning_count}</strong>
              </span>
              <span className="px-2.5 py-1 rounded-md bg-signal-wash text-signal-dark border border-signal/20 font-medium">
                Passed: <strong className="font-bold">{latestAudit.passed_checks_count}</strong>
              </span>
            </div>
          </div>

          <div className="space-y-3">
            {latestAudit.findings.map((f) => {
              const isBlocker = f.severity === "hard_blocker";
              const isWarning = f.severity === "warning";
              return (
                <div
                  key={f.id}
                  className={`p-4 rounded-xl border text-xs space-y-2.5 transition ${
                    isBlocker
                      ? "border-terracotta/40 bg-terracotta-soft/50"
                      : isWarning
                      ? "border-amber-200 bg-amber-50/50"
                      : "border-rule bg-sheet"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className={`px-2 py-0.5 rounded-full font-bold text-[10px] uppercase tracking-wider border ${
                          isBlocker
                            ? "bg-terracotta text-white border-terracotta"
                            : isWarning
                            ? "bg-amber-100 text-amber-900 border-amber-300"
                            : "bg-surface-100 text-ink border-rule"
                        }`}
                      >
                        {f.severity.replace(/_/g, " ")}
                      </span>
                      <span className="font-serif font-bold text-ink">
                        {f.finding_type.replace(/_/g, " ").toUpperCase()}
                      </span>
                      {f.asset_title && (
                        <span className="text-ink-muted">
                          &bull; Asset: <strong className="text-ink font-semibold">{f.asset_title}</strong> (v{f.revision_number})
                        </span>
                      )}
                    </div>
                    <span className="text-ink-muted capitalize text-[11px] font-mono px-2 py-0.5 rounded bg-paper border border-rule">
                      {f.confidence} confidence
                    </span>
                  </div>

                  {f.claim_text && (
                    <div className="p-2.5 bg-sheet rounded-lg border border-rule/80 font-mono text-[11px] text-ink leading-relaxed">
                      &ldquo;{f.claim_text}&rdquo;
                    </div>
                  )}

                  <p className="text-ink font-medium leading-relaxed">{f.explanation}</p>

                  <div className="pt-2 border-t border-rule/50 flex flex-wrap items-center justify-between gap-2 text-ink-muted text-[11px]">
                    <span>Action: <strong className="text-ink">{f.recommended_action}</strong></span>
                    {f.source_page && (
                      <span className="font-mono">Source Page: {f.source_page}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Add Asset Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-md bg-sheet border border-rule rounded-xl shadow-overlay p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div>
              <h2 className="text-lg font-serif font-bold text-ink">Add Asset to Campaign</h2>
              <p className="text-xs text-ink-muted mt-0.5">Select content from the brand repository to bind to this portfolio.</p>
            </div>
            <form onSubmit={handleAddAsset} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-ink mb-1">
                  Select Brand Content Asset *
                </label>
                <select
                  required
                  value={selectedAssetId}
                  onChange={(e) => setSelectedAssetId(e.target.value)}
                  className="input text-sm"
                >
                  {availableContent.map((c) => (
                    <option key={c.id} value={c.asset_id}>
                      {c.title} (v{c.revision_number} - {c.workflow_status})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1">
                  Channel / Role
                </label>
                <select
                  value={selectedRole}
                  onChange={(e) => setSelectedRole(e.target.value as ChannelRole)}
                  className="input text-sm"
                >
                  {CHANNEL_ROLES.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-rule">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="btn btn-secondary text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addingAsset || !selectedAssetId}
                  className="btn btn-primary text-xs disabled:opacity-50"
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-md bg-sheet border border-rule rounded-xl shadow-overlay p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div>
              <h2 className="text-lg font-serif font-bold text-ink">Release Campaign</h2>
              <p className="text-xs text-ink-muted mt-1 leading-relaxed">
                You are certifying that all marketing assets in this campaign are approved, consistent, and ready for publication.
              </p>
            </div>
            <form onSubmit={handleReleaseCampaign} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-ink mb-1">
                  Release Notes
                </label>
                <textarea
                  rows={3}
                  value={releaseNotes}
                  onChange={(e) => setReleaseNotes(e.target.value)}
                  placeholder="e.g. Q4 Global Release certified by Brand Reviewer."
                  className="input text-sm"
                />
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-rule">
                <button
                  type="button"
                  onClick={() => setShowReleaseModal(false)}
                  className="btn btn-secondary text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={releasing}
                  className="btn bg-signal text-white hover:bg-signal-dark text-xs font-semibold disabled:opacity-50"
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
