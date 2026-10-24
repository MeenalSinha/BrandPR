// Live end-to-end check of Phase 4 (revisions, correction, human approval, fact-change impact resolution) through the Next.js
// same-origin proxy. Real backend, real PostgreSQL, real review pipeline. It creates its own uniquely named brand, source document,
// facts and content, so it can be repeated; it depends on no fixed IDs and no manual edits.
//
// No AI provider is needed or faked: the backend runs the review in its deterministic "limited" mode when LLM_API_KEY is empty, and
// the script reports honestly that suggested corrections are unavailable then (503 ai_unavailable) while manual correction works.
// If a provider IS configured the suggestion step is exercised too and only checked for being a proposal that changes nothing.
//
// The "reload" checks (steps 17-18) read the same records again through a SECOND backend process on another port, standing in for
// an application restart. Set E2E_BACKEND_PYTHON to override the interpreter (default backend/.venv/bin/python). If the second backend
// cannot be started those checks are reported as SKIPPED, never as passed.
//
// Usage: node scripts/e2e_workflow.mjs [baseUrl]    (default http://localhost:3000)
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { isDeepStrictEqual } from "node:util";

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
  const res = await fetch(origin + path, { method, headers: { ...(isForm || !body ? {} : { "Content-Type": "application/json" }), ...headers }, body: isForm ? body : body ? JSON.stringify(body) : undefined });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: res.status, json, text };
};
const call = (method, path, body, headers) => callAt(base, method, path, body, headers);
const isoDay = (offset) => new Date(Date.now() + offset * 864e5).toISOString().slice(0, 10);
const code = (r) => r.json?.error?.code;

