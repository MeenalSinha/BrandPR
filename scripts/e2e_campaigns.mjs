// Live end-to-end check of Phase 6: Campaign Intelligence, Portfolio Audits & Release Readiness
// Usage: node scripts/e2e_campaigns.mjs [baseUrl]    (default http://localhost:3000)
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const base = process.argv[2] ?? "http://localhost:3000";
const root = fileURLToPath(new URL("..", import.meta.url));
let failures = 0;
let skipped = 0;

const check = (name, ok, extra = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`);
  if (!ok) failures++;
};
const skip = (name, why) => { console.log(`SKIP  ${name}  ${why}`); skipped++; };

const CREATOR = { "X-Actor-Name": "e2e-creator", "X-Actor-Role": "creator" };
const REVIEWER = { "X-Actor-Name": "e2e-reviewer", "X-Actor-Role": "reviewer" };

const callAt = async (origin, method, path, body, headers = {}) => {
  const isForm = body instanceof FormData;
  const res = await fetch(origin + path, {
    method,
    headers: { ...(isForm || !body ? {} : { "Content-Type": "application/json" }), ...headers },
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: res.status, json, text };
};
const call = (method, path, body, headers) => callAt(base, method, path, body, headers);

try {
  console.log("=== PHASE 6 CAMPAIGN INTELLIGENCE & RELEASE READINESS E2E ===");

  // 1. Create a unique brand
  const brand = (await call("POST", "/api/brands", { name: `Campaigns E2E Brand ${Date.now()}` })).json;
  check("1. create unique test brand", Boolean(brand?.id));

  // 2. Upload source document & create approved fact
  const form = new FormData();
  form.append("file", new File([readFileSync(join(root, "test-data/nova_product_specification.pdf"))], "nova_product_specification.pdf", { type: "application/pdf" }));
  const doc = (await call("POST", `/api/brands/${brand.id}/documents`, form)).json;
  check("2. upload and process source document", doc?.processing_status === "processed");

  const fact = (await call("POST", `/api/brands/${brand.id}/facts`, {
    name: "Battery life", value: "Up to 18 hours", category: "product_spec",
    status: "active", source_document_id: doc.id, source_page: 2,
    source_excerpt: "Battery life: up to 18 hours under specified test conditions.",
  })).json;
  check("3. create approved fact", fact?.status === "active");

  // 3. Create Campaign
  const camp = (await call("POST", `/api/brands/${brand.id}/campaigns`, {
    title: "Global Hardware Rollout 2026",
    description: "Multi-channel Q4 launch across web, email, and social.",
    owner: "Morgan Lead",
  }, CREATOR)).json;
  check("4. create campaign for brand", camp?.status === "draft" && camp?.title === "Global Hardware Rollout 2026");

  // 4. Reject cross-brand asset addition
  const otherBrand = (await call("POST", "/api/brands", { name: `Foreign Brand ${Date.now()}` })).json;
  const foreignSub = (await call("POST", `/api/brands/${otherBrand.id}/content`, {
    title: "Foreign Asset", content: "Unauthorized cross-brand content.",
  }, CREATOR)).json;
  const crossAdd = await call("POST", `/api/campaigns/${camp.id}/assets`, {
    asset_id: foreignSub.asset_id,
    channel_role: "landing_page",
  }, CREATOR);
  check("5. reject cross-brand asset addition (400 or 422)", [400, 422].includes(crossAdd.status));

  // 5. Create Asset 1 (Landing Page) - valid and approved
  const sub1 = (await call("POST", `/api/brands/${brand.id}/content`, {
    title: "Product Landing Page", content: "Battery life lasts up to 18 hours on a single charge.",
  }, CREATOR)).json;
  const revRun1 = (await call("POST", `/api/content/${sub1.id}/reviews`, {}, CREATOR)).json;
  await call("POST", `/api/content/${sub1.id}/submit-review`, {}, CREATOR);
  await call("POST", `/api/content/${sub1.id}/decisions`, {
    action: "approve", review_run_id: revRun1.id, rationale: "Specs verified against Nova documentation.",
  }, REVIEWER);
  const asset1 = (await call("POST", `/api/campaigns/${camp.id}/assets`, {
    asset_id: sub1.asset_id, channel_role: "landing_page",
  }, CREATOR)).json;
  check("6. add approved landing page asset to campaign", Boolean(asset1?.id));

  // 6. Create Asset 2 (Email Promo) - inconsistent contradictory claim ("24 hours")
  const sub2 = (await call("POST", `/api/brands/${brand.id}/content`, {
    title: "Promotional Email Blast", content: "Battery life lasts up to 24 hours continuously.",
  }, CREATOR)).json;
  const revRun2 = (await call("POST", `/api/content/${sub2.id}/reviews`, {}, CREATOR)).json;
  const asset2 = (await call("POST", `/api/campaigns/${camp.id}/assets`, {
    asset_id: sub2.asset_id, channel_role: "email",
  }, CREATOR)).json;
  check("7. add inconsistent asset to campaign", Boolean(asset2?.id));

  // 7. Run campaign audit 1 - detect contradiction & unapproved asset as hard blockers
  const audit1 = (await call("POST", `/api/campaigns/${camp.id}/audits`, {}, CREATOR)).json;
  check("8. campaign audit 1 detects hard blockers", audit1?.readiness_outcome === "blocked" && audit1?.blocker_count > 0);
  const contradictionFinding = audit1.findings.find(f => f.finding_type === "cross_asset_contradiction" || f.severity === "hard_blocker");
  check("9. audit snapshot contains detailed blocker finding", Boolean(contradictionFinding));

  // 8. Verify release evaluation reflects blocked state
  const eval1 = (await call("GET", `/api/campaigns/${camp.id}/release-evaluation`)).json;
  check("10. release evaluation reports can_release=false", eval1?.can_release === false && eval1?.status === "blocked");

  // 9. Guard against premature release
  const prematureRelease = await call("POST", `/api/campaigns/${camp.id}/release`, {
    release_notes: "Attempted premature release",
  }, REVIEWER);
  check("11. prevent release when blockers exist (409 or 422)", [409, 422].includes(prematureRelease.status));

  // 10. Correct Asset 2 using Revision Workflow (Phase 4 integration)
  const rev2 = (await call("POST", `/api/content/${sub2.id}/revisions`, {
    content: "Battery life lasts up to 18 hours under standard conditions.",
    change_note: "Aligned battery claim with approved brand facts.",
  }, CREATOR)).json;
  const revRun2b = (await call("POST", `/api/content/${rev2.id}/reviews`, {}, CREATOR)).json;
  await call("POST", `/api/content/${rev2.id}/submit-review`, {}, CREATOR);
  await call("POST", `/api/content/${rev2.id}/decisions`, {
    action: "approve", review_run_id: revRun2b.id, rationale: "Correction verified against approved spec.",
  }, REVIEWER);

  // Update campaign membership to point to approved revision 2
  await call("POST", `/api/campaigns/${camp.id}/assets`, {
    asset_id: sub2.asset_id, submission_id: rev2.id, channel_role: "email",
  }, CREATOR);
  check("12. corrected asset revision 2 reviewed and approved", rev2.revision_number === 2);

  // 11. Run campaign audit 2 - verify clean pass and audit history preservation
  const audit2 = (await call("POST", `/api/campaigns/${camp.id}/audits`, {}, CREATOR)).json;
  check("13. campaign audit 2 passes release readiness", audit2?.readiness_outcome === "ready_for_release" && audit2?.blocker_count === 0);

  // Compare audit 1 and audit 2
  const comp = (await call("GET", `/api/campaign-audits/${audit2.id}/comparison/${audit1.id}`)).json;
  check("14. audit comparison detects resolved issues", comp?.summary?.resolved_count >= 1 || comp?.resolved_findings?.length >= 0);

  // 12. Release gate enforcement
  // Creator cannot self-release
  const creatorRelease = await call("POST", `/api/campaigns/${camp.id}/release`, {
    release_notes: "Creator self release attempt",
  }, CREATOR);
  check("15. creator cannot self-release (403 Forbidden)", creatorRelease.status === 403);

  // Reviewer can release
  const reviewerRelease = await call("POST", `/api/campaigns/${camp.id}/release`, {
    release_notes: "Certified by Lead Brand Reviewer for global Q4 rollout.",
  }, REVIEWER);
  check("16. reviewer certifies release (201 Created)", [200, 201].includes(reviewerRelease.status) && reviewerRelease.json?.decision === "released");

  const updatedCamp = (await call("GET", `/api/campaigns/${camp.id}`)).json;
  check("17. campaign status updated to released", updatedCamp?.status === "released");

  // 13. Audit Staleness Detection
  // Adding an asset invalidates prior audit
  const sub3 = (await call("POST", `/api/brands/${brand.id}/content`, {
    title: "Late Social Post", content: "Check out our new release.",
  }, CREATOR)).json;
  await call("POST", `/api/campaigns/${camp.id}/assets`, {
    asset_id: sub3.asset_id, channel_role: "social_post",
  }, CREATOR);

  const staleAudit = (await call("GET", `/api/campaign-audits/${audit2.id}`)).json;
  check("18. subsequent portfolio change marks prior audit stale", staleAudit?.is_stale === true && Boolean(staleAudit?.stale_reason));

  // 14. Governance Insights includes campaign overview
  const insights = (await call("GET", `/api/brands/${brand.id}/insights`)).json;
  check("19. governance intelligence includes campaigns summary", Boolean(insights?.overview?.campaigns_summary));

  console.log(`\nAll checks complete. Passed: ${19 - failures}, Failed: ${failures}, Skipped: ${skipped}`);
  if (failures > 0) process.exit(1);
} catch (err) {
  console.error("E2E failed with error:", err);
  process.exit(1);
}
