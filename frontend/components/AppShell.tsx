"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type FormEvent, type ReactNode, useState } from "react";

import { Dialog, Field, Loading, Notice } from "@/components/ui";
import { BrandProvider, ToastProvider, useBrand, useToast } from "@/components/providers";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useResource } from "@/lib/hooks";

const NAV = [
  { href: "/knowledge", label: "Brand knowledge", hint: "Source documents" },
  { href: "/facts", label: "Approved facts", hint: "Claim ledger" },
  { href: "/review", label: "Review content", hint: "Findings, revisions, approval" },
  { href: "/fact-changes", label: "Fact changes", hint: "Affected content and resolution" },
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
    <p className="flex items-center gap-2 text-sm text-ink-soft" role="status">
      <span aria-hidden className={`inline-block h-2.5 w-2.5 rounded-full ${error ? "bg-state-expired" : data ? "bg-state-current" : "bg-rule-strong"}`} />
      {text}
    </p>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { brands, brand, loading, error, selectBrand, reload, actor, setActor, role, setRole } = useBrand();
  const [creating, setCreating] = useState(false);

  return (
    <div className="min-h-screen md:grid md:grid-cols-[264px_1fr]">
      <aside className="border-b border-rule bg-sheet md:sticky md:top-0 md:h-screen md:overflow-y-auto md:border-b-0 md:border-r">
        <div className="flex flex-col gap-6 px-5 py-5">
          <div>
            <p className="font-serif text-2xl font-semibold tracking-tight">BrandPR</p>
            <p className="text-sm text-ink-soft">Approved brand knowledge</p>
          </div>
          <div>
            <label className="label" htmlFor="brand-select">Brand</label>
            <select id="brand-select" className="input" value={brand?.id ?? ""} onChange={(e) => selectBrand(e.target.value)} disabled={!brands.length}>
              {!brands.length && <option value="">No brands yet</option>}
              {brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
            <button type="button" className="btn btn-quiet mt-1 px-0" onClick={() => setCreating(true)}>New brand</button>
          </div>
          <nav aria-label="Primary">
            <ul className="space-y-1">
              {NAV.map((item) => {
                const active = pathname?.startsWith(item.href);
                return (
                  <li key={item.href}>
                    <Link href={item.href} aria-current={active ? "page" : undefined}
                          className={`block border-l-4 px-3 py-2 ${active ? "border-signal bg-signal-wash font-bold text-signal-dark" : "border-transparent hover:bg-paper"}`}>
                      <span className="block">{item.label}</span>
                      <span className="block text-sm font-normal text-ink-soft">{item.hint}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
          <div>
            <label className="label" htmlFor="actor">Your name</label>
            <input id="actor" className="input" value={actor} onChange={(e) => setActor(e.target.value)} placeholder="Recorded with approvals" maxLength={200} autoComplete="name" />
            <label className="label mt-3" htmlFor="role">Demo role</label>
            <select id="role" className="input" value={role} onChange={(e) => setRole(e.target.value as "creator" | "reviewer")}>
              <option value="creator">Creator: edits and submits content</option>
              <option value="reviewer">Reviewer: approves and resolves</option>
            </select>
            <p className="hint">Demo identity, not sign-in: anyone can pick a role. The server still enforces what each role may do, and a reviewer cannot approve content they created.</p>
          </div>
          <ApiStatus />
        </div>
      </aside>
      <main className="min-w-0 px-5 py-8 md:px-10">
        <div className="mx-auto max-w-[1080px]">
          {loading && !brands.length ? <Loading label="Loading brands" /> : error ? (
            <Notice kind="error" action={<button className="btn btn-secondary" onClick={reload}>Try again</button>}>{error}</Notice>
          ) : children}
        </div>
      </main>
      {creating && <NewBrandDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return <ToastProvider><BrandProvider><Shell>{children}</Shell></BrandProvider></ToastProvider>;
}
