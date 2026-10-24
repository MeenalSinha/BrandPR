"use client";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, errorMessage, setIdentity } from "@/lib/api";
import { useStoredState } from "@/lib/hooks";
import type { ActorRole, Brand } from "@/types/api";

/* ---------------------------------------------------------------- toasts */
interface Toast { id: number; kind: "success" | "error"; message: string }
const ToastContext = createContext<{ push: (kind: Toast["kind"], message: string) => void }>({ push: () => {} });
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], message: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 9000 : 5000);
  }, []);
  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex max-w-sm flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} role={t.kind === "error" ? "alert" : "status"}
               className={`pointer-events-auto rounded-md border-l-4 bg-sheet px-4 py-3 text-sm font-bold shadow-lg ${t.kind === "error" ? "border-state-expired text-state-expired" : "border-state-current text-state-current"}`}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/* ---------------------------------------------------------------- brands and actor */
interface BrandContextValue {
  brands: Brand[];
  brand: Brand | null;
  loading: boolean;
  error: string | null;
  selectBrand: (id: string) => void;
  createBrand: (name: string, description?: string) => Promise<Brand>;
  reload: () => void;
  actor: string;
  setActor: (v: string) => void;
  /** Demo role. Not authentication: see the README. */
  role: ActorRole;
  setRole: (v: ActorRole) => void;
}

const BrandContext = createContext<BrandContextValue | null>(null);
export function useBrand(): BrandContextValue {
  const ctx = useContext(BrandContext);
  if (!ctx) throw new Error("useBrand must be used inside BrandProvider");
  return ctx;
}

export function BrandProvider({ children }: { children: ReactNode }) {
  const [brands, setBrands] = useState<Brand[]>([]);
  const [selected, setSelected] = useStoredState("brandpr.brandId", "");
  const [actor, setActor] = useStoredState("brandpr.actor", "");
  const [roleValue, setRoleValue] = useStoredState("brandpr.role", "creator");
  const role: ActorRole = roleValue === "reviewer" ? "reviewer" : "creator";
  setIdentity(actor, role);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    setLoading(true);
    api.listBrands().then(
      (page) => { if (live) { setBrands(page.items); setError(null); setLoading(false); } },
      (e) => { if (live) { setError(errorMessage(e)); setLoading(false); } },
    );
    return () => { live = false; };
  }, [tick]);

  const brand = useMemo(() => brands.find((b) => b.id === selected) ?? brands[0] ?? null, [brands, selected]);
  const createBrand = useCallback(async (name: string, description?: string) => {
    const created = await api.createBrand({ name, description: description || null });
    setBrands((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
    setSelected(created.id);
    return created;
  }, [setSelected]);

  const value = useMemo(
    () => ({ brands, brand, loading, error, selectBrand: setSelected, createBrand, reload: () => setTick((t) => t + 1), actor, setActor, role, setRole: (v: ActorRole) => setRoleValue(v) }),
    [brands, brand, loading, error, setSelected, createBrand, actor, setActor, role, setRoleValue],
  );
  return <BrandContext.Provider value={value}>{children}</BrandContext.Provider>;
}
