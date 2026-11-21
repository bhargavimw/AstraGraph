"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { ObserverLocation } from "@/lib/types";

const STORAGE_KEY = "astragraph.location.v1";

export const DEFAULT_LOCATION: ObserverLocation = {
  lat: 40.7128,
  lon: -74.006,
  tz: "America/New_York",
};

interface LocationContextValue {
  location: ObserverLocation;
  setLocation: (next: ObserverLocation) => void;
  /** False until the saved location (if any) has been read from storage. */
  ready: boolean;
}

const LocationContext = createContext<LocationContextValue | null>(null);

export function isValidLocation(value: unknown): value is ObserverLocation {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.lat === "number" && Number.isFinite(v.lat) && v.lat >= -90 && v.lat <= 90 &&
    typeof v.lon === "number" && Number.isFinite(v.lon) && v.lon >= -180 && v.lon <= 180 &&
    typeof v.tz === "string" && v.tz.length > 0
  );
}

export function LocationProvider({ children }: { children: ReactNode }) {
  const [location, setLocationState] = useState<ObserverLocation>(DEFAULT_LOCATION);
  const [ready, setReady] = useState(false);

  // Read after mount so server and first client render match (no hydration mismatch).
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed: unknown = JSON.parse(raw);
        if (isValidLocation(parsed)) setLocationState(parsed);
      }
    } catch {
      /* storage unavailable (private mode) — keep the default */
    }
    setReady(true);
  }, []);

  const setLocation = useCallback((next: ObserverLocation) => {
    setLocationState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* ignore: the location still applies for this visit */
    }
  }, []);

  const value = useMemo(() => ({ location, setLocation, ready }), [location, setLocation, ready]);
  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>;
}

export function useLocation(): LocationContextValue {
  const ctx = useContext(LocationContext);
  if (!ctx) throw new Error("useLocation() must be used inside <LocationProvider>");
  return ctx;
}

/** "40.71°N, 74.01°W" */
export function formatLocation({ lat, lon }: ObserverLocation): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(2)}°${ns}, ${Math.abs(lon).toFixed(2)}°${ew}`;
}
