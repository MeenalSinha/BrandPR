import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ContentItem } from "@/types/api";

import { BrandProvider, ToastProvider } from "@/components/providers";
import { AppShell } from "@/components/AppShell";
import { FactChangesView } from "@/components/FactChangesView";
import { FactsView } from "@/components/FactsView";
import { KnowledgeView } from "@/components/KnowledgeView";
import { ReviewView } from "@/components/ReviewView";
import { splitByExcerpt } from "@/lib/format";
import { FakeApi } from "./fakeApi";

let api: FakeApi;
beforeEach(() => {
  api = new FakeApi().install();
});

function renderPage(ui: React.ReactElement) {
  return render(<ToastProvider><BrandProvider>{ui}</BrandProvider></ToastProvider>);
}
const file = (name: string, type = "application/pdf") => new File(["content"], name, { type });

describe("Brand Knowledge page", () => {
  it("P1-25: loads the brand and its documents from the backend", async () => {
    const b = api.addBrand();
    api.addDoc(b.id, { title: "Nova product specification" });
    renderPage(<KnowledgeView />);
    expect(await screen.findByText("Nova product specification")).toBeInTheDocument();
    expect(screen.getByTestId("brand-name")).toHaveTextContent("Nova Systems");
    expect(api.calls.some((c) => c.url.startsWith(`/api/brands/${b.id}/documents`))).toBe(true);
    expect(screen.getByTestId("processing-badge")).toHaveTextContent("Processed");
  });

  it("P1-26: uploading a supported document shows its processing result and lists it", async () => {
    const b = api.addBrand();
    api.addDoc(b.id, { title: "Existing" });
    renderPage(<KnowledgeView />);
    await screen.findByText("Existing");
    await userEvent.upload(screen.getByLabelText("Choose file"), file("guide.pdf"));
    expect(screen.getByTestId("chosen-file")).toHaveTextContent("guide.pdf");
    await userEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(await screen.findByText(/was read successfully \(3 pages\)/)).toBeInTheDocument();
    expect(await screen.findByText("guide.pdf", { selector: "button" })).toBeInTheDocument();
    expect(api.calls.some((c) => c.method === "POST" && c.url.endsWith("/documents"))).toBe(true);
  });

  it("P1-26b: a document that fails processing is reported as failed, not as a success", async () => {
    const b = api.addBrand();
    api.uploadResult = { processing_status: "failed", error_message: "The PDF could not be opened. It may be corrupt or truncated.", page_count: null, section_count: 0, char_count: 0, processed_at: null };
    renderPage(<KnowledgeView />);
    await screen.findByText("No source documents yet");
    await userEvent.upload(screen.getByLabelText("Choose file"), file("broken.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Upload document" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("could not be processed");
    expect(alert).toHaveTextContent("corrupt or truncated");
    expect(screen.queryByText(/read successfully/)).not.toBeInTheDocument();
    expect((await screen.findByTestId("processing-badge")).textContent).toBe("Failed");
    expect(b.id).toBeTruthy();
  });

  it("P1-29: an upload rejected by the server shows the server's message", async () => {
    api.addBrand();
    renderPage(<KnowledgeView />);
    await screen.findByText("No source documents yet");
    // Browsers can bypass the picker's accept filter (drag and drop), so the server is the real authority.
    await userEvent.setup({ applyAccept: false }).upload(screen.getByLabelText("Choose file"), file("tool.exe", "application/x-msdownload"));
    api.failNext = { status: 415, code: "unsupported_file_type", message: "Unsupported file type. Upload a PDF, plain text (.txt) or CSV file." };
    await userEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unsupported file type");
  });

  it("P1-30: an empty brand shows a useful empty state", async () => {
    api.addBrand("Empty Co");
    renderPage(<KnowledgeView />);
    expect(await screen.findByText("No source documents yet")).toBeInTheDocument();
    expect(screen.getByText(/does not approve anything/)).toBeInTheDocument();
  });

  it("opens a document and shows its extracted text", async () => {
    const b = api.addBrand();
    api.addDoc(b.id);
    renderPage(<KnowledgeView />);
    await userEvent.click(await screen.findByRole("button", { name: "Inspect Nova spec" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/Page 1 text/)).toBeInTheDocument();
    expect(within(dialog).getByText("Page 1 of 3")).toBeInTheDocument();
  });
});

describe("Approved Facts page", () => {
  it("lists facts with state, validity and source", async () => {
    const b = api.addBrand();
    const d = api.addDoc(b.id);
    api.addFact(b.id, { source_document_id: d.id, source_page: 2, provenance: "document", source: { document_id: d.id, title: d.title, filename: d.filename, source_type: "pdf", processing_status: "processed", page_count: 3, archived: false } });
    api.addFact(b.id, { name: "Old claim", value: "Up to 14 hours", status: "expired", effective_state: "expired", expires_at: "2026-01-01" });
    api.addFact(b.id, { name: "Draft claim", value: "Fast", status: "proposed", effective_state: "unapproved", expires_at: null });
    renderPage(<FactsView />);
    const rows = await screen.findAllByTestId("fact-row");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("Nova spec, page 2")).toBeInTheDocument();
    const badges = screen.getAllByTestId("effective-badge").map((x) => x.textContent);
    expect(badges).toEqual(["Current", "Expired", "Unapproved"]);
    expect(within(rows[2]).getByText("No expiry date recorded")).toBeInTheDocument();
  });

  it("P1-27: a new fact appears in the list after saving, without a manual refresh", async () => {
    const b = api.addBrand();
    renderPage(<FactsView />);
    await userEvent.click(await screen.findByRole("button", { name: "Create the first fact" }));
    await userEvent.type(screen.getByLabelText("Name"), "Performance improvement");
    await userEvent.type(screen.getByLabelText("Approved value"), "25");
    await userEvent.type(screen.getByLabelText("Unit"), "%");
    await userEvent.type(screen.getByLabelText("How was this verified?"), "Benchmark report NS-BM-4");
    await userEvent.click(screen.getByRole("button", { name: "Save fact" }));
    expect(await screen.findByText("Performance improvement", { selector: "button" })).toBeInTheDocument();
    const post = api.calls.find((c) => c.method === "POST" && c.url === `/api/brands/${b.id}/facts`);
    expect(post?.body).toMatchObject({ name: "Performance improvement", value: "25", unit: "%", status: "proposed", source_note: "Benchmark report NS-BM-4" });
    expect(await screen.findByText(/saved as proposed/)).toBeInTheDocument();
  });

  it("validates required fields before calling the backend", async () => {
    api.addBrand();
    renderPage(<FactsView />);
    await userEvent.click(await screen.findByRole("button", { name: "Create the first fact" }));
    await userEvent.click(screen.getByRole("button", { name: "Save fact" }));
    expect(await screen.findByText(/Enter the fact name/)).toBeInTheDocument();
    expect(screen.getByText(/Enter the approved value/)).toBeInTheDocument();
    expect(screen.getByText(/Describe how this was verified/)).toBeInTheDocument();
    expect(api.calls.some((c) => c.method === "POST" && c.url.endsWith("/facts"))).toBe(false);
  });

  it("maps server validation errors onto the right field", async () => {
    api.addBrand();
    renderPage(<FactsView />);
    await userEvent.click(await screen.findByRole("button", { name: "Create the first fact" }));
    await userEvent.type(screen.getByLabelText("Name"), "Battery life");
    await userEvent.type(screen.getByLabelText("Approved value"), "18");
    await userEvent.type(screen.getByLabelText("How was this verified?"), "Team");
    api.failNext = { status: 422, code: "validation_error", message: "The fact could not be saved.", details: [{ field: "source_note", message: "Server says: describe the source." }] };
    await userEvent.click(screen.getByRole("button", { name: "Save fact" }));
    expect(await screen.findByText("Server says: describe the source.")).toBeInTheDocument();
    expect(screen.getByLabelText("How was this verified?")).toHaveAttribute("aria-invalid", "true");
  });

  it("P1-28: editing a fact shows the updated value after saving", async () => {
    const b = api.addBrand();
    const f = api.addFact(b.id);
    renderPage(<FactsView />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit Battery life" }));
    expect(screen.queryByText(/returns it to proposed/)).not.toBeInTheDocument();
    const value = screen.getByLabelText("Approved value");
    await userEvent.clear(value);
    await userEvent.type(value, "Up to 20 hours");
    expect(screen.getByText(/returns it to proposed/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Up to 20 hours", { selector: "[data-testid=drawer-value]" })).toBeInTheDocument();
    const patch = api.calls.find((c) => c.method === "PATCH" && c.url === `/api/facts/${f.id}`);
    expect(patch?.body).toMatchObject({ value: "Up to 20 hours", expected_version: 1 });
    expect(Object.keys(patch?.body as object)).not.toContain("name");
  });

  it("P1-29c: a failed facts request shows the server message and can be retried", async () => {
    const b = api.addBrand();
    api.addFact(b.id);
    renderPage(<FactsView />);
    await screen.findAllByTestId("fact-row");
    api.failNext = { status: 500, code: "internal_error", message: "An unexpected error occurred." };
    await userEvent.type(screen.getByLabelText("Search facts"), "bat");
    expect(await screen.findByRole("alert")).toHaveTextContent("An unexpected error occurred.");
    expect(screen.queryAllByTestId("fact-row")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findAllByTestId("fact-row")).toHaveLength(1);
  });

  it("P1-29d: an unreachable backend is reported plainly", async () => {
    const b = api.addBrand();
    api.addFact(b.id);
    renderPage(<FactsView />);
    await screen.findAllByTestId("fact-row");
    api.failNext = "network";
    await userEvent.type(screen.getByLabelText("Search facts"), "bat");
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the BrandPR API");
  });

  it("P1-30b: an empty brand shows the facts empty state with next steps", async () => {
    api.addBrand("Empty Co");
    renderPage(<FactsView />);
    expect(await screen.findByText("No approved facts yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload a source document" })).toHaveAttribute("href", "/knowledge");
  });

  it("approving a proposed fact is an explicit action that calls the backend", async () => {
    const b = api.addBrand();
    api.addFact(b.id, { name: "Draft", status: "proposed", effective_state: "unapproved" });
    renderPage(<FactsView />);
    await userEvent.click(await screen.findByRole("button", { name: "Details for Draft" }));
    const drawer = await screen.findByRole("dialog");
    await userEvent.click(within(drawer).getByRole("button", { name: "Approve fact" }));
    await userEvent.click(within(drawer).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(api.calls.some((c) => (c.url.endsWith("/status") || c.url.endsWith("/approve")))).toBe(true));
    expect(await screen.findByText(/is now approved/)).toBeInTheDocument();
  });

  it("requires a reason to mark a fact expired", async () => {
    const b = api.addBrand();
    api.addFact(b.id);
    renderPage(<FactsView />);
    await userEvent.click(await screen.findByRole("button", { name: "Details for Battery life" }));
    const drawer = await screen.findByRole("dialog");
    await userEvent.click(within(drawer).getByRole("button", { name: "Mark expired" }));
    await userEvent.click(within(drawer).getByRole("button", { name: "Confirm" }));
    expect(await within(drawer).findByRole("alert")).toHaveTextContent("Give a reason");
    expect(api.calls.some((c) => c.url.endsWith("/status"))).toBe(false);
  });

  it("shows the supporting passage highlighted in the source", async () => {
    const b = api.addBrand();
    const d = api.addDoc(b.id);
    api.addFact(b.id, { source_document_id: d.id, source_page: 2, source_excerpt: "Battery life: up to 18 hours", provenance: "document", source: { document_id: d.id, title: d.title, filename: d.filename, source_type: "pdf", processing_status: "processed", page_count: 3, archived: false } });
    renderPage(<FactsView />);
    await userEvent.click(await screen.findByRole("button", { name: "Details for Battery life" }));
    const mark = await screen.findByTestId("excerpt-mark");
    expect(mark).toHaveTextContent("Battery life: up to 18 hours");
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
  });
});

describe("helpers", () => {
  it("splitByExcerpt ignores whitespace and case differences", () => {
    const parts = splitByExcerpt("Battery  life:\nup to 18 HOURS here", "battery life: up to 18 hours");
    expect(parts.filter((p) => p.hit)).toHaveLength(1);
    expect(parts.map((p) => p.text).join("")).toBe("Battery  life:\nup to 18 HOURS here");
    expect(splitByExcerpt("nothing here", "absent text")).toEqual([{ text: "nothing here", hit: false }]);
  });
});

void vi;


// ====================================================================== Phase 2: ProofGraph review page
const DRAFT = "Battery life is up to 18 hours under specified test conditions. Battery life is 24 hours. Nova is the fastest laptop.";
const C1 = "Battery life is up to 18 hours under specified test conditions.";
const C2 = "Battery life is 24 hours.";
const C3 = "Nova is the fastest laptop.";

/** A backend response shaped exactly like the real one: three claims with different outcomes and real-looking evidence. */
function seedReview(a: FakeApi) {
  const b = a.addBrand();
  const doc = a.addDoc(b.id, { title: "Nova product specification v3.2" });
  const fact = a.addFact(b.id);
  a.reviewResponder = (item) => {
    const rid = "pending";
    const evidence = (role: "supports" | "conflicts") => a.makeEvidence({
      role, fact_id: fact.id, source_document_id: doc.id, source_title: doc.title, source_page: 2,
      excerpt: "Battery life: up to 18 hours under specified test conditions.", excerpt_verified: true,
    });
    return {
      run: {},
      findings: [
        a.makeFinding(rid, item.content, C1, { claim_index: 0, status: "supported", evidence: [evidence("supports")], explanation: "Approved fact supports this claim." }),
        a.makeFinding(rid, item.content, C2, { claim_index: 1, status: "conflicting", severity: "high", requires_human_review: true, evidence: [evidence("conflicts")],
          explanation: "The claim states 24 hours, but the approved value is up to 18 hours.", recommended_action: "Correct the figure." }),
        a.makeFinding(rid, item.content, C3, { claim_index: 2, claim_category: "comparative", status: "unsupported", severity: "high", requires_human_review: true, evidence: [],
          explanation: "No suitable approved evidence was found for this claim." }),
      ],
    };
  };
  return { b, doc, fact };
}

async function submitDraft(text = DRAFT, title = "Spring campaign") {
  await screen.findByTestId("review-brand");
  await userEvent.type(screen.getByLabelText("Title"), title);
  await userEvent.click(screen.getByLabelText("Content to review"));
  await userEvent.paste(text);
  await userEvent.click(screen.getByRole("button", { name: "Review content" }));
}

describe("Review content page (ProofGraph)", () => {
  it("P2-33: loads inside the application shell with its navigation entry", async () => {
    api.addBrand();
    render(<AppShell><ReviewView /></AppShell>);
    expect(await screen.findByRole("heading", { name: "Review content" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Review content/ })).toHaveAttribute("href", "/review");
    expect(screen.getByTestId("review-brand")).toHaveTextContent("Nova Systems");
  });

  it("P2-34: submitting sends the draft to the real client, which saves it and then requests a review", async () => {
    const { b } = seedReview(api);
    renderPage(<ReviewView />);
    await submitDraft();
    await screen.findByTestId("count-supported");
    const save = api.calls.find((c) => c.method === "POST" && c.url === `/api/brands/${b.id}/content`)!;
    expect(save.body).toMatchObject({ title: "Spring campaign", content: DRAFT });
    const start = api.calls.find((c) => c.method === "POST" && c.url.endsWith("/reviews"))!;
    expect(start.url).toBe(`/api/content/${api.contents[0].id}/reviews`);
    expect(api.contents[0].content).toBe(DRAFT);
  });

  it("validates empty input without calling the API", async () => {
    api.addBrand();
    renderPage(<ReviewView />);
    await screen.findByTestId("review-brand");
    await userEvent.click(screen.getByRole("button", { name: "Review content" }));
    expect(await screen.findByText("Enter a title for this draft.")).toBeInTheDocument();
    expect(screen.getByText("Paste or write the content to review.")).toBeInTheDocument();
    expect(api.calls.some((c) => c.method === "POST" && !c.url.includes("/auth"))).toBe(false);
  });

  it("P2-35: summary counts and the finding list are exactly what the backend returned", async () => {
    seedReview(api);
    renderPage(<ReviewView />);
    await submitDraft();
    expect(await screen.findByTestId("count-supported")).toHaveTextContent("1");
    expect(screen.getByTestId("count-conflicting")).toHaveTextContent("1");
    expect(screen.getByTestId("count-unsupported")).toHaveTextContent("1");
    expect(screen.getByTestId("count-outdated")).toHaveTextContent("0");
    expect(screen.getByTestId("count-uncertain")).toHaveTextContent("0");
    const items = screen.getAllByTestId("finding-item");
    expect(items).toHaveLength(3);
    expect(items[1]).toHaveTextContent(C2);
    expect(within(items[1]).getByTestId("finding-status")).toHaveTextContent("Conflicting");
    expect(items[1]).toHaveTextContent("High priority");
    expect(items[1]).toHaveTextContent("Needs human review");
    expect(items[1]).toHaveTextContent("Correct the figure.");
    expect(screen.getAllByTestId("claim-mark").length + screen.getAllByTestId("claim-mark-selected").length).toBe(3);
  });

  it("P2-36: selecting a finding shows its explanation and evidence", async () => {
    seedReview(api);
    renderPage(<ReviewView />);
    await submitDraft();
    await userEvent.click((await screen.findAllByTestId("finding-item"))[1]);
    const panel = screen.getByTestId("evidence-panel");
    expect(panel).toHaveTextContent("The claim states 24 hours, but the approved value is up to 18 hours.");
    expect(within(panel).getByText("Conflicting evidence")).toBeInTheDocument();
    expect(panel).toHaveTextContent("Battery life: Up to 18 hours");
    expect(panel).toHaveTextContent("Conditions: Under specified test conditions");
    expect(screen.getByTestId("needs-review")).toBeInTheDocument();
    expect(screen.getByTestId("claim-mark-selected")).toHaveTextContent(C2);
  });

  it("P2-37: opening a citation shows the correct source and page with the passage marked", async () => {
    const { doc } = seedReview(api);
    renderPage(<ReviewView />);
    await submitDraft();
    await userEvent.click((await screen.findAllByTestId("finding-item"))[0]);
    await userEvent.click(within(screen.getByTestId("evidence-panel")).getByRole("button", { name: /Open source \(page 2\)/ }));
    const source = await screen.findByTestId("source-evidence");
    expect(source).toHaveTextContent(doc.title);
    expect(source).toHaveTextContent("Page 2 of 3");
    expect((await within(source).findByTestId("excerpt-mark")).textContent).toBe("Battery life: up to 18 hours under specified test conditions.");
    expect(api.calls.some((c) => c.url === `/api/documents/${doc.id}/sections?page_number=2&limit=200`)).toBe(true);
  });

  it("P2-38: an unsupported claim says approved evidence was not found and shows no citation", async () => {
    seedReview(api);
    renderPage(<ReviewView />);
    await submitDraft();
    await userEvent.click((await screen.findAllByTestId("finding-item"))[2]);
    const panel = screen.getByTestId("evidence-panel");
    expect(within(panel).getByTestId("no-evidence")).toHaveTextContent("No suitable approved evidence was found");
    expect(within(panel).queryAllByTestId("evidence-item")).toHaveLength(0);
    expect(within(panel).queryByRole("button", { name: /Open source/ })).not.toBeInTheDocument();
  });

  it("P2-39a: a server error while saving shows the message and never reports a review result", async () => {
    api.addBrand();
    renderPage(<ReviewView />);
    await screen.findByTestId("review-brand");
    api.failNext = { status: 503, code: "database_unavailable", message: "The database is currently unavailable." };  // fails the save, not the page load
    await submitDraft();
    expect(await screen.findByText("The database is currently unavailable.")).toBeInTheDocument();
    expect(screen.queryByTestId("count-supported")).not.toBeInTheDocument();
    expect(screen.queryByText(/Completed/)).not.toBeInTheDocument();
  });

  it("P2-39b: a failed review run is shown as failed, with retry, and nothing is presented as verified", async () => {
    const { b } = seedReview(api);
    const working = api.reviewResponder;
    api.reviewResponder = () => ({ run: { status: "failed", error_code: "provider_unavailable", error_message: "The AI provider could not be reached.", completed_at: null }, findings: [] });
    renderPage(<ReviewView />);
    await submitDraft();
    expect(await screen.findByTestId("run-failed")).toHaveTextContent("nothing in this draft has been verified");
    expect(screen.getAllByRole("alert").some((a) => a.textContent?.includes("The AI provider could not be reached."))).toBe(true);
    expect(screen.queryByTestId("count-supported")).not.toBeInTheDocument();
    expect(screen.queryByTestId("finding-item")).not.toBeInTheDocument();
    // Retry runs a fresh review of the same saved content.
    api.reviewResponder = working;  // the provider is back
    await userEvent.click(screen.getByRole("button", { name: "Retry review" }));
    await waitFor(() => expect(api.calls.filter((c) => c.method === "POST" && c.url.endsWith("/reviews"))).toHaveLength(2));
    expect(api.contents).toHaveLength(1);
    expect(await screen.findByTestId("count-supported")).toHaveTextContent("1");
    expect(screen.queryByTestId("run-failed")).not.toBeInTheDocument();
    expect(b.id).toBeTruthy();
  });

  it("P2-39c: limited analysis is labelled and an empty result is not a failure", async () => {
    api.addBrand();
    api.reviewResponder = () => ({
      run: { status: "completed_limited", analysis_mode: "limited", provider_name: null, model_name: null, limitations: ["Limited analysis: no AI provider is configured (LLM_API_KEY is empty)."], notes: ["No candidate claims were detected in this content."] },
      findings: [],
    });
    renderPage(<ReviewView />);
    await submitDraft("We are delighted to welcome everyone.");
    expect(await screen.findByTestId("limited-mode")).toBeInTheDocument();
    expect(screen.getAllByText(/LLM_API_KEY is empty/)[0]).toBeInTheDocument();
    expect(screen.getByText(/No claims were identified in this draft by the deterministic rules/)).toBeInTheDocument();
    expect(screen.queryByTestId("run-failed")).not.toBeInTheDocument();
  });

  it("P2-40: reopening a saved draft loads its persisted findings from the backend", async () => {
    seedReview(api);
    const first = renderPage(<ReviewView />);
    await submitDraft();
    await screen.findByTestId("count-supported");
    first.unmount();  // a fresh page load: nothing is kept in the browser
    api.calls.length = 0;
    renderPage(<ReviewView />);
    await userEvent.click(await screen.findByRole("button", { name: "Spring campaign" }));
    expect(await screen.findByTestId("count-conflicting")).toHaveTextContent("1");
    expect(api.calls.map((c) => c.url)).toEqual(expect.arrayContaining([
      `/api/content/${api.contents[0].id}`, `/api/content/${api.contents[0].id}/reviews`, `/api/reviews/${api.runs[api.contents[0].id][0].id}/findings?limit=200`,
    ]));
    expect(api.calls.some((c) => c.method === "POST" && !c.url.includes("/auth"))).toBe(false);  // nothing was re-run or reconstructed
    expect(screen.getAllByTestId("finding-item")).toHaveLength(3);
    expect(screen.getByTestId("draft-text")).toHaveTextContent(DRAFT);
  });

  it("shows an empty state when a brand has no drafts yet", async () => {
    api.addBrand();
    renderPage(<ReviewView />);
    expect(await screen.findByText("No drafts reviewed yet")).toBeInTheDocument();
  });
});


describe("Fact changes page (Phase 3 Claim Ledger)", () => {
  it("P3-45: loads the actual impacts and summary from the backend", async () => {
    const b = api.addBrand();
    api.addImpact(b.id);
    api.addImpact(b.id, { content: api.contentBrief("Back to school") });
    renderPage(<FactChangesView />);
    expect(await screen.findAllByTestId("impact-row")).toHaveLength(2);
    expect(api.calls.some((c) => c.url.startsWith(`/api/brands/${b.id}/fact-change-impacts?`))).toBe(true);
    expect(api.calls.some((c) => c.url === `/api/brands/${b.id}/fact-change-impacts/summary`)).toBe(true);
  });

  it("P3-45b: summary counts come from the API response, not fixed values", async () => {
    const b = api.addBrand();
    const factA = api.id();
    api.addImpact(b.id, { fact: { id: factA, name: "Battery life", status: "proposed", effective_state: "unapproved", version: 2, value: "x", unit: null } });
    api.addImpact(b.id, { fact: { id: factA, name: "Battery life", status: "proposed", effective_state: "unapproved", version: 2, value: "x", unit: null }, content: api.contentBrief("Second") });
    api.addImpact(b.id, { trigger_type: "fact_expiry", change_type: "expired", content: api.contentBrief("Third") });
    renderPage(<FactChangesView />);
    expect(await screen.findByTestId("summary-open")).toHaveTextContent("3");
    expect(screen.getByTestId("summary-content")).toHaveTextContent("3");
    expect(screen.getByTestId("summary-facts")).toHaveTextContent("2");
    expect(screen.getByTestId("summary-expiry")).toHaveTextContent("1");
  });

  it("P3-46: an affected asset shows its changed fact, previous and current values, claim and reason", async () => {
    const b = api.addBrand();
    api.addImpact(b.id);
    renderPage(<FactChangesView />);
    const row = await screen.findByTestId("impact-row");
    expect(within(row).getByTestId("impact-content")).toHaveTextContent("Summer Campaign Advertisement");
    expect(within(row).getByTestId("impact-fact")).toHaveTextContent("Battery life");
    expect(within(row).getByTestId("impact-previous")).toHaveTextContent("Up to 18 hours");
    expect(within(row).getByTestId("impact-current")).toHaveTextContent("Up to 14 hours");
    expect(within(row).getByTestId("impact-claim")).toHaveTextContent("Battery life lasts up to 18 hours");
    expect(within(row).getByTestId("impact-reason-short")).toHaveTextContent("Meaning or evidence changed");
    expect(within(row).getByTestId("impact-status")).toHaveTextContent("Needs review");
  });

  it("P3-47: opening an impact shows the historical and the current fact information separately", async () => {
    const b = api.addBrand();
    api.addImpact(b.id);
    renderPage(<FactChangesView />);
    await userEvent.click(await screen.findByRole("button", { name: "Inspect impact" }));
    const detail = await screen.findByTestId("impact-detail");
    expect(within(detail).getByTestId("detail-previous")).toHaveTextContent("Up to 18 hours");
    expect(within(detail).getByTestId("detail-current")).toHaveTextContent("Up to 14 hours");
    expect(within(detail).getByText(/Historical: version 1/)).toBeInTheDocument();
    expect(within(detail).getByText(/Current: version 2/)).toBeInTheDocument();
    expect(within(detail).getByTestId("impact-reason")).toHaveTextContent("Another review is recommended");
    expect(within(detail).getByText(/Revision 2/)).toHaveTextContent("Reason given: Test results revised");
    expect(within(detail).getByTestId("resolution-section")).toHaveTextContent("Recorded against revision 1");   // Phase 4: resolution lives here; nothing is closed by viewing
  });

  it("P3-48: a historical finding shows the original claim and the evidence as saved at review time", async () => {
    const b = api.addBrand();
    api.addImpact(b.id);
    renderPage(<FactChangesView />);
    await userEvent.click(await screen.findByRole("button", { name: "Inspect impact" }));
    const finding = await screen.findByTestId("historical-finding");
    expect(finding).toHaveTextContent("Battery life lasts up to 18 hours");
    const ev = within(finding).getByTestId("historical-evidence");
    expect(ev).toHaveTextContent("Up to 18 hours");
    expect(ev).toHaveTextContent("Battery life: up to 18 hours under specified test conditions.");
    expect(ev).toHaveTextContent("Nova spec, page 2");
    expect(finding).toHaveTextContent("Saved evidence cites fact version 1");
  });

  it("P3-49: no affected content shows a clear empty state", async () => {
    api.addBrand();
    renderPage(<FactChangesView />);
    expect(await screen.findByText("No content is affected")).toBeInTheDocument();
    expect(await screen.findByTestId("summary-open")).toHaveTextContent("0");
    expect(screen.queryByTestId("impact-row")).not.toBeInTheDocument();
  });

  it("P3-50: when the list request fails, an error is shown and no empty state or zero count is shown", async () => {
    const b = api.addBrand();
    api.addImpact(b.id);
    // The page requests the fact list first, then impacts and summary; fail every impact request.
    const original = api.handler;
    api.handler = async (input, init) => {
      if (String(input).includes("/fact-change-impacts")) return new Response(JSON.stringify({ error: { code: "database_unavailable", message: "The database is currently unavailable.", details: [], request_id: "t" } }), { status: 503, headers: { "Content-Type": "application/json" } });
      return original(input, init);
    };
    vi.stubGlobal("fetch", vi.fn(api.handler));
    renderPage(<FactChangesView />);
    expect(await screen.findByText(/could not be loaded, so nothing is shown here/)).toBeInTheDocument();
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
    expect(screen.queryByText("No content is affected")).not.toBeInTheDocument();
    expect(screen.queryByTestId("summary-open")).not.toBeInTheDocument();
  });

  it("P3-51: reloading the page returns the same persisted records", async () => {
    const b = api.addBrand();
    api.addImpact(b.id);
    const first = renderPage(<FactChangesView />);
    expect(await screen.findByTestId("impact-content")).toHaveTextContent("Summer Campaign Advertisement");
    first.unmount();
    renderPage(<FactChangesView />);
    expect(await screen.findAllByTestId("impact-row")).toHaveLength(1);
    expect(screen.getByTestId("impact-previous")).toHaveTextContent("Up to 18 hours");
    expect(api.calls.filter((c) => c.url.includes("/fact-change-impacts?")).length).toBeGreaterThanOrEqual(2);
  });

  it("P3-52: the impact links to the draft's existing review page", async () => {
    const b = api.addBrand();
    const impact = api.addImpact(b.id);
    renderPage(<FactChangesView />);
    await userEvent.click(await screen.findByRole("button", { name: "Inspect impact" }));
    const link = await screen.findByRole("link", { name: /Open the latest revision/ });
    expect(link).toHaveAttribute("href", `/review?content=${impact.content.id}`);
  });

  it("P3-52b: the review page opens that draft with its stored review when given the link", async () => {
    const b = api.addBrand();
    const item: ContentItem = { id: api.id(), brand_id: b.id, asset_id: api.id(), revision_number: 1, parent_submission_id: null, workflow_status: "draft", is_latest: true, change_note: null, title: "Summer Campaign Advertisement", content: "Battery life lasts up to 18 hours.", content_hash: "c".repeat(64), submitted_by: null, created_at: "2026-10-20T00:00:00Z", updated_at: "2026-10-20T00:00:00Z", review_count: 1, latest_review: null };
    api.contents.push(item);
    const runId = api.id();
    api.runs[item.id] = [{ id: runId, brand_id: b.id, content_submission_id: item.id, status: "completed_limited", analysis_mode: "limited", content_hash: item.content_hash, requested_by: null, started_at: "2026-10-20T00:00:05Z", completed_at: "2026-10-20T00:00:06Z", provider_name: null, model_name: null, error_code: null, error_message: null, counts: { supported: 1 }, limitations: [], notes: [], total_findings: 1, findings: null }];
    api.findingsByRun[runId] = [api.makeFinding(runId, item.content, "Battery life lasts up to 18 hours")];
    window.history.pushState({}, "", `/review?content=${item.id}`);
    try {
      renderPage(<ReviewView />);
      expect(await screen.findByTestId("draft-text")).toHaveTextContent("Battery life lasts up to 18 hours.");
      expect(await screen.findAllByTestId("finding-item")).toHaveLength(1);
      expect(api.calls.some((c) => c.url === `/api/content/${item.id}/reviews`)).toBe(true);
      expect(api.calls.some((c) => c.method === "POST" && c.url.endsWith("/reviews"))).toBe(false);   // opening never starts a new review
    } finally {
      window.history.pushState({}, "", "/");
    }
  });

  it("filters by trigger through the API and resets to the first page", async () => {
    const b = api.addBrand();
    api.addImpact(b.id);
    api.addImpact(b.id, { trigger_type: "fact_expiry", change_type: "expired", content: api.contentBrief("Expired one") });
    renderPage(<FactChangesView />);
    expect(await screen.findAllByTestId("impact-row")).toHaveLength(2);
    await userEvent.selectOptions(screen.getByLabelText("Trigger"), "fact_expiry");
    await waitFor(() => expect(screen.getAllByTestId("impact-row")).toHaveLength(1));
    expect(screen.getByTestId("impact-content")).toHaveTextContent("Expired one");
    expect(api.calls.some((c) => c.url.includes("trigger_type=fact_expiry"))).toBe(true);
  });

  it("paginates through the API", async () => {
    const b = api.addBrand();
    for (let n = 1; n <= 12; n++) api.addImpact(b.id, { content: api.contentBrief(`Draft ${n}`) });
    renderPage(<FactChangesView />);
    expect(await screen.findAllByTestId("impact-row")).toHaveLength(10);
    expect(screen.getByText(/Showing 1 to 10 of 12/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(screen.getAllByTestId("impact-row")).toHaveLength(2));
    expect(screen.getByText(/Showing 11 to 12 of 12/)).toBeInTheDocument();
    expect(api.calls.some((c) => c.url.includes("offset=10"))).toBe(true);
  });

  it("the shell navigation links to the Fact changes page", async () => {
    api.addBrand();
    render(<AppShell><div>child</div></AppShell>);
    expect(await screen.findByRole("link", { name: /Fact changes/ })).toHaveAttribute("href", "/fact-changes");
  });
});
