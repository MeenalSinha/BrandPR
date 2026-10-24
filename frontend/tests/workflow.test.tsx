import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { AppShell } from "@/components/AppShell";
import { BrandProvider, ToastProvider } from "@/components/providers";
import { FactChangesView } from "@/components/FactChangesView";
import { ReviewView } from "@/components/ReviewView";
import type { ContentItem, Finding } from "@/types/api";
import { FakeApi } from "./fakeApi";

let api: FakeApi;
beforeEach(() => {
  api = new FakeApi().install();
  window.history.pushState({}, "", "/");
});

const CLAIM = "Battery life lasts up to 18 hours";
const as = (name: string, role: "creator" | "reviewer") => {
  window.localStorage.setItem("brandpr.actor", name);
  window.localStorage.setItem("brandpr.role", role);
};
function page(ui: React.ReactElement) {
  return render(<ToastProvider><BrandProvider>{ui}</BrandProvider></ToastProvider>);
}
function reviewed(over: Partial<ContentItem> = {}, findingOver: Partial<Finding> = {}, runOver = {}) {
  const b = api.brands[0] ?? api.addBrand();
  const item = api.addContent(b.id, over);
  const finding = api.makeFinding("pending", item.content, CLAIM, {
    status: "conflicting", severity: "medium", explanation: "The approved fact says up to 14 hours.",
    evidence: [api.makeEvidence({ role: "conflicts", fact_name: "Battery life", fact_value: "Up to 14 hours", fact_version: 3, excerpt: "Battery life: up to 14 hours.", source_title: "Nova spec", source_page: 2 })],
    ...findingOver,
  });
  const run = api.addReview(item, [finding], runOver);
  return { b, item, finding, run };
}
function open(id: string) {
  window.history.pushState({}, "", `/review?content=${id}`);
  return page(<ReviewView />);
}
const lastCall = (m: string, suffix: string) => [...api.calls].reverse().find((c) => c.method === m && c.url.endsWith(suffix));

