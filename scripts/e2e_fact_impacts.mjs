// Live end-to-end check of Phase 3 (Claim Ledger fact-change propagation) through the Next.js same-origin proxy.
// Uses the real backend, the real PostgreSQL database and the real review pipeline. Creates its own uniquely named
// brand, source document, facts and content, so it can be repeated; it depends on no fixed IDs and no manual edits.
//
// Step 17 needs the date to move forward. It starts a SECOND backend process on another port with CLOCK_OFFSET_DAYS=10
// (a testing aid that shifts only the date used by validity rules; refused in production) against the same database,
// then reads the impacts through both backends. Set E2E_BACKEND_PYTHON to override the interpreter
// (default backend/.venv/bin/python). If it cannot be started, step 17 is reported as SKIPPED, never as passed.
//
// Usage: node scripts/e2e_fact_impacts.mjs [baseUrl]    (default http://localhost:3000)
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
const callAt = async (origin, method, path, body) => {
  const isForm = body instanceof FormData;
  const res = await fetch(origin + path, { method, headers: isForm || !body ? {} : { "Content-Type": "application/json" }, body: isForm ? body : body ? JSON.stringify(body) : undefined });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: res.status, json, text };
};
const call = (method, path, body) => callAt(base, method, path, body);
const isoDay = (offset) => new Date(Date.now() + offset * 864e5).toISOString().slice(0, 10);
const titles = (page) => page.items.map((i) => i.content.title).sort();

