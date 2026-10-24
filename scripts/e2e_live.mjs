// Live end-to-end check through the Next.js server (same-origin /api proxy) against a running backend.
// Usage: node scripts/e2e_live.mjs [baseUrl]    (default http://localhost:3000)
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const base = process.argv[2] ?? "http://localhost:3000";
const root = fileURLToPath(new URL("..", import.meta.url));
let failures = 0;
const check = (name, ok, extra = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`);
  if (!ok) failures++;
};
const call = async (method, path, body, headers = {}) => {
  const isForm = body instanceof FormData;
  const res = await fetch(base + path, { method, headers: isForm || !body ? headers : { "Content-Type": "application/json", ...headers }, body: isForm ? body : body ? JSON.stringify(body) : undefined });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: res.status, json, text };
};

const health = await call("GET", "/api/health");
check("proxy reaches backend health", health.status === 200 && health.json.status === "ok");
check("database health through proxy", (await call("GET", "/api/health/db")).json?.database === "connected");
for (const page of ["/", "/knowledge", "/facts", "/review"]) {
  const r = await fetch(base + page, { redirect: "follow" });
  const html = await r.text();
  check(`page ${page} renders`, r.status === 200 && html.includes("BrandPR"));
}

const unique = `E2E Brand ${Date.now()}`;
const brand = (await call("POST", "/api/brands", { name: unique })).json;
check("create brand", Boolean(brand?.id));

const pdf = readFileSync(join(root, "test-data/nova_product_specification.pdf"));
const form = new FormData();
form.append("file", new File([pdf], "nova_product_specification.pdf", { type: "application/pdf" }));
const up = await call("POST", `/api/brands/${brand.id}/documents`, form);
check("upload PDF", up.status === 201 && up.json.processing_status === "processed" && up.json.page_count === 3);
const sections = (await call("GET", `/api/documents/${up.json.id}/sections?page_number=2`)).json;
check("page 2 text has battery statement", sections.items[0].text.includes("Battery life: up to 18 hours"));

const dupForm = new FormData();
dupForm.append("file", new File([pdf], "copy.pdf", { type: "application/pdf" }));
check("duplicate upload rejected (409)", (await call("POST", `/api/brands/${brand.id}/documents`, dupForm)).status === 409);
const badForm = new FormData();
badForm.append("file", new File([new Uint8Array([77, 90, 144, 0])], "tool.exe"));
check("unsupported type rejected (415)", (await call("POST", `/api/brands/${brand.id}/documents`, badForm)).status === 415);
const corruptForm = new FormData();
corruptForm.append("file", new File([readFileSync(join(root, "test-data/corrupt.pdf"))], "corrupt.pdf", { type: "application/pdf" }));
const corrupt = await call("POST", `/api/brands/${brand.id}/documents`, corruptForm);
check("corrupt PDF recorded as failed", corrupt.status === 201 && corrupt.json.processing_status === "failed" && corrupt.json.error_message);

const fact = (await call("POST", `/api/brands/${brand.id}/facts`, {
  name: "Battery life", value: "Up to 18 hours", category: "product_spec", qualifications: "Under specified test conditions",
  source_document_id: up.json.id, source_page: 2, source_excerpt: "Battery life: up to 18 hours", expires_at: "2999-01-01", status: "active", actor: "e2e",
})).json;
check("create approved fact with page reference", fact.status === "active" && fact.effective_state === "current" && fact.source_excerpt_verified === true && fact.source.title);
const edited = (await call("PATCH", `/api/facts/${fact.id}`, { value: "Up to 20 hours", expected_version: fact.version })).json;
check("editing wording returns fact to proposed", edited.status === "proposed" && edited.value === "Up to 20 hours" && edited.version === 2);
const approved = (await call("PATCH", `/api/facts/${fact.id}/status`, { status: "active", actor: "e2e" })).json;
check("explicit re-approval", approved.status === "active" && approved.approved_by === "e2e");
const list = (await call("GET", `/api/brands/${brand.id}/facts?effective_state=current`)).json;
check("filtered list returns the fact", list.total === 1);
const err = await call("POST", `/api/brands/${brand.id}/facts`, { name: "", value: "x" });
check("structured validation error", err.status === 422 && err.json.error.code === "validation_error");

const nova = (await call("GET", "/api/brands")).json.items.find((b) => b.name === "Nova Systems");
if (nova) {
  const s = (await call("GET", `/api/brands/${nova.id}/facts/summary`)).json;
  check("seeded Nova Systems facts present", s.total >= 5, JSON.stringify(s.by_effective_state));
}

// Secret scan of the production bundle: nothing server-only may be shipped to the browser.
const walk = (dir) => readdirSync(dir).flatMap((f) => { const p = join(dir, f); return statSync(p).isDirectory() ? walk(p) : [p]; });
try {
  const files = walk(join(root, "frontend/.next/static")).filter((f) => /\.(js|css|html)$/.test(f));
  const needles = ["brandpr_dev_password", "DATABASE_URL", "postgresql+psycopg", "LLM_API_KEY", "BACKEND_URL"];
  const leaked = files.flatMap((f) => needles.filter((n) => readFileSync(f, "utf8").includes(n)).map((n) => `${n} in ${f}`));
  check("no server-side configuration in the browser bundle", leaked.length === 0, leaked.join("; "));
} catch (e) {
  check("bundle scan (run `npm run build` first)", false, String(e));
}

console.log(failures ? `\n${failures} check(s) failed` : "\nAll live checks passed");
process.exit(failures ? 1 : 0);