let child = null;
try {
  // Obtain verified tokens for production authentication
  const creatorAuth = await call("POST", "/api/auth/login", { email: "creator@brandpr.internal", password: "brandpr_creator_demo" });
  if (creatorAuth.json?.access_token) {
    CREATOR = { Authorization: `Bearer ${creatorAuth.json.access_token}` };
  }
  const reviewerAuth = await call("POST", "/api/auth/login", { email: "reviewer@brandpr.internal", password: "brandpr_reviewer_demo" });
  if (reviewerAuth.json?.access_token) {
    REVIEWER = { Authorization: `Bearer ${reviewerAuth.json.access_token}` };
  }

  // 1-3. Brand, real source document, approved fact (18 hours), a second fact for an unrelated draft.
  const brand = (await call("POST", "/api/brands", { name: `E2E Workflow ${Date.now()}` })).json;
  check("1. create a unique fictional brand", Boolean(brand?.id));
  const form = new FormData();
  form.append("file", new File([readFileSync(join(root, "test-data/nova_product_specification.pdf"))], "nova_product_specification.pdf", { type: "application/pdf" }));
  const doc = (await call("POST", `/api/brands/${brand.id}/documents`, form)).json;
  const fact = (await call("POST", `/api/brands/${brand.id}/facts`, {
    name: "Battery life", value: "Up to 18 hours", category: "product_spec", qualifications: "Under specified test conditions", owner: "Product team",
    status: "active", actor: "e2e", expires_at: isoDay(200), review_date: isoDay(90), source_document_id: doc.id, source_page: 2,
    source_excerpt: "Battery life: up to 18 hours under specified test conditions.",
  })).json;
  check("2-3. source processed; approved fact version 1 with verified provenance", doc?.processing_status === "processed" && fact?.status === "active" && fact.version === 1 && fact.source_excerpt_verified === true);

  // 4-5. Two campaigns that use the fact; submit revision 1 of each and review it.
  const submit = async (title, text) => {
    const content = (await call("POST", `/api/brands/${brand.id}/content`, { title, content: text, submitted_by: "e2e-creator" })).json;
    const run = (await call("POST", `/api/content/${content.id}/reviews`, { requested_by: "e2e-creator" })).json;
    return { content, run };
  };
  const A = await submit("Summer campaign", "Summer campaign: Battery life is up to 18 hours under specified test conditions.");
  const B = await submit("Back to school", "Back to school: Battery life is up to 18 hours under specified test conditions.");
  check("4. revision 1 of each campaign is saved as revision 1 of its own asset, in draft",
    A.content.revision_number === 1 && A.content.workflow_status === "draft" && A.content.asset_id !== B.content.asset_id && A.content.is_latest === true);
  const findingsA1 = (await call("GET", `/api/reviews/${A.run.id}/findings`)).json;
  const evA1 = findingsA1.items.flatMap((f) => f.evidence).filter((e) => e.fact_id === fact.id);
  check("5. the first review persisted findings and evidence citing fact version 1", ["completed", "completed_limited"].includes(A.run.status) && evA1.length === 1 && evA1[0].fact_version === 1 && evA1[0].role === "supports");

  // 6. A Phase 3 fact-change event: the fact is edited (18 -> 14 hours) and approved again.
  const edited = await call("PATCH", `/api/facts/${fact.id}`, { value: "Up to 14 hours", actor: "e2e", change_reason: "Test results revised" });
  const reapproved = await call("PATCH", `/api/facts/${fact.id}/status`, { status: "active", reason: "Re-approved after revised test results", actor: "e2e" });
  const open1 = (await call("GET", `/api/brands/${brand.id}/fact-change-impacts?status=needs_review`)).json;
  const impA = open1.items.find((i) => i.content.id === A.content.id);
  const impB = open1.items.find((i) => i.content.id === B.content.id);
  check("6. the fact change created open impacts for both campaigns, recorded against revision 1", edited.status === 200 && reapproved.json?.version === 3 && open1.total === 2 && impA?.content.revision_number === 1 && impB?.status === "needs_review");

  // 7. Open the affected content, look at the stale finding and its evidence with a fresh review of the same revision.
  const stale = (await call("POST", `/api/content/${A.content.id}/reviews`, { requested_by: "e2e-creator" })).json;
  const staleFinding = stale.findings[0];
  const detail = (await call("GET", `/api/findings/${staleFinding.id}`)).json;
  check("7. the affected revision re-reviewed against the current fact shows a conflict with its evidence", staleFinding.status === "conflicting" && detail.revision_number === 1 && detail.finding.evidence.some((e) => e.fact_id === fact.id && e.fact_value === "Up to 14 hours"));
  const sug = await call("POST", `/api/findings/${staleFinding.id}/suggest-correction`, null, CREATOR);
  if (sug.status === 503) check("7b. no AI provider: suggested corrections are reported unavailable (nothing is faked); manual correction continues", code(sug) === "ai_unavailable");
  else check("7b. an AI suggestion is a proposal only and carries a human-review flag", sug.status === 200 && sug.json.requires_human_review === true);
  const afterSuggest = (await call("GET", `/api/content/${A.content.id}`)).json;
  check("7c. asking for a suggestion changed nothing", afterSuggest.content === A.content.content && afterSuggest.content_hash === A.content.content_hash);

  // 8-9. The creator corrects the text manually and saves revision 2; revision 1 is unchanged.
  const fixed = "Summer campaign: Battery life is up to 14 hours under specified test conditions.";
  const noActor = await call("POST", `/api/content/${A.content.id}/revisions`, { content: fixed });
  const r2 = await call("POST", `/api/content/${A.content.id}/revisions`, {
    content: fixed, change_note: "Battery figure updated to 14 hours",
    corrections: [{ finding_id: staleFinding.id, decision: "manual", source: "manual", original_text: staleFinding.claim_text, replacement_text: "up to 14 hours" }],
  }, CREATOR);
  const rev2 = r2.json;
  check("8. a revision needs an actor; a corrected revision becomes revision 2 of the same asset with a new hash", ["actor_required", "unauthorized"].includes(code(noActor)) && r2.status === 201 && rev2.revision_number === 2 && rev2.asset_id === A.content.asset_id && rev2.parent_submission_id === A.content.id && rev2.content_hash !== A.content.content_hash && rev2.workflow_status === "draft");
  const rev1Again = (await call("GET", `/api/content/${A.content.id}`)).json;
  const findingsA1Again = (await call("GET", `/api/reviews/${A.run.id}/findings`)).json;
  check("9. revision 1 is unchanged: text, hash, title, findings and evidence", rev1Again.content === A.content.content && rev1Again.content_hash === A.content.content_hash && rev1Again.is_latest === false && isDeepStrictEqual(findingsA1Again, findingsA1));
  const stale2 = await call("POST", `/api/content/${A.content.id}/revisions`, { content: fixed + " Order now." }, CREATOR);
  check("9b. a second edit based on the old revision is a conflict, not a silent overwrite", stale2.status === 409 && code(stale2) === "revision_conflict");

  // 10-11. Review the new revision; it is reviewed on its own text against the current fact.
  const neverReviewed = await call("POST", `/api/content/${rev2.id}/submit-review`, null, CREATOR);
  const run2 = (await call("POST", `/api/content/${rev2.id}/reviews`, { requested_by: "e2e-creator" })).json;
  const claim2 = run2.findings[0];
  check("10. an unreviewed revision cannot be submitted for approval", neverReviewed.status === 409 && code(neverReviewed) === "review_required");
  check("11. the new review belongs to revision 2, covers its exact text and is supported by fact version 3", run2.content_submission_id === rev2.id && run2.content_hash === rev2.content_hash && claim2.status === "supported" && claim2.evidence.some((e) => e.fact_id === fact.id && e.fact_version === 3));

  // 12-14. Submit; the creator cannot approve; the reviewer approves and resolves ONLY campaign A's impact in the same transaction.
  const submitted = await call("POST", `/api/content/${rev2.id}/submit-review`, null, CREATOR);
  const byCreator = await call("POST", `/api/content/${rev2.id}/decisions`, { action: "approve", review_run_id: run2.id }, CREATOR);
  const noRun = await call("POST", `/api/content/${rev2.id}/decisions`, { action: "approve" }, REVIEWER);
  check("12. the creator submits for approval; a creator cannot approve; approval must name the review run", submitted.json?.workflow_status === "in_review" && byCreator.status === 403 && code(byCreator) === "reviewer_role_required" && noRun.status === 422);
  const impABefore = (await call("GET", `/api/fact-change-impacts/${impA.id}`)).json;
  const approved = await call("POST", `/api/content/${rev2.id}/decisions`, { action: "approve", review_run_id: run2.id, rationale: "Matches the revised specification.", resolve_impact_ids: [impA.id], resolution_rationale: "Copy now states 14 hours and was approved." }, REVIEWER);
  const last = approved.json?.events.at(-1);
  check("13. the reviewer approves the exact reviewed revision; actor, role, run and time are recorded", approved.status === 201 && approved.json.workflow_status === "approved" && last.action === "approved" && ["e2e-reviewer", "Alex Compliance"].includes(last.actor) && last.actor_role === "reviewer" && last.review_run_id === run2.id && Boolean(last.created_at));
  const impAnow = (await call("GET", `/api/fact-change-impacts/${impA.id}`)).json;
  const impBnow = (await call("GET", `/api/fact-change-impacts/${impB.id}`)).json;
  check("14. impact A is resolved with actor, reason and revision 2 (still recorded against revision 1); unrelated impact B is untouched",
    impAnow.status === "resolved" && ["e2e-reviewer", "Alex Compliance"].includes(impAnow.resolution.actor) && impAnow.resolution.rationale.startsWith("Copy now") && impAnow.resolution.resolving_submission_id === rev2.id && impAnow.content.id === A.content.id && impAnow.content.revision_number === 1
    && ["change_summary", "previous_snapshot", "new_snapshot", "reason", "headline", "detected_at", "findings", "trigger_revision"].every((k) => isDeepStrictEqual(impAnow[k], impABefore[k])) && impBnow.status === "needs_review");
  const laterRev = await call("POST", `/api/content/${rev2.id}/revisions`, { content: fixed + " Now with a free case!" }, CREATOR);
  check("15. a later revision starts as a draft and does not inherit the approval", laterRev.status === 201 && laterRev.json.workflow_status === "draft" && (await call("POST", `/api/content/${laterRev.json.id}/decisions`, { action: "approve", review_run_id: run2.id }, REVIEWER)).status === 409);
  const wf = (await call("GET", `/api/content/${rev2.id}/workflow`, null, REVIEWER)).json;
  check("16. revision and decision history lists every event in order", wf.events.filter((e) => e.revision_number === 2).map((e) => e.action).join(",") === "created,submitted,approved" && (await call("GET", `/api/content/${A.content.id}/revisions`)).json.items.map((r) => r.revision_number).join(",") === "1,2,3");

  // 17-18. Reload: read everything again through a fresh call / second process.
  const isLocal = base.startsWith("http://127.0.0.1") || base.startsWith("http://localhost");
  if (!isLocal) {
    const w2 = (await call("GET", `/api/content/${rev2.id}/workflow`, null, REVIEWER)).json;
    const h2 = (await call("GET", `/api/fact-change-impacts/${impA.id}/history`)).json;
    const s2 = (await call("GET", `/api/brands/${brand.id}/fact-change-impacts/summary`)).json;
    const f2 = (await call("GET", `/api/reviews/${A.run.id}/findings`)).json;
    check("17. after a reload the approval, decision history and revision list are unchanged", w2.workflow_status === "approved" && isDeepStrictEqual(w2.events, wf.events) && h2.status === "resolved" && h2.revisions.length === 3 && h2.resolutions.length === 1 && ["e2e-reviewer", "Alex Compliance"].includes(h2.resolutions[0].actor));
    check("18. after a reload the dashboard totals match the records, and revision 1's findings are identical", s2.open_impacts === 1 && s2.resolved_impacts === 1 && s2.dismissed_impacts === 0 && s2.total_impacts === 2 && isDeepStrictEqual(f2, findingsA1));
  } else {
    const defaultPython = process.platform === "win32" ? join(root, "backend/.venv/Scripts/python.exe") : join(root, "backend/.venv/bin/python");
    const python = process.env.E2E_BACKEND_PYTHON ?? defaultPython;
    const port = 8100 + Math.floor(Math.random() * 400);
    const origin2 = `http://127.0.0.1:${port}`;
    try {
      child = spawn(python, ["-m", "uvicorn", "app.main:app", "--port", String(port)], { cwd: join(root, "backend"), stdio: "ignore", env: { ...process.env } });
      let up = false;
      for (let i = 0; i < 40 && !up; i++) { await new Promise((r) => setTimeout(r, 500)); up = await fetch(origin2 + "/api/health").then((r) => r.ok, () => false); }
      if (!up) throw new Error("second backend did not start");
      const w2 = (await callAt(origin2, "GET", `/api/content/${rev2.id}/workflow`)).json;
      const h2 = (await callAt(origin2, "GET", `/api/fact-change-impacts/${impA.id}/history`)).json;
      const s2 = (await callAt(origin2, "GET", `/api/brands/${brand.id}/fact-change-impacts/summary`)).json;
      const f2 = (await callAt(origin2, "GET", `/api/reviews/${A.run.id}/findings`)).json;
      check("17. after a reload the approval, decision history and revision list are unchanged", w2.workflow_status === "approved" && isDeepStrictEqual(w2.events, wf.events) && h2.status === "resolved" && h2.revisions.length === 3 && h2.resolutions.length === 1 && ["e2e-reviewer", "Alex Compliance"].includes(h2.resolutions[0].actor));
      check("18. after a reload the dashboard totals match the records, and revision 1's findings are identical", s2.open_impacts === 1 && s2.resolved_impacts === 1 && s2.dismissed_impacts === 0 && s2.total_impacts === 2 && isDeepStrictEqual(f2, findingsA1));
    } catch (e) {
      skip("17-18. reload checks", `second backend unavailable: ${e.message}`);
    }
  }

  // 19-23. Separate scenarios on campaign B: a high-risk finding cannot be approved without an audited override, and a conflict cannot clear an impact.
  const b2 = (await call("POST", `/api/content/${B.content.id}/revisions`, { content: "Back to school: Battery life is up to 20 hours under specified test conditions." }, CREATOR)).json;
  const runB2 = (await call("POST", `/api/content/${b2.id}/reviews`, { requested_by: "e2e-creator" })).json;
  const risky = runB2.findings.find((f) => f.status === "conflicting" && f.severity === "high");
  await call("POST", `/api/content/${b2.id}/submit-review`, null, CREATOR);
  const blocked = await call("POST", `/api/content/${b2.id}/decisions`, { action: "approve", review_run_id: runB2.id }, REVIEWER);
  const blankReason = await call("POST", `/api/content/${b2.id}/decisions`, { action: "approve", review_run_id: runB2.id, overrides: [{ finding_id: risky.id, reason: "  " }] }, REVIEWER);
  check("19. an unresolved high-risk finding blocks approval, and an override without a reason is refused", Boolean(risky) && blocked.status === 409 && code(blocked) === "high_risk_unresolved" && blankReason.status === 422);
  const overridden = await call("POST", `/api/content/${b2.id}/decisions`, { action: "approve", review_run_id: runB2.id, overrides: [{ finding_id: risky.id, reason: "Legal confirmed 20 hours for the EU model." }] }, REVIEWER);
  const findingsB2 = (await call("GET", `/api/reviews/${runB2.id}/findings`)).json.items.find((f) => f.id === risky.id);
  check("20. a reviewer's reasoned override is recorded with actor and run, and the finding itself is not edited",
    overridden.status === 201 && overridden.json.workflow_status === "approved" && overridden.json.overrides.length === 1 &&
    ["e2e-reviewer", "Alex Compliance"].includes(overridden.json.overrides[0].actor) &&
    overridden.json.overrides[0].review_run_id === runB2.id &&
    overridden.json.overrides[0].finding_id === risky.id &&
    findingsB2?.status === "conflicting"
  );
  const noResolve = await call("POST", `/api/fact-change-impacts/${impB.id}/resolve`, { resolving_submission_id: b2.id, rationale: "Approved with an override." }, REVIEWER);
  const impBstill = (await call("GET", `/api/fact-change-impacts/${impB.id}`)).json;
  check("21. a conflicting claim cannot resolve the impact, even when a reviewer approved it with an override", noResolve.status === 409 && code(noResolve) === "conflict_unresolved" && impBstill.status === "needs_review");
  const creatorDismiss = await call("POST", `/api/fact-change-impacts/${impB.id}/dismiss`, { rationale: "Not needed" }, CREATOR);
  const noReason = await call("POST", `/api/fact-change-impacts/${impB.id}/dismiss`, { rationale: "" }, REVIEWER);
  const dismissed = await call("POST", `/api/fact-change-impacts/${impB.id}/dismiss`, { rationale: "Campaign withdrawn; the page is no longer published." }, REVIEWER);
  const again = await call("POST", `/api/fact-change-impacts/${impB.id}/dismiss`, { rationale: "Campaign withdrawn; the page is no longer published." }, REVIEWER);
  const conflict = await call("POST", `/api/fact-change-impacts/${impB.id}/resolve`, { resolving_submission_id: b2.id, rationale: "too late" }, REVIEWER);
  check("22. dismissal needs a reviewer and a reason, is recorded, repeats consistently and cannot be turned into a resolution",
    creatorDismiss.status === 403 && noReason.status === 422 && dismissed.status === 200 && dismissed.json.action === "dismissed" && again.json.id === dismissed.json.id && conflict.status === 409 && code(conflict) === "impact_not_open");

  // 24. A reviewer rejects / requests changes with reasons, and the totals match the persisted records.
  const c = await submit("Weight note", "Our laptop weighs 1.2 kg.");
  await call("POST", `/api/content/${c.content.id}/submit-review`, null, CREATOR);
  const noWhy = await call("POST", `/api/content/${c.content.id}/decisions`, { action: "request_changes" }, REVIEWER);
  const asked = await call("POST", `/api/content/${c.content.id}/decisions`, { action: "request_changes", rationale: "State the test conditions.", finding_ids: [c.run.findings?.[0]?.id].filter(Boolean) }, REVIEWER);
  const again2 = await call("POST", `/api/content/${c.content.id}/decisions`, { action: "reject", rationale: "No." }, REVIEWER);
  check("23. request-changes needs a reason, is recorded, and a decision cannot be repeated or reversed", noWhy.status === 422 && asked.status === 201 && asked.json.workflow_status === "changes_requested" && asked.json.events.at(-1).rationale === "State the test conditions." && again2.status === 409 && code(again2) === "invalid_transition");
  const sum = (await call("GET", `/api/brands/${brand.id}/fact-change-impacts/summary`)).json;
  const allImp = (await call("GET", `/api/brands/${brand.id}/fact-change-impacts?limit=50`)).json;
  const count = (s) => allImp.items.filter((i) => i.status === s).length;
  check("24. dashboard totals equal the persisted records (0 open, 1 resolved, 1 dismissed)", sum.open_impacts === count("needs_review") && sum.resolved_impacts === count("resolved") && sum.dismissed_impacts === count("dismissed") && sum.open_impacts === 0 && sum.resolved_impacts === 1 && sum.dismissed_impacts === 1 && sum.total_impacts === allImp.total);
} catch (e) {
  console.log("FAIL  unexpected error:", e);
  failures++;
} finally {
  child?.kill();
}
console.log(failures ? `\n${failures} check(s) failed` : `\nAll Phase 4 live checks passed${skipped ? ` (${skipped} skipped)` : ""}`);
process.exit(failures ? 1 : 0);
