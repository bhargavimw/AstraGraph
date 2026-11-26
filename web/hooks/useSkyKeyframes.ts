"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { interpolateSky, type InterpolatedSky } from "@/lib/sky-interp";
import type { ApiSky, ObserverLocation } from "@/lib/types";

/**
 * Sky snapshots from the API every STEP hours across ±RANGE hours, fetched on
 * demand around the current time (and prefetched ahead in the direction of
 * travel), then blended by `skyAt(offset)` so motion between snapshots is
 * smooth. Changing location (or "Now") cancels every in-flight request and
 * starts over, so stale answers never appear.
 */

export const STEP_HOURS = 0.5;
export const RANGE_HOURS = 12;
const MAX_INDEX = RANGE_HOURS / STEP_HOURS;
const CONCURRENCY = 3;
const PREFETCH = 4;

export type KeyframeStatus = "loading" | "waking" | "ready" | "error";

const clampIndex = (i: number) => Math.max(-MAX_INDEX, Math.min(MAX_INDEX, i));

function roundedNowIso(): string {
  const d = new Date();
  d.setSeconds(0, 0);
  return d.toISOString();
}

export function useSkyKeyframes(location: ObserverLocation, enabled: boolean) {
  // The base time is set in the browser after mount, never during server
  // rendering: the page is pre-rendered at build time, and a build-time clock
  // would not match the visitor's clock (a hydration mismatch).
  const [base, setBase] = useState<string | null>(null);
  useEffect(() => setBase(roundedNowIso()), []);
  const [status, setStatus] = useState<KeyframeStatus>("loading");
  const [error, setError] = useState<ApiError | null>(null);
  const [, setVersion] = useState(0); // bumps when a snapshot arrives

  const cache = useRef(new Map<number, ApiSky>());
  const inFlight = useRef(new Set<number>());
  const queue = useRef<number[]>([]);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const minAltitude = 10;

  const pump = useCallback(() => {
    const ctrl = controller.current;
    if (!ctrl) return;
    const gen = generation.current;
    while (inFlight.current.size < CONCURRENCY && queue.current.length > 0) {
      const index = queue.current.shift()!;
      if (cache.current.has(index) || inFlight.current.has(index)) continue;
      inFlight.current.add(index);
      api
        .sky(location, index * STEP_HOURS, {
          signal: ctrl.signal,
          onWaking: () => gen === generation.current && setStatus((s) => (s === "ready" ? s : "waking")),
        }, base ?? undefined)
        .then((sky) => {
          if (gen !== generation.current) return;
          cache.current.set(index, sky);
          setStatus("ready");
          setError(null);
          setVersion((v) => v + 1);
        })
        .catch((e: unknown) => {
          if (gen !== generation.current || ctrl.signal.aborted) return;
          if (cache.current.size === 0) setStatus("error");
          setError(e instanceof ApiError ? e : new ApiError(String(e), null, false));
        })
        .finally(() => {
          inFlight.current.delete(index);
          if (gen === generation.current) pump();
        });
    }
  }, [location, base]);

  // New location or new base time: cancel everything and start over.
  useEffect(() => {
    if (!enabled || !base) return;
    generation.current += 1;
    controller.current?.abort();
    controller.current = new AbortController();
    cache.current.clear();
    inFlight.current.clear();
    queue.current = [];
    setStatus("loading");
    setError(null);
    setVersion((v) => v + 1);
    return () => controller.current?.abort();
  }, [enabled, location, base]);

  /** Make sure the snapshots around `offset` are loaded; prefetch ahead. */
  const ensure = useCallback(
    (offset: number, direction: 1 | -1 = 1) => {
      if (!enabled || !base || !controller.current) return;
      const lo = clampIndex(Math.floor(offset / STEP_HOURS));
      const hi = clampIndex(Math.ceil(offset / STEP_HOURS));
      const wanted = [lo, hi];
      for (let k = 1; k <= PREFETCH; k++) wanted.push(clampIndex((direction > 0 ? hi : lo) + direction * k));
      // Urgent ones first; skip anything already cached or queued.
      const fresh = wanted.filter((i) => !cache.current.has(i) && !inFlight.current.has(i));
      queue.current = [...new Set([...fresh, ...queue.current])].slice(0, 12);
      pump();
    },
    [enabled, base, pump],
  );

  /** Blended sky at `offset` hours, or null until a nearby snapshot exists. */
  const skyAt = useCallback(
    (offset: number): InterpolatedSky | null => {
      const exact = offset / STEP_HOURS;
      const lo = clampIndex(Math.floor(exact));
      const hi = clampIndex(Math.ceil(exact));
      const a = cache.current.get(lo);
      const b = cache.current.get(hi);
      if (a && b) return interpolateSky(a, b, hi === lo ? 0 : exact - lo, minAltitude);
      const near = a ?? b;
      if (near) return interpolateSky(near, near, 0, minAltitude);
      return null;
    },
    [],
  );

  const resetToNow = useCallback(() => setBase(roundedNowIso()), []);
  const retry = useCallback(() => {
    queue.current = [];
    setStatus("loading");
    setError(null);
    setVersion((v) => v + 1);
  }, []);

  return { base, status, error, ensure, skyAt, resetToNow, retry, loaded: cache.current.size };
}
