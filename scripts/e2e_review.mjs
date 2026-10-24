// Live end-to-end check of Phase 2 (content review and ProofGraph) through the Next.js same-origin proxy.
// Uses the real backend and database and creates its own uniquely named brand, so it can be repeated.
// No external model is needed: with no LLM_API_KEY the backend runs its deterministic rules and labels the run "limited".
// Usage: node scripts/e2e_review.mjs [baseUrl]    (default http://localhost:3000)
import { readFileSync } from "node:fs";
import { join } from "node:path";

const base = process.argv[2] ?? "http://localhost:3000";
const root = new URL("..", import.meta.url).pathname;
let failures = 0;
const check = (name, ok, extra = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`);
  if (!ok) failures++;
};
const call = async (method, path, body) => {
  const isForm = body instanceof FormData;
  const res = await fetch(base + path, { method, headers: isForm || !body ? {} : { "Content-Type": "application/json" }, body: isForm ? body : body ? JSON.stringify(body) : undefined });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: res.status, json, text };
};
const isoDay = (offset) => new Date(Date.now() + offset * 864e5).toISOString().slice(0, 10);

// 1. A unique brand with a real source document and an approved fact citing page 2.
const brand = (await call("POST", "/api/brands", { name: `E2E Review ${Date.now()}` })).json;
check("1. create a unique test brand", Boolean(brand?.id));
const form = new FormData();
form.append("file", new File([readFileSync(join(root, "test-data/nova_product_specification.pdf"))], "nova_product_specification.pdf", { type: "application/pdf" }));
const doc = (await call("POST", `/api/brands/${brand.id}/documents`, form)).json;
const excerpt = "Battery life: up to 18 hours under specified test conditions.";
const fact = (await call("POST", `/api/brands/${brand.id}/facts`, {
  name: "Battery life", value: "Up to 18 hours", category: "product_spec", qualifications: "Under specified test conditions", owner: "Product team", status: "active", actor: "e2e",
  expires_at: isoDay(200), review_date: isoDay(90), source_document_id: doc.id, source_page: 2, source_excerpt: excerpt,
})).json;

// 2. Approved facts and source documents exist.
const facts = (await call("GET", `/api/brands/${brand.id}/facts?effective_state=current`)).json;
const docs = (await call("GET", `/api/brands/${brand.id}/documents`)).json;
check("2. approved fact and its processed source document exist", facts.total === 1 && facts.items[0].id === fact.id && docs.items[0].processing_status === "processed" && fact.source_excerpt_verified === true);

// 3. Submit a campaign with a supported, a conflicting and an unsupported comparative claim.
const supported = "Battery life is up to 18 hours under specified test conditions.";
const conflicting = "Battery life is 24 hours under specified test conditions.";
const unsupported = "Nova is the fastest laptop on the market.";
const campaign = `Meet Nova.\n${supported}\n${conflicting}\n${unsupported}\nWe are excited to share it with you.`;
const content = await call("POST", `/api/brands/${brand.id}/content`, { title: "E2E launch campaign", content: campaign, submitted_by: "e2e" });
check("3. submit the campaign", content.status === 201 && content.json.content === campaign && content.json.brand_id === brand.id);

// 4-5. Start the review and retrieve the run.
const created = await call("POST", `/api/content/${content.json.id}/reviews`, { requested_by: "e2e" });
check("4. start the review (run recorded)", created.status === 201 && ["completed", "completed_limited"].includes(created.json?.status), `status=${created.json?.status} mode=${created.json?.analysis_mode}`);
const run = (await call("GET", `/api/reviews/${created.json.id}`)).json;
check("5. retrieve the review run", run.id === created.json.id && run.content_submission_id === content.json.id && run.status === created.json.status);
if (run.analysis_mode === "limited") check("5b. limited mode is labelled with its limitation", run.limitations.length > 0 && run.provider_name === null);

// 6. Findings persisted.
const page = (await call("GET", `/api/reviews/${run.id}/findings`)).json;
const find = (frag) => page.items.find((f) => f.claim_text.includes(frag));
const [fSup, fConf, fUnsup] = [find("up to 18 hours"), find("24 hours"), find("fastest")];
check("6. exactly the three expected findings were persisted", page.total === 3 && fSup && fConf && fUnsup);
check("6b. statuses are supported / conflicting / unsupported", fSup?.status === "supported" && fConf?.status === "conflicting" && fUnsup?.status === "unsupported", `${fSup?.status}/${fConf?.status}/${fUnsup?.status}`);
check("6c. offsets point at the claim text in the saved content", page.items.every((f) => campaign.slice(f.start_offset, f.end_offset) === f.claim_text));
check("6d. counts match the findings", run.counts.supported === 1 && run.counts.conflicting === 1 && run.counts.unsupported === 1 && run.total_findings === 3);

// 7. Evidence for supported and conflicting claims points at the real fact, document, page and passage.
const page2 = (await call("GET", `/api/documents/${doc.id}/sections?page_number=2`)).json.items[0];
const real = (f, role) => {
  const e = f?.evidence?.[0];
  return f?.evidence?.length === 1 && e.role === role && e.fact_id === fact.id && e.source_document_id === doc.id && e.document_section_id === page2.id
    && e.source_page === 2 && e.excerpt_verified === true && page2.text.replace(/\s+/g, " ").includes(e.excerpt) && e.fact_version === fact.version;
};
check("7. supported claim cites the real fact, document, page 2 and verified passage", real(fSup, "supports"));
check("7b. conflicting claim cites the same real approved fact", real(fConf, "conflicts") && fConf.requires_human_review === true && fConf.severity === "high");

// 8. No fabricated citation for the unsupported claim.
check("8. unsupported claim has no citation", fUnsup.evidence.length === 0 && fUnsup.matched_fact_id === null && fUnsup.explanation.includes("No suitable approved evidence"));

// 9. Brand association.
check("9. review and content belong to the test brand", run.brand_id === brand.id && (await call("GET", `/api/content/${content.json.id}`)).json.brand_id === brand.id);
const other = (await call("POST", "/api/brands", { name: `E2E Other ${Date.now()}` })).json;
check("9b. another brand lists none of this content", (await call("GET", `/api/brands/${other.id}/content`)).json.total === 0);

// 10. Persistence on re-fetch, and a re-review is a separate run.
const again = (await call("GET", `/api/reviews/${run.id}/findings`)).json;
check("10. findings retrieved again are identical", JSON.stringify(again.items) === JSON.stringify(page.items));
const second = (await call("POST", `/api/content/${content.json.id}/reviews`, {})).json;
const history = (await call("GET", `/api/content/${content.json.id}/reviews`)).json;
check("10b. a second review is a separate run and the first is untouched", second.id !== run.id && history.length === 2 && history[1].id === run.id && history[1].counts.conflicting === 1);

// The same data is what the review page shows.
const html = await (await fetch(base + "/review")).text();
check("11. /review page is served by the frontend", html.includes("Review content"));

console.log(failures ? `\n${failures} check(s) failed` : "\nAll Phase 2 live checks passed");
process.exit(failures ? 1 : 0);