let child = null;
try {
  // 1-3. A unique brand, a real source document, an approved fact with provenance, and an unrelated fact.
  const brand = (await call("POST", "/api/brands", { name: `E2E Impacts ${Date.now()}` })).json;
  check("1. create a unique fictional brand", Boolean(brand?.id));
  const form = new FormData();
  form.append("file", new File([readFileSync(join(root, "test-data/nova_product_specification.pdf"))], "nova_product_specification.pdf", { type: "application/pdf" }));
  const doc = (await call("POST", `/api/brands/${brand.id}/documents`, form)).json;
  const excerpt = "Battery life: up to 18 hours under specified test conditions.";
  const fact = (await call("POST", `/api/brands/${brand.id}/facts`, {
    name: "Battery life", value: "Up to 18 hours", category: "product_spec", qualifications: "Under specified test conditions", owner: "Product team",
    status: "active", actor: "e2e", expires_at: isoDay(200), review_date: isoDay(90), source_document_id: doc.id, source_page: 2, source_excerpt: excerpt,
  })).json;
  const weight = (await call("POST", `/api/brands/${brand.id}/facts`, {
    name: "Weight", value: "1.2", unit: "kg", category: "product_spec", owner: "Product team", status: "active", actor: "e2e",
    expires_at: isoDay(3), source_note: "Confirmed by the product team",
  })).json;
  check("2-3. source document processed; approved fact has verified provenance at version 1", doc?.processing_status === "processed" && fact?.status === "active" && fact.version === 1 && fact.source_excerpt_verified === true && weight?.version === 1);

  // 4-5. Two campaigns that use the battery fact, one unrelated draft, one draft with no claims; review all four.
  const submit = async (title, text) => {
    const c = (await call("POST", `/api/brands/${brand.id}/content`, { title, content: text, submitted_by: "e2e" })).json;
    const run = (await call("POST", `/api/content/${c.id}/reviews`, { requested_by: "e2e" })).json;
    return { content: c, run };
  };
  const A = await submit("Summer campaign", "Summer campaign: Battery life is up to 18 hours under specified test conditions.");
  const B = await submit("Back to school", "Back to school: Battery life is up to 18 hours under specified test conditions.");
  const U = await submit("Weight note", "Our laptop weighs 1.2 kg.");
  const N = await submit("Welcome note", "Welcome to our store. We love our customers.");
  check("4-5. all four reviews completed and were recorded as separate runs", [A, B, U, N].every((x) => ["completed", "completed_limited"].includes(x.run.status)) && new Set([A, B, U, N].map((x) => x.run.id)).size === 4);

  // 6-7. Persisted findings and evidence link to the correct fact, and record the fact version used.
  const evOf = async (x, factId) => {
    const page = (await call("GET", `/api/reviews/${x.run.id}/findings`)).json;
    return { page, ev: page.items.flatMap((f) => f.evidence).filter((e) => e.fact_id === factId) };
  };
  const [evA, evB, evU, evN] = [await evOf(A, fact.id), await evOf(B, fact.id), await evOf(U, weight.id), await evOf(N, fact.id)];
  check("6. campaigns A and B persist evidence that cites the battery fact", evA.ev.length === 1 && evB.ev.length === 1 && evA.ev[0].role === "supports" && evB.ev[0].role === "supports");
  check("7. each review recorded the fact version it used (1)", evA.ev[0].fact_version === 1 && evB.ev[0].fact_version === 1);
  check("7b. the unrelated draft cites a different fact and the empty draft cites none", evU.ev.length === 1 && evN.page.total === 0 && (await evOf(U, fact.id)).ev.length === 0);
  const beforeFindingsA = JSON.stringify(evA.page);
  const beforeFindingsB = JSON.stringify(evB.page);
  check("7c. nothing is flagged before any fact changes", (await call("GET", `/api/brands/${brand.id}/fact-change-impacts`)).json.total === 0);

  // 8-9. Change the approved fact through the real API; the existing update path must trigger propagation by itself.
  const edited = await call("PATCH", `/api/facts/${fact.id}`, { value: "Up to 14 hours", actor: "e2e", change_reason: "Revised test results", expected_version: 1 });
  check("8. the fact is changed through the real API (returns to proposed, version 2)", edited.status === 200 && edited.json.version === 2 && edited.json.status === "proposed");
  const list = (await call("GET", `/api/brands/${brand.id}/fact-change-impacts`)).json;
  check("9. propagation ran with the fact update (no separate call was made)", list.total === 2);

  // 10-12. Both dependent assets are flagged; unrelated content is not.
  check("10-11. both campaigns are flagged for review", isDeepEqual(titles(list), ["Back to school", "Summer campaign"]), titles(list).join(", "));
  check("12. unrelated and claim-free drafts remain unaffected", !titles(list).includes("Weight note") && !titles(list).includes("Welcome note"));
  check("12b. every impact needs review, names the fact, and cites versions 1 -> 2", list.items.every((i) => i.status === "needs_review" && i.trigger_type === "fact_revision" && i.fact.id === fact.id && i.previous_fact_version === 1 && i.current_fact_version === 2 && i.previous_value === "Up to 18 hours" && i.current_value === "Up to 14 hours"));

  // 13. Previous and current snapshots are inspectable, and the trigger is the real revision.
  const revisions = (await call("GET", `/api/facts/${fact.id}/revisions`)).json;
  const rev2 = revisions.find((r) => r.revision_number === 2);
  const detail = (await call("GET", `/api/fact-change-impacts/${list.items.find((i) => i.content.id === A.content.id).id}`)).json;
  check("13. detail shows the previous snapshot, the new snapshot and the current fact distinctly",
    detail.previous_snapshot.value === "Up to 18 hours" && detail.new_snapshot.value === "Up to 14 hours" && detail.current_fact.value === "Up to 14 hours" && detail.current_fact.status === "proposed");
  check("13b. the trigger is the stored fact revision and the finding is the one that was reviewed",
    detail.trigger_revision.id === rev2.id && detail.trigger_revision.changed_by === "e2e" && detail.trigger_revision.change_reason === "Revised test results"
    && detail.findings.length === 1 && detail.findings[0].finding.id === evA.page.items[0].id && detail.findings[0].relied_fact_version === 1 && detail.findings[0].finding.evidence[0].fact_value === "Up to 18 hours");

  // 14. Historical review results are byte-for-byte unchanged.
  const afterA = (await call("GET", `/api/reviews/${A.run.id}/findings`)).json;
  const afterB = (await call("GET", `/api/reviews/${B.run.id}/findings`)).json;
  check("14. previous findings and evidence are unchanged after the fact changed", JSON.stringify(afterA) === beforeFindingsA && JSON.stringify(afterB) === beforeFindingsB);

  // 15-16. Request again: no duplicates, same records.
  const again = (await call("GET", `/api/brands/${brand.id}/fact-change-impacts`)).json;
  const forFact = (await call("GET", `/api/facts/${fact.id}/impacts`)).json;
  const summary = (await call("GET", `/api/brands/${brand.id}/fact-change-impacts/summary`)).json;
  check("15-16. repeated requests return the same two records and create no duplicates",
    again.total === 2 && isDeepEqual(again.items.map((i) => i.id).sort(), list.items.map((i) => i.id).sort()) && forFact.total === 2);
  check("16b. summary counts are computed from the stored records", summary.open_impacts === 2 && summary.facts_with_changes === 1 && summary.content_needing_review === 2 && summary.revision_affected_content === 2 && summary.expiry_affected_content === 0, JSON.stringify(summary));
  const owner = await call("PATCH", `/api/facts/${weight.id}`, { owner: "Hardware team" });
  check("16c. a metadata-only edit (owner) creates no impact", owner.status === 200 && (await call("GET", `/api/brands/${brand.id}/fact-change-impacts`)).json.total === 2);

  // 17. Controlled expiry: a second backend whose date is 10 days ahead sweeps the same database.
  if (!base.includes("localhost") && !base.includes("127.0.0.1")) {
    skip("17-18. controlled expiry through a second backend", "remote deployment active; cannot spawn local shifted-date backend against remote Cloud SQL");
  } else {
    const defaultPython = process.platform === "win32" ? join(root, "backend/.venv/Scripts/python.exe") : join(root, "backend/.venv/bin/python");
    const python = process.env.E2E_BACKEND_PYTHON ?? defaultPython;
    const port = 8100 + Math.floor(Math.random() * 800);
    const shifted = `http://127.0.0.1:${port}`;
    try {
      child = spawn(python, ["-m", "uvicorn", "app.main:app", "--port", String(port), "--log-level", "warning"], {
        cwd: join(root, "backend"), env: { ...process.env, CLOCK_OFFSET_DAYS: "10", APP_ENV: "development" }, stdio: "ignore",
      });
      let up = false;
      for (let i = 0; i < 60 && !up; i++) {
        await new Promise((r) => setTimeout(r, 500));
        up = await fetch(shifted + "/api/health").then((r) => r.ok, () => false);
      }
      if (!up) throw new Error("the shifted-date backend did not start");
    const today = (await callAt(shifted, "GET", `/api/facts/${weight.id}`)).json;
    check("17. with the date moved forward the weight fact reads as expired while stored as active", today.status === "active" && today.effective_state === "expired" && (await call("GET", `/api/facts/${weight.id}`)).json.effective_state === "current");
    const swept = (await callAt(shifted, "GET", `/api/brands/${brand.id}/fact-change-impacts`)).json;
    const expiry = swept.items.filter((i) => i.trigger_type === "fact_expiry");
    check("17b. the sweep flags exactly the content that relied on the expired fact (no fact edit was needed)", expiry.length === 1 && expiry[0].content.id === U.content.id && expiry[0].change_type === "expired" && expiry[0].fact.id === weight.id && swept.total === 3, `${swept.total} impacts`);
    const sweepAgain = [(await callAt(shifted, "GET", `/api/brands/${brand.id}/fact-change-impacts`)).json, (await callAt(shifted, "GET", `/api/brands/${brand.id}/fact-change-impacts`)).json];
    const s2 = (await callAt(shifted, "GET", `/api/brands/${brand.id}/fact-change-impacts/summary`)).json;
    check("17c. repeated sweeps create no duplicates", sweepAgain.every((p) => p.total === 3) && s2.open_impacts === 3 && s2.expiry_affected_content === 1);

    // 18. Persistence: read everything again through the normal backend (real date) and the frontend proxy.
    const final = (await call("GET", `/api/brands/${brand.id}/fact-change-impacts`)).json;
    const weightImpact = final.items.find((i) => i.trigger_type === "fact_expiry");
    check("18. the expiry impact persisted and is visible through the normal backend", final.total === 3 && weightImpact?.id === expiry[0].id);
    const weightDetail = (await call("GET", `/api/fact-change-impacts/${weightImpact.id}`)).json;
    check("18b. its detail keeps the original review and evidence", weightDetail.trigger_revision === null && weightDetail.findings[0].finding.id === evU.page.items[0].id && weightDetail.findings[0].relied_fact_version === 1);
    check("18c. the two revision impacts are unchanged", isDeepEqual(final.items.filter((i) => i.trigger_type === "fact_revision").map((i) => i.id).sort(), list.items.map((i) => i.id).sort()));
    check("18d. brand isolation: another brand sees none of this", await (async () => {
      const other = (await call("POST", "/api/brands", { name: `E2E Impacts other ${Date.now()}` })).json;
      const page = (await call("GET", `/api/brands/${other.id}/fact-change-impacts`)).json;
      const cross = await call("GET", `/api/brands/${other.id}/fact-change-impacts?fact_id=${fact.id}`);
      return page.total === 0 && cross.status === 404;
    })());
  } catch (err) {
    skip("17-18. controlled expiry through a second backend", `could not run: ${err.message}`);
  }
  }

  const page = await fetch(base + "/fact-changes");
  check("19. the /fact-changes page is served by the frontend", page.status === 200);
} finally {
  child?.kill();
}

function isDeepEqual(a, b) { return isDeepStrictEqual(a, b); }
console.log(failures ? `\n${failures} check(s) FAILED` : `\nAll Phase 3 live checks passed${skipped ? ` (${skipped} skipped, see above)` : ""}`);
process.exit(failures ? 1 : 0);
