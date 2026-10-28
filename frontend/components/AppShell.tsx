"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type FormEvent, type ReactNode, useState } from "react";

import { Dialog, Field, Loading, Notice } from "@/components/ui";
import { BrandProvider, ToastProvider, useBrand, useToast } from "@/components/providers";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import {
  IconHome, IconKnowledge, IconFacts, IconReview, IconImpacts, IconCampaigns,
  IconGuidelines, IconSandbox, IconInsights, IconPlus,
} from "@/components/Icons";

interface NavItem {
  href: string;
  label: string;
  hint: string;
  icon: (props: { className?: string }) => ReactNode;
}

const NAV_GROUPS: { group: string; items: NavItem[] }[] = [
  {
    group: "Getting Started",
    items: [
      { href: "/", label: "Overview & Guide", hint: "Judge walkthrough", icon: IconHome },
    ],
  },
  {
    group: "Knowledge Base",
    items: [
      { href: "/knowledge", label: "Brand knowledge", hint: "Source documents", icon: IconKnowledge },
      { href: "/facts", label: "Approved facts", hint: "Claim ledger", icon: IconFacts },
    ],
  },
  {
    group: "Review & Workflow",
    items: [
      { href: "/review", label: "Review content", hint: "Findings & revisions", icon: IconReview },
      { href: "/fact-changes", label: "Fact changes", hint: "Affected content & resolution", icon: IconImpacts },
      { href: "/guidelines", label: "Guidelines", hint: "Rules & lint checks", icon: IconGuidelines },
    ],
  },
  {
    group: "Campaigns & Intelligence",
    items: [
      { href: "/campaigns", label: "Campaigns", hint: "Audits & release readiness", icon: IconCampaigns },
      { href: "/sandbox", label: "Policy sandbox", hint: "Simulate proposed rules", icon: IconSandbox },
      { href: "/insights", label: "Governance insights", hint: "Analytics & recommendations", icon: IconInsights },
    ],
  },
];

function NewBrandDialog({ onClose }: { onClose: () => void }) {
  const { createBrand } = useBrand();
  const toast = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setError("Enter a brand name.");
    setBusy(true);
    setError(null);
    try {
      const b = await createBrand(name.trim(), description.trim());
      toast.push("success", `Brand "${b.name}" created.`);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err : errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  const message = error instanceof ApiError ? error.fieldMessage("name") ?? error.message : error;
  return (
    <Dialog title="New brand" onClose={onClose}
      footer={<><button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button><button form="new-brand-form" className="btn btn-primary" disabled={busy}>{busy ? "Creating" : "Create brand"}</button></>}>
      <form id="new-brand-form" onSubmit={submit} className="space-y-4" noValidate>
        {message && <Notice kind="error">{message}</Notice>}
        <Field label="Brand name" htmlFor="brand-name"><input id="brand-name" className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="off" /></Field>
        <Field label="Description" htmlFor="brand-description" hint="Optional. Who the brand is and what content it publishes.">
          <textarea id="brand-description" className="input" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} />
        </Field>
      </form>
    </Dialog>
  );
}

