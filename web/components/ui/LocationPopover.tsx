"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { CheckIcon, CrosshairIcon, PinIcon } from "@/components/ui/icons";
import { formatLocation, isValidLocation, useLocation } from "@/hooks/useLocation";
import type { ObserverLocation } from "@/lib/types";

/** Nav button showing the current place; opens a glass popover to change it. */
export default function LocationPopover({
  align = "right",
  side = "down",
}: {
  align?: "left" | "right";
  /** Open below the button (nav bar) or above it (bottom of the mobile menu). */
  side?: "down" | "up";
}) {
  const { location, setLocation } = useLocation();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({ lat: "", lon: "", tz: "" });
  const [status, setStatus] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const ids = { panel: useId(), lat: useId(), lon: useId(), tz: useId() };

  const zones = useMemo<string[]>(() => {
    try {
      return Intl.supportedValuesOf("timeZone");
    } catch {
      return ["UTC"];
    }
  }, []);

  // Fill the form with the saved location whenever it opens.
  useEffect(() => {
    if (!open) return;
    setDraft({ lat: String(location.lat), lon: String(location.lon), tz: location.tz });
    setStatus(null);
  }, [open, location]);

  // Close on Escape or a click outside.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onPointer = (e: PointerEvent) => {
      const target = e.target as Node;
      if (!panelRef.current?.contains(target) && !buttonRef.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  const useMyLocation = () => {
    if (!("geolocation" in navigator)) {
      setStatus("Your browser doesn't share location. Enter it by hand.");
      return;
    }
    setLocating(true);
    setStatus("Finding you…");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setDraft({
          lat: pos.coords.latitude.toFixed(4),
          lon: pos.coords.longitude.toFixed(4),
          tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
        });
        setStatus("Found you. Press Save to use this location.");
        setLocating(false);
      },
      (err) => {
        setStatus(
          err.code === err.PERMISSION_DENIED
            ? "Location permission was denied. Enter it by hand."
            : "Couldn't get your location. Enter it by hand.",
        );
        setLocating(false);
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
    );
  };

  const candidate: ObserverLocation = {
    lat: Number(draft.lat),
    lon: Number(draft.lon),
    tz: draft.tz,
  };
  const valid = draft.lat.trim() !== "" && draft.lon.trim() !== "" && isValidLocation(candidate)
    && isUsableTimeZone(candidate.tz);
  // Browsers spell some zones differently (Chrome lists "Asia/Calcutta" for
  // "Asia/Kolkata"), so keep the current value selectable even if not listed.
  const options = draft.tz && !zones.includes(draft.tz) ? [draft.tz, ...zones] : zones;

  const save = () => {
    if (!valid) return;
    setLocation(candidate);
    setOpen(false);
    buttonRef.current?.focus();
  };

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={ids.panel}
        aria-label={`Observing location: ${formatLocation(location)}. Change location`}
        className="flex items-center gap-2 rounded-full border border-line px-3.5 py-1.5 text-[0.8rem] text-muted transition-colors duration-300 hover:border-gold/50 hover:text-ink"
      >
        <PinIcon size={15} className="text-gold" />
        <span className="tabular-nums">{formatLocation(location)}</span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            ref={panelRef}
            id={ids.panel}
            role="dialog"
            aria-label="Observing location"
            initial={{ opacity: 0, y: side === "down" ? -6 : 6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: side === "down" ? -6 : 6, scale: 0.98 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className={`glass absolute z-50 w-[min(20rem,calc(100vw-2rem))] rounded-2xl p-5 ${
              side === "down" ? "top-[calc(100%+0.75rem)]" : "bottom-[calc(100%+0.75rem)]"
            } ${align === "right" ? "right-0" : "left-0"}`}
          >
            <p className="label-caps mb-4">Observing from</p>

            <div className="grid grid-cols-2 gap-3">
              <Field id={ids.lat} label="Latitude" hint="−90 to 90">
                <input
                  id={ids.lat}
                  inputMode="decimal"
                  value={draft.lat}
                  onChange={(e) => setDraft((d) => ({ ...d, lat: e.target.value }))}
                  className="field-input"
                />
              </Field>
              <Field id={ids.lon} label="Longitude" hint="−180 to 180">
                <input
                  id={ids.lon}
                  inputMode="decimal"
                  value={draft.lon}
                  onChange={(e) => setDraft((d) => ({ ...d, lon: e.target.value }))}
                  className="field-input"
                />
              </Field>
            </div>

            <Field id={ids.tz} label="Time zone" className="mt-3">
              <select
                id={ids.tz}
                value={draft.tz}
                onChange={(e) => setDraft((d) => ({ ...d, tz: e.target.value }))}
                className="field-input"
              >
                {options.map((z) => (
                  <option key={z} value={z} className="bg-deep">
                    {z.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </Field>

            <button
              type="button"
              onClick={useMyLocation}
              disabled={locating}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-full border border-cyan/40 px-4 py-2 text-sm text-cyan transition-colors duration-300 hover:bg-cyan/10 disabled:opacity-60"
            >
              <CrosshairIcon size={16} />
              {locating ? "Locating…" : "Use my location"}
            </button>

            <p className="mt-3 min-h-[1.25rem] text-xs text-muted" role="status" aria-live="polite">
              {status ?? (valid ? "" : "Check the latitude, longitude and time zone.")}
            </p>

            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-full px-4 py-2 text-sm text-muted transition-colors hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={save}
                disabled={!valid}
                className="flex items-center gap-1.5 rounded-full bg-gold px-4 py-2 text-sm font-medium text-void transition-[box-shadow,opacity] duration-300 hover:shadow-[0_0_24px_rgb(245_196_81/0.45)] disabled:opacity-40"
              >
                <CheckIcon size={15} />
                Save
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** True if the browser can format dates in this IANA time zone. */
function isUsableTimeZone(tz: string): boolean {
  try {
    new Intl.DateTimeFormat("en", { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

function Field({
  id, label, hint, className = "", children,
}: { id: string; label: string; hint?: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 flex items-baseline justify-between text-xs text-muted">
        <span>{label}</span>
        {hint && <span className="text-[0.65rem] opacity-70">{hint}</span>}
      </label>
      {children}
    </div>
  );
}
