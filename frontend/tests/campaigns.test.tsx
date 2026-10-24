import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { BrandProvider, ToastProvider } from "@/components/providers";
import { CampaignsView } from "@/components/CampaignsView";
import { CampaignDetailView } from "@/components/CampaignDetailView";
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

describe("Phase 6 Frontend Campaign Components", () => {
  it("P6-33: Campaign list loads from API and displays status badges and metrics", async () => {
    as("Alex Admin", "reviewer");
    const b = api.addBrand("Aegis Tech");
    api.addCampaign(b.id, {
      title: "Summer Product Launch",
      description: "Q3 global hardware rollout across multiple channels.",
      owner: "Morgan Lead",
      status: "ready_for_release",
      latest_readiness: "ready_for_release",
      asset_count: 2,
    });
    api.addCampaign(b.id, {
      title: "Fall Promotion Campaign",
      description: "Direct to consumer discount push.",
      owner: "Morgan Lead",
      status: "draft",
      latest_readiness: null,
      asset_count: 1,
    });

    renderWithProviders(<CampaignsView />);

    expect(await screen.findByText("Summer Product Launch")).toBeInTheDocument();
    expect(screen.getByText("Fall Promotion Campaign")).toBeInTheDocument();
    expect(screen.getByText(/Q3 global hardware rollout/i)).toBeInTheDocument();
    expect(screen.getAllByText("READY FOR RELEASE").length).toBeGreaterThanOrEqual(1);
  });

  it("P6-34: Campaign creation modal creates new campaign and adds to list", async () => {
    as("Alex Admin", "reviewer");
    const b = api.addBrand("Aegis Tech");

    renderWithProviders(<CampaignsView />);
    await screen.findByText("Campaigns & Portfolios");

    const newBtn = screen.getByRole("button", { name: /\+ New Campaign/i });
    await userEvent.click(newBtn);

    expect(screen.getByText(/Create New Campaign/i)).toBeInTheDocument();

    const titleInput = screen.getByLabelText(/Campaign Title/i);
    await userEvent.type(titleInput, "Winter Holiday Campaign");

    const descInput = screen.getByLabelText(/Description/i);
    await userEvent.type(descInput, "Holiday marketing push");

    const submitBtn = screen.getByRole("button", { name: /Create Campaign/i });
    await userEvent.click(submitBtn);

    expect(await screen.findByText("Winter Holiday Campaign")).toBeInTheDocument();
  });

  it("P6-35: Campaign detail view displays assets, triggers audit, and updates readiness", async () => {
    as("Alex Admin", "reviewer");
    const b = api.addBrand("Aegis Tech");
    const camp = api.addCampaign(b.id, {
      title: "Omnichannel Hardware Push",
      description: "Multi-channel hardware promotion.",
      status: "draft",
      latest_readiness: null,
    });
    const c1 = api.addContent(b.id, { title: "Landing Page Asset" });
    api.addCampaignAsset(camp.id, c1, "landing_page");

    renderWithProviders(<CampaignDetailView campaignId={camp.id} />);

    expect(await screen.findByText("Omnichannel Hardware Push")).toBeInTheDocument();
    expect(await screen.findByText("Landing Page Asset")).toBeInTheDocument();
    expect(screen.getByText("landing page")).toBeInTheDocument();

    const auditBtn = screen.getByRole("button", { name: /Run Campaign Audit/i });
    await userEvent.click(auditBtn);

    expect(await screen.findByText(/Audit #1 completed/i)).toBeInTheDocument();
  });

  it("P6-36 & P6-37: Release modal allows reviewer to evaluate readiness and release campaign", async () => {
    as("Alex Admin", "reviewer");
    const b = api.addBrand("Aegis Tech");
    const camp = api.addCampaign(b.id, {
      title: "Ready Hardware Rollout",
      status: "ready_for_release",
      latest_readiness: "ready_for_release",
    });
    const c1 = api.addContent(b.id, { title: "Reviewed Landing Page" });
    api.addCampaignAsset(camp.id, c1, "landing_page");

    renderWithProviders(<CampaignDetailView campaignId={camp.id} />);
    expect(await screen.findByText("Ready Hardware Rollout")).toBeInTheDocument();

    const releaseBtn = screen.getByRole("button", { name: /Release Campaign/i });
    await userEvent.click(releaseBtn);

    expect(await screen.findByRole("heading", { name: "Release Campaign" })).toBeInTheDocument();
    expect(screen.getByText(/You are certifying that all marketing assets in this campaign are approved/i)).toBeInTheDocument();

    const confirmBtn = screen.getByRole("button", { name: "Confirm Release" });
    await userEvent.click(confirmBtn);

    expect(await screen.findByText("Campaign officially released!")).toBeInTheDocument();
  });
});
