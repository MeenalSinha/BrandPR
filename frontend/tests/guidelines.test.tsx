import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { BrandProvider, ToastProvider } from "@/components/providers";
import { GuidelinesView } from "@/components/GuidelinesView";
import { PolicySandboxView } from "@/components/PolicySandboxView";
import { InsightsView } from "@/components/InsightsView";
import { FakeApi } from "./fakeApi";

let api: FakeApi;

beforeEach(() => {
  api = new FakeApi().install();
  window.history.pushState({}, "", "/");
});

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <ToastProvider>
      <BrandProvider>{ui}</BrandProvider>
    </ToastProvider>
  );
}

const as = (name: string, role: "creator" | "reviewer") => {
  window.localStorage.setItem("brandpr.actor", name);
  window.localStorage.setItem("brandpr.role", role);
};

describe("Phase 5 Frontend Components", () => {
  it("P5-21: Guidelines list loads from API and displays active and proposed rules", async () => {
    as("Alex Admin", "reviewer");
    const b = api.addBrand("Aegis Tech");
    api.addGuideline(b.id, {
      title: "No Comparative Claims",
      rule_text: "Comparative claims must not be used without prior lab verification.",
      status: "active",
      current_version: 1,
    });
    api.addGuideline(b.id, {
      title: "Proposed Tone Rule",
      rule_text: "Marketing content must maintain an objective, professional tone.",
      status: "proposed",
      current_version: 1,
    });

    renderWithProviders(<GuidelinesView />);

    expect(await screen.findByText("No Comparative Claims")).toBeInTheDocument();
    expect(screen.getByText("Proposed Tone Rule")).toBeInTheDocument();
    expect(screen.getAllByText("ACTIVE").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("PROPOSED").length).toBeGreaterThanOrEqual(1);
  });

  it("P5-21b: Running guideline lint identifies candidate issues", async () => {
    as("Alex Admin", "reviewer");
    const b = api.addBrand("Aegis Tech");
    api.addGuideline(b.id, {
      title: "Vague Performance Guideline",
      rule_text: "Our solutions deliver market-leading best performance.",
      status: "active",
    });

    renderWithProviders(<GuidelinesView />);
    await screen.findByText("Vague Performance Guideline");

    const lintBtn = screen.getByRole("button", { name: /Run Guideline Lint/i });
    await userEvent.click(lintBtn);

    expect(await screen.findByText(/Guideline Lint Results/i)).toBeInTheDocument();
  });

  it("P5-22: Policy Sandbox simulates proposed policy against historical content without altering records", async () => {
    as("Alex Admin", "reviewer");
    const b = api.addBrand("Aegis Tech");
    const rule = api.addGuideline(b.id, {
      title: "Comparative Claim Policy",
      rule_text: "Comparative claims must not be used.",
      status: "active",
    });

    renderWithProviders(<PolicySandboxView />);

    expect(await screen.findByText(/Configure Policy Simulation/i)).toBeInTheDocument();
    expect(screen.getByText(/Historical Integrity Guarantee/i)).toBeInTheDocument();

    const select = screen.getByLabelText(/1\. Select Active or Proposed Rule/i);
    await screen.findByText(new RegExp(rule.title, "i"));
    await userEvent.selectOptions(select, rule.id);

    const runBtn = screen.getByRole("button", { name: /Run Policy Simulation/i });
    await userEvent.click(runBtn);

    expect(await screen.findByText(/Simulation Report/i)).toBeInTheDocument();
    expect(screen.getByText(/Total Evaluated/i)).toBeInTheDocument();
    expect(screen.getByText(/Outcomes Changed/i)).toBeInTheDocument();
  });

  it("P5-23: Governance Intelligence renders real backend analytics and actionable recommendations", async () => {
    as("Alex Admin", "reviewer");
    const b = api.addBrand("Aegis Tech");

    renderWithProviders(<InsightsView />);

    expect(await screen.findByText(/Completed Reviews/i)).toBeInTheDocument();
    expect(screen.getByText(/Total Findings Flagged/i)).toBeInTheDocument();
    expect(screen.getByText(/Frequently Flagged Terms & Claims/i)).toBeInTheDocument();
    expect(screen.getByText(/Actionable Governance Recommendations/i)).toBeInTheDocument();
  });
});
