"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export interface Resource<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

/** Load data from the API; refetches when deps change; exposes reload(). Ignores stale responses. */
export function useResource<T>(load: (() => Promise<T>) | null, deps: unknown[]): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(Boolean(load));
  const [tick, setTick] = useState(0);
  const seq = useRef(0);
  const loader = useRef(load);
  loader.current = load;

  useEffect(() => {
    const fn = loader.current;
    if (!fn) {
      setLoading(false);
      return;
    }
    const mine = ++seq.current;
    setLoading(true);
    fn().then(
      (d) => {
        if (mine === seq.current) {
          setData(d);
          setError(null);
          setLoading(false);
        }
      },
      (e) => {
        if (mine === seq.current) {
          setError(e instanceof Error ? e : new Error(String(e)));
          setLoading(false);
        }
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function useStoredState(key: string, initial: string): [string, (v: string) => void] {
  const [value, setValue] = useState(initial);
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(key);
      if (stored !== null) setValue(stored);
    } catch {
      /* storage unavailable */
    }
  }, [key]);
  const set = useCallback(
    (v: string) => {
      setValue(v);
      try {
        window.localStorage.setItem(key, v);
      } catch {
        /* storage unavailable */
      }
    },
    [key],
  );
  return [value, set];
}