function ApiStatus() {
  const { data, error, loading } = useResource(() => api.health(), []);
  const text = loading ? "Checking API" : error ? "API unreachable" : "API online";
  return (
    <div className="flex items-center gap-2 rounded-lg border border-rule/70 bg-paper/60 px-3 py-2 text-xs font-semibold text-ink-soft shadow-subtle" role="status">
      <span aria-hidden className={`inline-block h-2 w-2 rounded-full ring-2 ring-sheet ${error ? "bg-state-expired" : data ? "bg-state-current" : "bg-ink-faint"}`} />
      <span className="tracking-wide">{text}</span>
    </div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { brands, brand, loading, error, selectBrand, reload, actor, setActor, role, setRole } = useBrand();
  const [creating, setCreating] = useState(false);

  // Compute active navigation title for top header
  const allNavItems = NAV_GROUPS.flatMap((g) => g.items);
  const currentItem = allNavItems.find((item) => item.href === "/" ? pathname === "/" : pathname?.startsWith(item.href)) ?? allNavItems[0];

  return (
    <div className="min-h-screen bg-paper md:grid md:grid-cols-[272px_1fr]">
      {/* Sidebar */}
      <aside className="border-b border-rule bg-sheet md:sticky md:top-0 md:h-screen md:overflow-y-auto md:border-b-0 md:border-r shadow-subtle z-20">
        <div className="flex flex-col h-full justify-between p-5">
          <div className="space-y-6">
            {/* Brand Logo & Tagline */}
            <div className="flex items-center justify-between border-b border-rule/60 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-signal text-white font-serif font-bold text-lg shadow-sm">
                  B
                </div>
                <div>
                  <p className="font-serif text-xl font-bold tracking-tight text-ink leading-none">BrandPR</p>
                  <p className="mt-1 text-xs text-ink-soft font-medium">Enterprise Governance</p>
                </div>
              </div>
            </div>

            {/* Brand Selector */}
            <div className="rounded-xl border border-rule bg-paper/50 p-3 shadow-subtle">
              <div className="flex items-center justify-between mb-1.5">
                <label className="label mb-0" htmlFor="brand-select">Active Brand</label>
                <button type="button" className="btn btn-quiet text-xs font-semibold px-1 py-0 h-auto min-h-0 flex items-center gap-1" onClick={() => setCreating(true)}>
                  <IconPlus className="h-3 w-3" /> New
                </button>
              </div>
              <select id="brand-select" className="input bg-sheet text-sm font-medium py-1.5" value={brand?.id ?? ""} onChange={(e) => selectBrand(e.target.value)} disabled={!brands.length}>
                {!brands.length && <option value="">No brands yet</option>}
                {brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>

            {/* Navigation Groups */}
            <nav aria-label="Primary" className="space-y-5">
              {NAV_GROUPS.map((group) => (
                <div key={group.group} className="space-y-1">
                  <p className="px-2.5 text-[11px] font-bold uppercase tracking-wider text-ink-faint">
                    {group.group}
                  </p>
                  <ul className="space-y-0.5">
                    {group.items.map((item) => {
                      const active = item.href === "/" ? pathname === "/" : pathname?.startsWith(item.href);
                      const Icon = item.icon;
                      return (
                        <li key={item.href}>
                          <Link
                            href={item.href}
                            aria-current={active ? "page" : undefined}
                            className={`group flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-all duration-150 ${
                              active
                                ? "bg-signal-wash font-semibold text-signal-dark shadow-subtle border border-signal-border"
                                : "text-ink-soft hover:bg-paper hover:text-ink font-medium"
                            }`}
                          >
                            <span className={`shrink-0 ${active ? "text-signal" : "text-ink-faint group-hover:text-ink-soft"}`}>
                              <Icon className="h-4 w-4" />
                            </span>
                            <div className="min-w-0 flex-1">
                              <span className="block truncate leading-snug">{item.label}</span>
                              <span className="block truncate text-[11px] font-normal text-ink-faint leading-none mt-0.5">
                                {item.hint}
                              </span>
                            </div>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </nav>
          </div>

          {/* Actor & Role Controls */}
          <div className="border-t border-rule/70 pt-4 mt-6 space-y-3">
            <div className="rounded-xl border border-rule bg-paper/40 p-3 space-y-2.5 shadow-subtle">
              <div>
                <label className="label text-[11px] mb-1" htmlFor="actor">Your name</label>
                <input
                  id="actor"
                  className="input bg-sheet text-xs py-1.5"
                  value={actor}
                  onChange={(e) => setActor(e.target.value)}
                  placeholder="Your Name (for audit trail)"
                  maxLength={200}
                  autoComplete="name"
                />
              </div>
              <div>
                <label className="label text-[11px] mb-1" htmlFor="role">Demo role</label>
                <select
                  id="role"
                  className="input bg-sheet text-xs py-1.5 font-medium"
                  value={role}
                  onChange={(e) => setRole(e.target.value as "creator" | "reviewer")}
                >
                  <option value="creator">Creator: Edit & submit</option>
                  <option value="reviewer">Reviewer: Approve & release</option>
                </select>
              </div>
              <p className="text-[11px] text-ink-muted leading-tight pt-0.5">Demo identity, not sign-in: anyone can pick a role. The server still enforces what each role may do, and a reviewer cannot approve content they created.</p>
            </div>
            <ApiStatus />
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-col min-w-0">
        {/* Top Header Bar */}
        <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-rule bg-sheet/95 backdrop-blur-sm px-6 md:px-10">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-sm text-ink-soft">
              <span className="font-medium text-ink-faint">Platform</span>
              <span className="text-ink-faint">/</span>
              <span className="font-semibold text-ink">{currentItem.label}</span>
            </div>
            {brand && (
              <span className="hidden sm:inline-flex items-center gap-1.5 rounded-full bg-paper px-2.5 py-0.5 text-xs font-semibold text-ink-soft border border-rule">
                <span className="h-1.5 w-1.5 rounded-full bg-signal" />
                <span>{brand.name}</span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-ink-soft hidden md:inline">Acting as:</span>
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-rule bg-paper px-2.5 py-1 text-xs font-bold text-ink">
                <span>{actor || "Anonymous"}</span>
                <span className={`rounded px-1.5 py-0.2 text-[10px] uppercase tracking-wider ${role === "reviewer" ? "bg-signal text-white" : "bg-rule text-ink-soft"}`}>
                  {role}
                </span>
              </span>
            </div>
          </div>
        </header>

        {/* Page Content Viewport */}
        <main className="min-w-0 flex-1 px-6 py-8 md:px-10">
          <div className="mx-auto max-w-[1160px]">
            {loading && !brands.length ? (
              <Loading label="Loading brands" />
            ) : error ? (
              <Notice kind="error" action={<button className="btn btn-secondary" onClick={reload}>Try again</button>}>
                {error}
              </Notice>
            ) : (
              children
            )}
          </div>
        </main>
      </div>

      {creating && <NewBrandDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return <ToastProvider><BrandProvider><Shell>{children}</Shell></BrandProvider></ToastProvider>;
}
