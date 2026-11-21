"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type RequestOptions } from "@/lib/api";

export type ResourceStatus = "loading" | "waking" | "ready" | "error";

export interface Resource<T> {
  data: T | null;
  status: ResourceStatus;
  error: ApiError | null;
  /** Fetch again (e.g. from a Retry button). */
  retry: () => void;
}

/**
 * Load API data and track its state. Re-fetches when `key` changes, cancels
 * the previous request (so stale answers never overwrite fresh ones), and
 * reports "waking" while a sleeping server is being retried. Pass `key: null`
 * to skip fetching (e.g. until the saved location has been read).
 */
export function useApiResource<T>(
  key: string | null,
  fetcher: (opts: RequestOptions) => Promise<T>,
): Resource<T> {
  // `forKey` records which request the data answers, so data for a previous
  // key (e.g. the old location) is never shown under a new one.
  const [state, setState] = useState<Omit<Resource<T>, "retry"> & { forKey: string | null }>({
    data: null, status: "loading", error: null, forKey: null,
  });
  const [attempt, setAttempt] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    // Same key (a retry): keep showing the last good data while refreshing.
    // New key: drop the old data straight away.
    const keep = <S extends { data: T | null; forKey: string | null }>(s: S) => (s.forKey === key ? s.data : null);
    setState((s) => ({ data: keep(s), status: "loading", error: null, forKey: keep(s) ? key : null }));
    fetcherRef
      .current({
        signal: controller.signal,
        onWaking: () => setState((s) => ({ ...s, status: "waking" })),
      })
      .then((data) => {
        if (!controller.signal.aborted) setState({ data, status: "ready", error: null, forKey: key });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const apiError = error instanceof ApiError ? error : new ApiError(String(error), null, false);
        setState((s) => ({ data: keep(s), status: "error", error: apiError, forKey: keep(s) ? key : null }));
      });
    return () => controller.abort();
  }, [key, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const { forKey, ...rest } = state;
  return { ...rest, data: forKey === key ? rest.data : null, retry };
}