describe("Revision editor (Phase 4)", () => {
  it("P4-U01: an existing submission opens with its revision number, status, findings and history", async () => {
    as("Casey Creator", "creator");
    const { item } = reviewed();
    open(item.id);
    expect(await screen.findByTestId("revision-label")).toHaveTextContent("Revision 1");
    expect(screen.getAllByTestId("workflow-status")[0]).toHaveTextContent("Draft");
    expect(await screen.findAllByTestId("finding-item")).toHaveLength(1);
    expect(await screen.findAllByTestId("revision-item")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Create corrected revision" })).toBeInTheDocument();
  });

  it("P4-U02: the editor keeps the original read only, shows evidence first, and cannot save without a change", async () => {
    as("Casey Creator", "creator");
    const { item } = reviewed();
    open(item.id);
    await userEvent.click(await screen.findByRole("button", { name: "Create corrected revision" }));
    expect(screen.getByTestId("original-text")).toHaveTextContent(item.content);
    expect(screen.getByLabelText(/Your revision/)).toHaveValue(item.content);
    expect(screen.getByTestId("correction-evidence")).toHaveTextContent("Up to 14 hours");
    expect(screen.getByTestId("correction-evidence")).toHaveTextContent("Battery life: up to 14 hours.");
    expect(screen.getByRole("button", { name: "Save as new revision" })).toBeDisabled();
  });

  it("P4-U03: a manual correction is saved as a new revision; the original stays; history shows both", async () => {
    as("Casey Creator", "creator");
    const { item, finding } = reviewed();
    open(item.id);
    await userEvent.click(await screen.findByRole("button", { name: "Create corrected revision" }));
    await userEvent.type(screen.getByLabelText("Or write the replacement yourself"), "Battery life lasts up to 14 hours");
    await userEvent.click(screen.getByRole("button", { name: "Replace claim" }));
    expect(screen.getByLabelText(/Your revision/)).toHaveValue("Battery life lasts up to 14 hours. Order today.");
    expect(screen.getByTestId("diff-removed")).toHaveTextContent("18");
    expect(screen.getByTestId("diff-added")).toHaveTextContent("14");
    expect(screen.getByTestId("original-text")).toHaveTextContent("up to 18 hours");           // never edited in place
    await userEvent.click(screen.getByRole("button", { name: "Save as new revision" }));
    await waitFor(() => expect(screen.getByTestId("revision-label")).toHaveTextContent("Revision 2"));
    const call = lastCall("POST", `/content/${item.id}/revisions`)!;
    expect(call.headers).toMatchObject({ "x-actor-name": "Casey Creator", "x-actor-role": "creator" });
    expect(call.body).toMatchObject({ content: "Battery life lasts up to 14 hours. Order today.", corrections: [{ finding_id: finding.id, decision: "manual", source: "manual", original_text: CLAIM }] });
    expect(api.contents.find((c) => c.id === item.id)!.content).toContain("18 hours");           // revision 1 unchanged on the server
    await waitFor(() => expect(screen.getAllByTestId("revision-item")).toHaveLength(2));
    expect(screen.getAllByTestId("workflow-status")[0]).toHaveTextContent("Draft");              // the new revision starts as a draft
  });

  it("P4-U04: an AI suggestion is a proposal; the draft changes only when it is accepted", async () => {
    as("Casey Creator", "creator");
    api.suggestResponder = () => ({ replacement_text: "Battery life lasts up to 14 hours", warnings: ["AI-generated: check the wording against the evidence before accepting.", "The suggestion contains number(s) that appear in neither the approved facts nor the original claim: 99."] });
    const { item, finding } = reviewed();
    open(item.id);
    await userEvent.click(await screen.findByRole("button", { name: "Create corrected revision" }));
    await userEvent.click(screen.getByRole("button", { name: "Suggest wording (AI)" }));
    const box = await screen.findByTestId("suggestion");
    expect(box).toHaveTextContent("Battery life lasts up to 14 hours");
    expect(box).toHaveTextContent(/neither the approved facts nor the original claim/);
    expect(screen.getByLabelText(/Your revision/)).toHaveValue(item.content);                    // not applied yet
    await userEvent.click(within(box).getByRole("button", { name: "Accept suggestion" }));
    expect(screen.getByLabelText(/Your revision/)).toHaveValue("Battery life lasts up to 14 hours. Order today.");
    await userEvent.click(screen.getByRole("button", { name: "Save as new revision" }));
    await waitFor(() => expect(lastCall("POST", `/content/${item.id}/revisions`)).toBeTruthy());
    expect(lastCall("POST", `/content/${item.id}/revisions`)!.body).toMatchObject({ corrections: [{ finding_id: finding.id, decision: "accepted", source: "ai" }] });
  });

  it("P4-U05: rejecting a suggestion leaves the draft alone and is recorded", async () => {
    as("Casey Creator", "creator");
    api.suggestResponder = () => ({ replacement_text: "Battery life lasts up to 14 hours" });
    const { item, finding } = reviewed();
    open(item.id);
    await userEvent.click(await screen.findByRole("button", { name: "Create corrected revision" }));
    await userEvent.click(screen.getByRole("button", { name: "Suggest wording (AI)" }));
    await userEvent.click(await screen.findByRole("button", { name: "Reject suggestion" }));
    expect(screen.getByLabelText(/Your revision/)).toHaveValue(item.content);
    expect(screen.queryByTestId("suggestion")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Your revision/), " Free shipping.");
    await userEvent.click(screen.getByRole("button", { name: "Save as new revision" }));
    await waitFor(() => expect(lastCall("POST", `/content/${item.id}/revisions`)).toBeTruthy());
    expect(lastCall("POST", `/content/${item.id}/revisions`)!.body).toMatchObject({ corrections: [{ finding_id: finding.id, decision: "rejected", replacement_text: null }] });
  });

  it("P4-U06: without an AI provider the message is honest and manual correction still works", async () => {
    as("Casey Creator", "creator");
    const { item } = reviewed();
    open(item.id);
    await userEvent.click(await screen.findByRole("button", { name: "Create corrected revision" }));
    await userEvent.click(screen.getByRole("button", { name: "Suggest wording (AI)" }));
    expect(await screen.findByTestId("correction-message")).toHaveTextContent(/No AI provider is configured/);
    expect(screen.queryByTestId("suggestion")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replace claim" })).toBeEnabled();
    await userEvent.type(screen.getByLabelText(/Your revision/), " Edited.");
    expect(screen.getByRole("button", { name: "Save as new revision" })).toBeEnabled();
  });

  it("P4-U07: a revision conflict is explained and the typed text is kept", async () => {
    as("Casey Creator", "creator");
    const { item } = reviewed();
    open(item.id);
    await userEvent.click(await screen.findByRole("button", { name: "Create corrected revision" }));
    await userEvent.type(screen.getByLabelText(/Your revision/), " My edit.");
    api.addContent(item.brand_id, { asset_id: item.asset_id, revision_number: 2, parent_submission_id: item.id });   // someone else saved revision 2
    item.is_latest = false;
    await userEvent.click(screen.getByRole("button", { name: "Save as new revision" }));
    expect(await screen.findByText(/A newer revision \(revision 2\) already exists/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Your revision/)).toHaveValue(`${item.content} My edit.`);
  });

  it("P4-U08: saving without a name explains why instead of failing silently", async () => {
    const { item } = reviewed();
    open(item.id);
    await userEvent.click(await screen.findByRole("button", { name: "Create corrected revision" }));
    expect(screen.getByText(/Enter your name in the sidebar before saving/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Your revision/), " More.");
    await userEvent.click(screen.getByRole("button", { name: "Save as new revision" }));
    expect(await screen.findByText(/Enter your name in the sidebar first/)).toBeInTheDocument();
  });

  it("P4-U09: an older revision is read only and points to the latest", async () => {
    as("Casey Creator", "creator");
    const { item } = reviewed({ is_latest: false });
    api.addContent(item.brand_id, { asset_id: item.asset_id, revision_number: 2, parent_submission_id: item.id });
    open(item.id);
    expect(await screen.findByText(/kept for the record/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create corrected revision" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open the latest revision" })).toBeDisabled();   // enabled once the latest id is known
    expect(await screen.findAllByTestId("revision-item")).toHaveLength(2);
  });
});

