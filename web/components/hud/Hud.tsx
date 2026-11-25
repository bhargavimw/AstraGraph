"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { COLORS, type Layer, type Layers } from "@/components/hud/Overlay";
import { LayersIcon } from "@/components/ui/icons-extra";

/** Viewfinder corners and a small centre crosshair. */
export function HudFrame() {
  const corner = "absolute h-7 w-7 border-ink/45";
  return (
    <div className="pointer-events-none absolute inset-x-4 bottom-4 top-[calc(var(--nav-height)+0.5rem)] sm:inset-x-8 sm:bottom-8" aria-hidden="true">
      <span className={`${corner} left-0 top-0 border-l-[1.5px] border-t-[1.5px]`} />
      <span className={`${corner} right-0 top-0 border-r-[1.5px] border-t-[1.5px]`} />
      <span className={`${corner} bottom-0 left-0 border-b-[1.5px] border-l-[1.5px]`} />
      <span className={`${corner} bottom-0 right-0 border-b-[1.5px] border-r-[1.5px]`} />
      <svg className="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-ink/40" viewBox="0 0 32 32">
        <path d="M16 4v8M16 20v8M4 16h8M20 16h8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        <circle cx="16" cy="16" r="1.4" fill="currentColor" />
      </svg>
    </div>
  );
}

export interface HudStats {
  stars: number;
  constellations: number;
  satellites: number;
  anomalies: number;
  fps: number | null;
  latencyMs: number | null;
}

export type Link = "idle" | "waking" | "ok" | "error";

/** Glass readout (bottom-left): what is being found, and how fast. */
export function Readout({ stats, link, names }: { stats: HudStats; link: Link; names: string[] }) {
  const linkText = { idle: "Idle", waking: "Waking server", ok: "Live", error: "Reconnecting" }[link];
  const linkColor = { idle: "bg-muted", waking: "bg-gold animate-pulse", ok: "bg-[rgb(92_220_120)]", error: "bg-[rgb(255_92_92)] animate-pulse" }[link];
  const rows: Array<[string, string]> = [
    ["Stars", String(stats.stars)],
    ["Constellations", String(stats.constellations)],
    ["Satellites", String(stats.satellites)],
    ["Anomalies", String(stats.anomalies)],
    ["FPS", stats.fps === null ? "–" : stats.fps.toFixed(1)],
    ["Latency", stats.latencyMs === null ? "–" : `${Math.round(stats.latencyMs)} ms`],
  ];
  return (
    <div className="glass w-[9.5rem] rounded-2xl !bg-[rgb(8_12_28/0.82)] px-3 py-2.5 text-[0.7rem] sm:w-52 sm:px-4 sm:py-3 sm:text-xs">
      <p className="mb-2 flex items-center gap-2 font-display text-[0.65rem] uppercase tracking-[0.24em] text-muted">
        <span className={`h-1.5 w-1.5 rounded-full ${linkColor}`} />
        {linkText}
      </p>
      <dl className="grid grid-cols-[1fr_auto] gap-x-2 gap-y-0.5 sm:gap-x-3 sm:gap-y-1">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="text-right tabular-nums text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      {names.length > 0 && (
        <p className="mt-2 truncate border-t border-line pt-2 text-gold" title={names.join(", ")}>{names.join(", ")}</p>
      )}
    </div>
  );
}

const LEGEND: Array<{ layer: Layer; label: string; color: string; shape: "ring" | "line" | "dashed" | "dot" | "diamond" }> = [
  { layer: "stars", label: "Detected stars", color: COLORS.star, shape: "ring" },
  { layer: "lines", label: "Constellations", color: COLORS.gold, shape: "line" },
  { layer: "ghosts", label: "Hidden stars (inferred)", color: COLORS.cyan, shape: "dashed" },
  { layer: "satellites", label: "Satellites", color: COLORS.red, shape: "dot" },
  { layer: "anomalies", label: "Not in catalog", color: COLORS.amber, shape: "diamond" },
];

function Swatch({ color, shape }: { color: string; shape: (typeof LEGEND)[number]["shape"] }) {
  const c = `rgb(${color})`;
  return (
    <svg viewBox="0 0 20 20" className="h-5 w-5 shrink-0" aria-hidden="true">
      {shape === "ring" && <circle cx="10" cy="10" r="6" fill="none" stroke={c} strokeWidth="1.5" />}
      {shape === "dashed" && <circle cx="10" cy="10" r="6" fill="none" stroke={c} strokeWidth="1.5" strokeDasharray="3 2.5" />}
      {shape === "line" && (
        <>
          <path d="M3 15 10 6l7 5" fill="none" stroke={c} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="3" cy="15" r="1.6" fill={c} /><circle cx="10" cy="6" r="1.6" fill={c} /><circle cx="17" cy="11" r="1.6" fill={c} />
        </>
      )}
      {shape === "dot" && <circle cx="10" cy="10" r="4" fill={c} />}
      {shape === "diamond" && <path d="M10 3.5 16.5 10 10 16.5 3.5 10Z" fill="none" stroke={c} strokeWidth="1.5" />}
    </svg>
  );
}

/** Collapsible legend with one show/hide switch per overlay layer. */
export function Legend({ layers, onToggle, defaultOpen }: { layers: Layers; onToggle: (layer: Layer) => void; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="flex flex-col items-end gap-2">
      <AnimatePresence>
        {open && (
          <motion.ul
            id="hud-legend"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.2 }}
            className="glass w-64 rounded-2xl p-2"
          >
            {LEGEND.map(({ layer, label, color, shape }) => (
              <li key={layer}>
                <button
                  type="button"
                  role="switch"
                  aria-checked={layers[layer]}
                  onClick={() => onToggle(layer)}
                  className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-sm transition-colors hover:bg-ink/5"
                >
                  <Swatch color={color} shape={shape} />
                  <span className={`flex-1 ${layers[layer] ? "text-ink" : "text-muted line-through decoration-muted/50"}`}>{label}</span>
                  <span className={`relative h-5 w-9 rounded-full transition-colors ${layers[layer] ? "bg-gold/80" : "bg-ink/15"}`}>
                    <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-void transition-[left] duration-200 ${layers[layer] ? "left-[1.125rem]" : "left-0.5"}`} />
                  </span>
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="hud-legend"
        className="glass flex min-h-11 items-center gap-2 rounded-full px-4 text-sm text-ink transition-colors hover:text-gold"
      >
        <LayersIcon size={18} />
        Legend
      </button>
    </div>
  );
}
