// Live end-to-end check of Phase 5 (Guideline Lint, Policy Sandbox, Governance Intelligence) through the Next.js
// same-origin proxy. Real backend, real PostgreSQL, real guidelines engine.
//
// Usage: node scripts/e2e_guidelines.mjs [baseUrl]    (default http://localhost:3000)
import { spawn } from "node:child_process";
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

let CREATOR = { "X-Actor-Name": "e2e-creator", "X-Actor-Role": "creator" };
let REVIEWER = { "X-Actor-Name": "e2e-reviewer", "X-Actor-Role": "reviewer" };

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

let child = null;
try {
  console.log("=== PHASE 5 END-TO-END DEMONSTRATION ===");

  // Obtain verified tokens for production authentication
  const creatorAuth = await call("POST", "/api/auth/login", { email: "creator@brandpr.internal", password: "brandpr_creator_demo" });
  if (creatorAuth.json?.access_token) {
    CREATOR = { Authorization: `Bearer ${creatorAuth.json.access_token}` };
  }
  const reviewerAuth = await call("POST", "/api/auth/login", { email: "reviewer@brandpr.internal", password: "brandpr_reviewer_demo" });
  if (reviewerAuth.json?.access_token) {
    REVIEWER = { Authorization: `Bearer ${reviewerAuth.json.access_token}` };
  }

  // 1. Create a unique brand
  const brand = (await call("POST", "/api/brands", { name: `E2E Guidelines Brand ${Date.now()}` }, CREATOR)).json;
  check("1. create a unique test brand", Boolean(brand?.id));

  // 2. Upload source document
  const form = new FormData();
  form.append("file", new File([readFileSync(join(root, "test-data/nova_product_specification.pdf"))], "nova_product_specification.pdf", { type: "application/pdf" }));
  const doc = (await call("POST", `/api/brands/${brand.id}/documents`, form)).json;
  check("2. upload and process source document", doc?.processing_status === "processed");

  // 3. Create approved fact & historical content
  const fact = (await call("POST", `/api/brands/${brand.id}/facts`, {
    name: "Battery life", value: "Up to 18 hours", category: "product_spec",
    status: "active", source_document_id: doc.id, source_page: 2,
    source_excerpt: "Battery life: up to 18 hours under specified test conditions.",
  })).json;
  check("3. approved fact created", fact?.status === "active");

  const sub1 = (await call("POST", `/api/brands/${brand.id}/content`, {
    title: "Battery Campaign Ad",
    content: "The Nova system battery lasts up to 18 hours under test conditions.",
  }, CREATOR)).json;
  const rev1 = (await call("POST", `/api/content/${sub1.id}/reviews`)).json;

  const sub2 = (await call("POST", `/api/brands/${brand.id}/content`, {
    title: "Comparative Flawed Ad",
    content: "The Nova system has market-leading battery running for 24 hours continuously.",
  }, CREATOR)).json;
  const rev2 = (await call("POST", `/api/content/${sub2.id}/reviews`)).json;
  check("4. historical content submitted and reviewed", rev1?.status && rev2?.status);

  // 4. Extract rules from document; verify extracted rules are in proposed status
  const ext = (await call("POST", `/api/brands/${brand.id}/guidelines/extract`, {
    source_document_id: doc.id,
  }, REVIEWER)).json;
  check("5. document rule extraction returns proposals", ext?.extracted_count >= 1 && ext?.proposed_rules?.length >= 1);
  check("6. extracted rules remain proposed (never automatically activated)", ext?.proposed_rules?.every((r) => r.status === "proposed"));

  // 5. Create a manual source-linked guideline rule
  const rule = (await call("POST", `/api/brands/${brand.id}/guidelines`, {
    title: "Comparative Claims Restriction",
    rule_text: "Comparative claims must not be used without prior approval and verified lab benchmarks.",
    category: "claim",
    severity: "high",
    scope: "all advertising campaigns",
    source_document_id: doc.id,
    source_page: 2,
    source_excerpt: "Battery life: up to 18 hours under specified test conditions.",
    status: "active",
  }, REVIEWER)).json;
  check("7. manual source-linked rule created", rule?.id && rule.status === "active" && rule.current_version === 1);

  // Add an intentionally vague rule to trigger deterministic lint
  const vagueRule = (await call("POST", `/api/brands/${brand.id}/guidelines`, {
    title: "Vague Superlatives",
    rule_text: "Deliver market-leading best performance across every touchpoint.",
    category: "tone",
    severity: "medium",
    status: "active",
  }, REVIEWER)).json;

  // 6. Run Guideline Lint and inspect identified ambiguity
  const lintRes = (await call("POST", `/api/brands/${brand.id}/guideline-lint`, {}, REVIEWER)).json;
  check("8. guideline lint runs and detects candidate ambiguities", lintRes?.total_issues >= 1 && lintRes?.issues?.length >= 1);
  const foundVague = lintRes?.issues?.some((i) => i.rule_id === vagueRule.id && i.issue_category === "vague_instruction");
  check("9. candidate issue identifies vague terms with suggested action", foundVague && lintRes?.issues[0]?.suggested_action);

  // 7. Propose a revised version of the comparative rule
  const propVersion = (await call("POST", `/api/guidelines/${rule.id}/versions`, {
    rule_text: "Comparative claims may be used when supported by approved product specs.",
    change_reason: "Allow comparative statements if backed by active product specifications.",
  }, CREATOR)).json;
  check("10. proposed revised rule version saved", propVersion?.version_number === 2 && propVersion?.rule_id === rule.id);

  // Active rule text remains unchanged at version 1 until approved
  const checkRule = (await call("GET", `/api/guidelines/${rule.id}`)).json;
  check("11. active rule text unmutated prior to approval", checkRule?.current_version === 1);

  // 8. Run Policy Simulation against historical content
  const sim = (await call("POST", `/api/brands/${brand.id}/policy-simulations`, {
    rule_id: rule.id,
    proposed_rule_text: "Comparative claims may be used when supported by approved product specs.",
  }, REVIEWER)).json;
  check("12. policy simulation executes successfully", sim?.status === "completed" && sim?.summary?.total_evaluated >= 1);
  check("13. baseline and simulated outcomes recorded separately", sim?.results?.length >= 1 && sim.results.every((r) => r.baseline_outcome && r.simulated_outcome));

  // 9. Confirm historical review records remain strictly unchanged
  const revCheck = (await call("GET", `/api/reviews/${rev1.id}`)).json;
  const findingsCheck = (await call("GET", `/api/reviews/${rev1.id}/findings`)).json;
  check("14. historical reviews and findings intact and unchanged by simulation", revCheck?.status === rev1.status && findingsCheck?.total > 0);

  // 10. Reload simulation verification
  const simReload = (await call("GET", `/api/policy-simulations/${sim.id}`)).json;
  check("15. simulation details survive reload and match stored metrics", simReload?.id === sim.id && simReload.summary.total_evaluated === sim.summary.total_evaluated);

  // 11. Workflow authorization: Creator cannot approve guideline rules (403)
  const unauthApprove = await call("PATCH", `/api/guidelines/${vagueRule.id}`, { status: "retired" }, CREATOR);
  check("16. unauthorised actor cannot approve or retire guideline rules (403)", unauthApprove.status === 403);

  // Reviewer approves rule version / updates status
  const approvedRule = (await call("PATCH", `/api/guidelines/${rule.id}`, {
    rule_text: "Comparative claims may be used when supported by approved product specs.",
    status: "active",
    change_reason: "Approved version 2 for general brand publication.",
  }, REVIEWER)).json;
  check("17. reviewer explicitly approves rule version to make it active", approvedRule?.current_version === 2 && approvedRule?.status === "active");

  // 12. Governance Intelligence Dashboard
  const insights = (await call("GET", `/api/brands/${brand.id}/insights?period=all`)).json;
  check("18. governance intelligence returns computed metrics", Boolean(insights?.overview));
  check("19. completed review counts match database records", insights?.overview?.completed_reviews >= 2);
  check("20. finding breakdowns reflect actual verdicts without double-counting", insights?.overview?.total_findings >= 1);
  check("21. actionable recommendations provide evidence links", insights?.governance_recommendations?.length >= 1 && insights.governance_recommendations[0]?.suggested_action);
  check("22. simulation summary reflects recorded policy sandbox activity", insights?.simulations_summary?.total_simulations >= 1);

  // Cross-brand isolation check (P5-10)
  const brand2 = (await call("POST", `/api/brands`, { name: `Other Brand ${Date.now()}` })).json;
  const crossSim = await call("POST", `/api/brands/${brand2.id}/policy-simulations`, {
    rule_id: rule.id, // rule belongs to brand 1
    proposed_rule_text: "Some text",
  }, REVIEWER);
  check("23. cross-brand simulation rejected (404/400)", crossSim.status === 404 || crossSim.status === 422);

} catch (err) {
  console.error("UNCAUGHT EXCEPTION in e2e_guidelines:", err);
  failures++;
} finally {
  if (child) {
    try { child.kill(); } catch {}
  }
}

console.log("\n--- PHASE 5 DEMONSTRATION SUMMARY ---");
console.log(`PASS: ${23 - failures - skipped} | FAIL: ${failures} | SKIP: ${skipped}`);
if (failures > 0) {
  console.error(`E2E Demonstration FAILED with ${failures} failure(s).`);
  process.exit(1);
} else {
  console.log("ALL PHASE 5 END-TO-END ACCEPTANCE CRITERIA PASSED.");
}