describe("Approval panel (Phase 4)", () => {
  it("P4-U10: a failed review is never shown as ready for approval", async () => {
    as("Casey Creator", "creator");
    const b = api.addBrand();
    const item = api.addContent(b.id);
    api.addReview(item, [], { status: "failed", error_message: "The provider timed out." });
    open(item.id);
    expect(await screen.findByTestId("not-ready")).toHaveTextContent("Not ready for approval");
    expect(screen.getAllByText(/provider timed out/i).length).toBeGreaterThan(0);   // the run banner and the approval panel both say so
    expect(screen.queryByRole("button", { name: "Submit for approval" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("P4-U11: a creator submits a reviewed revision; then it waits for a reviewer", async () => {
    as("Casey Creator", "creator");
    const { item } = reviewed();
    open(item.id);
    await userEvent.click(await screen.findByRole("button", { name: "Submit for approval" }));
    await waitFor(() => expect(within(screen.getByTestId("workflow-panel")).getByTestId("workflow-status")).toHaveTextContent("In review"));
    expect(screen.getByTestId("waiting")).toHaveTextContent(/Waiting for a reviewer/);
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByTestId("event-list")).toHaveTextContent("Submitted for approval");
    expect(lastCall("POST", `/content/${item.id}/submit-review`)!.headers).toMatchObject({ "x-actor-role": "creator" });
  });

  it("P4-U12: a reviewer approves and the approval and its history come from the backend", async () => {
    as("Riley Reviewer", "reviewer");
    const { item, finding } = reviewed({ workflow_status: "in_review" }, { status: "supported", severity: "low", evidence: [] });
    api.events.push({ id: api.id(), submission_id: item.id, revision_number: 1, action: "submitted", from_status: "draft", to_status: "in_review", actor: "Casey Creator", actor_role: "creator", rationale: null, review_run_id: null, finding_ids: [], created_at: "2026-10-22T11:00:00Z" });
    open(item.id);
    await userEvent.type(await screen.findByLabelText(/Reason \(required/), "Matches the spec.");
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(within(screen.getByTestId("workflow-panel")).getByTestId("workflow-status")).toHaveTextContent("Approved"));
    expect(screen.getByTestId("approved-note")).toHaveTextContent(/applies only to this exact text/);
    expect(lastCall("POST", `/content/${item.id}/decisions`)!.body).toMatchObject({ action: "approve", review_run_id: api.runs[item.id][0].id, rationale: "Matches the spec." });
    expect(lastCall("POST", `/content/${item.id}/decisions`)!.headers).toMatchObject({ "x-actor-name": "Riley Reviewer", "x-actor-role": "reviewer" });
    expect(screen.getByTestId("event-list")).toHaveTextContent("Approved");
    expect(finding.id).toBeTruthy();
  });

  it("P4-U13: a reviewer cannot decide on a revision they created", async () => {
    as("Riley Reviewer", "reviewer");
    const { item } = reviewed({ workflow_status: "in_review", submitted_by: "Riley Reviewer" });
    open(item.id);
    expect(await screen.findByTestId("waiting")).toHaveTextContent(/You created this revision/);
    expect(screen.queryByTestId("decision-form")).not.toBeInTheDocument();
  });

  it("P4-U14: changes and rejection need a reason before the button is usable", async () => {
    as("Riley Reviewer", "reviewer");
    const { item } = reviewed({ workflow_status: "in_review" }, { status: "supported", severity: "low", evidence: [] });
    open(item.id);
    const changes = await screen.findByRole("button", { name: "Request changes" });
    expect(changes).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Reason \(required/), "Wrong figure.");
    expect(changes).toBeEnabled();
    await userEvent.click(changes);
    await waitFor(() => expect(within(screen.getByTestId("workflow-panel")).getByTestId("workflow-status")).toHaveTextContent("Changes requested"));
    expect(lastCall("POST", `/content/${item.id}/decisions`)!.body).toMatchObject({ action: "request_changes", rationale: "Wrong figure." });
    expect(screen.getByTestId("event-list")).toHaveTextContent("Wrong figure.");
  });

  it("P4-U15: a high-risk finding needs a recorded reason before approval can be sent", async () => {
    as("Riley Reviewer", "reviewer");
    const { item, finding } = reviewed({ workflow_status: "in_review" }, { status: "conflicting", severity: "high" });
    open(item.id);
    const blocking = await screen.findByTestId("blocking-findings");
    expect(blocking).toHaveTextContent(CLAIM);
    const approve = screen.getByRole("button", { name: "Approve" });
    expect(approve).toBeDisabled();
    await userEvent.type(within(blocking).getByLabelText("Reason for accepting this risk"), "Legal confirmed the figure.");
    expect(approve).toBeEnabled();
    await userEvent.click(approve);
    await waitFor(() => expect(lastCall("POST", `/content/${item.id}/decisions`)).toBeTruthy());
    expect(lastCall("POST", `/content/${item.id}/decisions`)!.body).toMatchObject({ action: "approve", overrides: [{ finding_id: finding.id, reason: "Legal confirmed the figure." }] });
  });

  it("P4-U16: limited analysis is disclosed to the reviewer", async () => {
    as("Riley Reviewer", "reviewer");
    const { item } = reviewed({ workflow_status: "in_review" }, { status: "supported", severity: "low", evidence: [] }, { status: "completed_limited", analysis_mode: "limited", limitations: ["Limited analysis: no AI provider is configured (LLM_API_KEY is empty)."] });
    open(item.id);
    expect(await screen.findByTestId("limited-warning")).toHaveTextContent("limited mode");
  });

  it("P4-U17: a server refusal is shown, not hidden", async () => {
    as("Casey Creator", "creator");
    const { item } = reviewed();
    open(item.id);
    const submit = await screen.findByRole("button", { name: "Submit for approval" });
    api.failNext = { status: 409, code: "review_failed", message: "The latest review failed and is not evidence of anything." };
    await userEvent.click(submit);
    expect(await screen.findByText(/latest review failed/)).toBeInTheDocument();
  });
});

describe("Fact changes: resolution (Phase 4)", () => {
  function impactWithRevisions(extra: { approved?: boolean } = {}) {
    const b = api.addBrand();
    const original = api.addContent(b.id, { is_latest: false });
    const corrected = api.addContent(b.id, { asset_id: original.asset_id, revision_number: 2, parent_submission_id: original.id, workflow_status: extra.approved === false ? "draft" : "approved", content: "Battery life lasts up to 14 hours." });
    const impact = api.addImpact(b.id, { content: api.contentBrief("Summer Campaign Advertisement", { id: original.id, asset_id: original.asset_id, latest_revision_id: corrected.id, latest_revision_number: 2, latest_revision_status: corrected.workflow_status }) });
    return { b, original, corrected, impact };
  }

  it("P4-U20: status tabs query the backend and show closed impacts with their resolution", async () => {
    as("Riley Reviewer", "reviewer");
    const { b, impact } = impactWithRevisions();
    api.impacts[0].status = "resolved";
    api.impacts[0].resolution = { action: "resolved", actor: "Riley Reviewer", rationale: "Copy now says 14 hours.", created_at: "2026-10-23T12:00:00Z", resolving_submission_id: impact.content.latest_revision_id, resolving_revision_number: 2, resolving_review_run_id: null };
    page(<FactChangesView />);
    expect(await screen.findByText("No content is affected")).toBeInTheDocument();                // default tab: needs review, and none is open
    await userEvent.click(screen.getByTestId("tab-resolved"));
    expect(await screen.findByTestId("impact-resolution-line")).toHaveTextContent("Resolved by revision 2");
    expect(api.calls.some((c) => c.url.includes(`/brands/${b.id}/fact-change-impacts?`) && c.url.includes("status=resolved"))).toBe(true);
    expect(screen.getByTestId("impact-status")).toHaveTextContent("Resolved");
    await userEvent.click(screen.getByTestId("tab-all"));
    await waitFor(() => expect(api.calls.some((c) => c.url.includes("fact-change-impacts?") && !c.url.includes("status="))).toBe(true));
  });

  it("P4-U21: summary shows resolved and dismissed counts from the API", async () => {
    as("Riley Reviewer", "reviewer");
    const b = api.addBrand();
    api.addImpact(b.id);
    api.addImpact(b.id, { content: api.contentBrief("Two") });
    api.addImpact(b.id, { content: api.contentBrief("Three") });
    api.impacts[1].status = "resolved";
    api.impacts[2].status = "dismissed";
    page(<FactChangesView />);
    expect(await screen.findByTestId("summary-open")).toHaveTextContent("1");
    expect(screen.getByTestId("summary-resolved")).toHaveTextContent("1");
    expect(screen.getByTestId("summary-dismissed")).toHaveTextContent("1");
  });

  it("P4-U22: a reviewer resolves an impact with an approved later revision and a reason", async () => {
    as("Riley Reviewer", "reviewer");
    const { corrected } = impactWithRevisions();
    page(<FactChangesView />);
    await userEvent.click(await screen.findByRole("button", { name: "Inspect impact" }));
    const form = await screen.findByTestId("resolve-form");
    const resolve = within(form).getByRole("button", { name: "Resolve impact" });
    expect(resolve).toBeDisabled();
    await userEvent.selectOptions(within(form).getByLabelText(/Resolve with an approved/), corrected.id);
    expect(resolve).toBeDisabled();                                                              // still needs a reason
    await userEvent.type(within(form).getByLabelText(/Reason \(required\)/), "Copy corrected and approved.");
    await userEvent.click(resolve);
    await waitFor(() => expect(screen.getByTestId("resolution-record")).toHaveTextContent("Resolved by Riley Reviewer"));
    expect(lastCall("POST", "/resolve")!.body).toEqual({ resolving_submission_id: corrected.id, rationale: "Copy corrected and approved." });
    expect(screen.getByTestId("resolution-record")).toHaveTextContent("Copy corrected and approved.");
    expect(screen.queryByTestId("resolve-form")).not.toBeInTheDocument();
  });

  it("P4-U23: without an approved later revision there is nothing to resolve with", async () => {
    as("Riley Reviewer", "reviewer");
    impactWithRevisions({ approved: false });
    page(<FactChangesView />);
    await userEvent.click(await screen.findByRole("button", { name: "Inspect impact" }));
    const form = await screen.findByTestId("resolve-form");
    expect(within(form).getByLabelText(/Resolve with an approved/)).toBeDisabled();
    expect(form).toHaveTextContent("Reviewing or editing alone does not close an impact");
    expect(within(form).getByRole("button", { name: "Resolve impact" })).toBeDisabled();
  });

  it("P4-U24: dismissal needs a reason and records it", async () => {
    as("Riley Reviewer", "reviewer");
    impactWithRevisions({ approved: false });
    page(<FactChangesView />);
    await userEvent.click(await screen.findByRole("button", { name: "Inspect impact" }));
    const form = await screen.findByTestId("resolve-form");
    const dismiss = within(form).getByRole("button", { name: /Dismiss/ });
    expect(dismiss).toBeDisabled();
    await userEvent.type(within(form).getByLabelText(/Reason \(required\)/), "Campaign retired.");
    await userEvent.click(dismiss);
    await waitFor(() => expect(screen.getByTestId("resolution-record")).toHaveTextContent("Dismissed by Riley Reviewer"));
    expect(lastCall("POST", "/dismiss")!.body).toEqual({ rationale: "Campaign retired." });
  });

  it("P4-U25: a creator sees the impact but cannot close it, and a refusal is displayed", async () => {
    as("Casey Creator", "creator");
    impactWithRevisions();
    page(<FactChangesView />);
    await userEvent.click(await screen.findByRole("button", { name: "Inspect impact" }));
    expect(await screen.findByTestId("reviewer-only")).toBeInTheDocument();
    expect(screen.queryByTestId("resolve-form")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open the latest revision to correct it/ }).getAttribute("href")).toMatch(/^\/review\?content=/);
  });

  it("P4-U26: the server's refusal to resolve is shown and nothing is marked resolved", async () => {
    as("Riley Reviewer", "reviewer");
    const { corrected } = impactWithRevisions();
    page(<FactChangesView />);
    await userEvent.click(await screen.findByRole("button", { name: "Inspect impact" }));
    const form = await screen.findByTestId("resolve-form");
    await userEvent.selectOptions(within(form).getByLabelText(/Resolve with an approved/), corrected.id);
    await userEvent.type(within(form).getByLabelText(/Reason \(required\)/), "Approved anyway.");
    api.failNext = { status: 409, code: "conflict_unresolved", message: "The approved review still reports a conflict with the changed fact.", details: [] };
    await userEvent.click(within(form).getByRole("button", { name: "Resolve impact" }));
    expect(await screen.findByText(/still reports a conflict/)).toBeInTheDocument();
    expect(screen.queryByTestId("resolution-record")).not.toBeInTheDocument();
    expect(api.impacts[0].status).toBe("needs_review");
  });
});

describe("Demo identity (Phase 4)", () => {
  it("P4-U30: the role chosen in the sidebar is the role sent with workflow requests", async () => {
    const b = api.addBrand();
    const item = api.addContent(b.id);
    api.addReview(item, [], {});
    window.history.pushState({}, "", `/review?content=${item.id}`);
    render(<AppShell><ReviewView /></AppShell>);
    await userEvent.type(await screen.findByLabelText("Your name"), "Riley Reviewer");
    await userEvent.selectOptions(screen.getByLabelText("Demo role"), "reviewer");
    await waitFor(() => expect(api.calls.some((c) => c.url.endsWith("/workflow") && c.headers?.["x-actor-role"] === "reviewer" && c.headers?.["x-actor-name"] === "Riley Reviewer")).toBe(true));
    expect(screen.getByText(/not sign-in/i)).toBeInTheDocument();
  });
});
