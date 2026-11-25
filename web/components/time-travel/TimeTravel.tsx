"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import SkyDome from "@/components/sky/SkyDome";
import { ChevronUpIcon, PauseIcon, PlayIcon, ResetIcon, SunIcon } from "@/components/ui/icons-extra";
import { ApiErrorNotice, ConstellationSkeleton, WakingTelescope } from "@/components/ui/LoadingStates";
import { formatLocation, useLocation } from "@/hooks/useLocation";
import { RANGE_HOURS, useSkyKeyframes } from "@/hooks/useSkyKeyframes";
import type { ConstellationRow } from "@/lib/sky-interp";

const SPEEDS = [0.5, 1, 2, 4] as const; // hours of sky per second of playback

/** Page background that follows the Sun: night → twilight glow → daylight. */
function skyBackground(sun: number): string {
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  const twilight = clamp((sun + 18) / 18); // 0 at astronomical night, 1 at sunrise
  const day = clamp(sun / 10); // 0 at the horizon, 1 when well up
  const mix = (a: number[], b: number[], t: number) => a.map((v, i) => Math.round(v + ((b[i] ?? v) - v) * t));
  const top = mix(mix([5, 7, 15], [28, 26, 70], twilight), [52, 86, 132], day);
  const bottom = mix(mix([10, 15, 36], [120, 64, 52], twilight), [104, 140, 178], day);
  const glow = 0.55 * twilight * (1 - day);
  // Partly see-through at night so the site's starfield shows; solid by day.
  const alpha = (0.55 + 0.45 * Math.max(day, twilight * 0.5)).toFixed(3);
  return [
    `radial-gradient(ellipse 120% 55% at 50% 100%, rgba(255, 150, 80, ${glow.toFixed(3)}), transparent 70%)`,
    `linear-gradient(180deg, rgba(${top.join(",")}, ${alpha}) 0%, rgba(${bottom.join(",")}, ${alpha}) 100%)`,
  ].join(", ");
}

function visibilityBadge(row: ConstellationRow): { label: string; className: string } {
  if (row.visible) return { label: "Visible", className: "border-gold/40 text-gold" };
  if (row.alt > 0) return { label: "Low", className: "border-cyan/40 text-cyan" };
  return { label: "Below", className: "border-line text-muted" };
}

export default function TimeTravel() {
  const { location, ready } = useLocation();
  const sky = useSkyKeyframes(location, ready);
  const [offset, setOffset] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(1);
  const [selected, setSelected] = useState<string | null>("Orion");
  const [hovered, setHovered] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const direction = useRef<1 | -1>(1);
  const lastOffset = useRef(0);

  // Load the snapshots around the current time (and ahead of it).
  useEffect(() => {
    direction.current = offset >= lastOffset.current ? 1 : -1;
    lastOffset.current = offset;
    sky.ensure(offset, direction.current);
  }, [offset, sky.ensure, sky.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Playback: advance the clock every frame; stop at the end of the window.
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      let reachedEnd = false;
      setOffset((o) => {
        const next = o + dt * speed;
        if (next >= RANGE_HOURS) {
          reachedEnd = true;
          return RANGE_HOURS;
        }
        return next;
      });
      if (reachedEnd) setPlaying(false);
      else frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed]);

  const interp = sky.skyAt(offset);
  const highlight = hovered ?? selected;
  const sun = interp?.sunAltitude ?? -30;
  // null until the page is running in the browser (see useSkyKeyframes).
  const moment = useMemo(
    () => (sky.base ? new Date(new Date(sky.base).getTime() + offset * 3600000) : null),
    [sky.base, offset],
  );
  const fmt = useMemo(
    () => ({
      time: new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: location.tz }),
      date: new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: location.tz }),
    }),
    [location.tz],
  );
  const timeText = moment ? fmt.time.format(moment) : "––:––";
  const dateText = moment ? fmt.date.format(moment) : "";

  const togglePlay = useCallback(() => {
    setPlaying((p) => {
      if (!p && offset >= RANGE_HOURS - 0.01) setOffset(-RANGE_HOURS); // replay from the start
      return !p;
    });
  }, [offset]);
  const goNow = useCallback(() => {
    setPlaying(false);
    setOffset(0);
    sky.resetToNow();
  }, [sky]);

  const selectedRow = interp?.rows.find((r) => r.name === selected) ?? null;
  const whenText =
    Math.abs(offset) < 0.05
      ? "Right now"
      : offset > 0
        ? `In ${formatHours(offset)}`
        : `${formatHours(-offset)} ago`;
  const verb = Math.abs(offset) < 0.05 ? "is" : offset > 0 ? "will be" : "was";
  const sunState = sun > -0.833 ? "day" : sun > -12 ? "twilight" : "night";

  const list = interp && (
    <ul className="divide-y divide-line" aria-label="Constellations">
      {[...interp.rows].sort((a, b) => b.alt - a.alt).map((row) => {
        const badge = visibilityBadge(row);
        const isSelected = row.name === selected;
        return (
          <li key={row.name}>
            <button
              type="button"
              onClick={() => setSelected(isSelected ? null : row.name)}
              onMouseEnter={() => setHovered(row.name)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(row.name)}
              onBlur={() => setHovered(null)}
              aria-pressed={isSelected}
              className={`grid min-h-11 w-full grid-cols-[1fr_auto_auto_auto] items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors ${
                isSelected ? "bg-gold/10" : "hover:bg-ink/5"
              }`}
            >
              <span className={isSelected ? "text-gold" : "text-ink"}>{row.name}</span>
              <span className="w-7 text-right font-display text-xs tracking-wider text-muted">{row.direction}</span>
              <span className="w-24 text-right text-xs tabular-nums text-muted">
                {Math.round(row.az)}° · {Math.round(row.alt)}°
              </span>
              <span className={`w-16 rounded-full border px-2 py-0.5 text-center text-[0.65rem] uppercase tracking-wider ${badge.className}`}>
                {badge.label}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );

  return (
    <section
      className="relative min-h-[100svh] pt-[var(--nav-height)] transition-[background] duration-700"
      style={{ background: skyBackground(sun) }}
    >
      <div className="mx-auto grid max-w-[110rem] gap-8 px-5 pb-28 pt-6 sm:px-8 md:pb-12 lg:grid-cols-[minmax(0,1fr)_24rem] lg:px-12">
        <div className="flex flex-col items-center">
          {/* Readout */}
          <div className="mb-4 w-full text-center">
            <h1 className="label-caps mb-2">Time travel · {formatLocation(location)}</h1>
            <p className="font-display text-6xl font-light tabular-nums text-ink sm:text-7xl" aria-live="off">
              {timeText}
            </p>
            <p className="mt-1 text-sm text-muted">
              {dateText}{dateText && " · "}{location.tz.replaceAll("_", " ")}
              <span className="ml-2 tabular-nums text-ink/80">
                {offset === 0 ? "now" : `${offset > 0 ? "+" : "−"}${formatHours(Math.abs(offset))}`}
              </span>
            </p>
            <div className="mt-3 flex min-h-8 justify-center">
              <AnimatePresence>
                {sunState !== "night" && (
                  <motion.p
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="glass flex items-center gap-2 rounded-full px-4 py-1.5 text-xs text-ink"
                    role="status"
                  >
                    <SunIcon size={14} className="text-gold" />
                    {sunState === "day"
                      ? "Sun is up — the stars are there, hidden by daylight"
                      : "Twilight — only the brightest stars show"}
                  </motion.p>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Dome */}
          {/* Sized so readout, dome and controls fit one screen on laptops. */}
          <div className="relative w-full lg:max-w-[max(18rem,min(46rem,calc(100svh-27rem)))]">
            {interp ? (
              <SkyDome
                scene={interp.scene}
                highlight={highlight}
                onConstellationClick={(name) => name && setSelected(name)}
                ariaLabel={`Interactive sky chart for ${timeText}. ${
                  selectedRow ? `${selectedRow.name} is ${Math.round(selectedRow.alt)} degrees up in the ${selectedRow.direction}.` : ""
                }`}
              />
            ) : (
              <div className="flex aspect-square w-full items-center justify-center rounded-full border border-line">
                {sky.status === "waking" ? (
                  <WakingTelescope />
                ) : sky.status === "error" ? (
                  <ApiErrorNotice
                    message={sky.error?.status === null
                      ? "We couldn't reach the AstraGraph server. Check your connection, or try again in a moment."
                      : sky.error?.message ?? "Something went wrong."}
                    onRetry={sky.retry}
                  />
                ) : (
                  <ConstellationSkeleton label="Loading the sky" />
                )}
              </div>
            )}
          </div>

          {selectedRow && (
            <p className="glass mt-4 max-w-xl rounded-full px-5 py-2 text-center text-sm text-ink/80" aria-live="polite">
              {whenText}, <span className="text-gold">{selectedRow.name}</span> {verb} at azimuth{" "}
              <span className="tabular-nums text-ink">{Math.round(selectedRow.az)}°</span> ({selectedRow.direction}), altitude{" "}
              <span className="tabular-nums text-ink">{Math.round(selectedRow.alt)}°</span>
              {selectedRow.alt < 0 ? " — below the horizon." : "."}
            </p>
          )}

          {/* Controls */}
          <div className="glass mt-6 flex w-full max-w-3xl flex-wrap items-center gap-x-4 gap-y-3 rounded-2xl px-4 py-3 sm:flex-nowrap">
            <button
              type="button"
              onClick={togglePlay}
              disabled={!interp}
              aria-label={playing ? "Pause" : "Play"}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gold text-void transition-shadow hover:shadow-[0_0_24px_rgb(245_196_81/0.5)] disabled:opacity-40"
            >
              {playing ? <PauseIcon size={18} /> : <PlayIcon size={18} />}
            </button>
            <label className="flex min-w-0 flex-1 items-center gap-3">
              <span className="sr-only">Hours from now</span>
              <span className="text-xs tabular-nums text-muted">−12h</span>
              <input
                type="range"
                min={-RANGE_HOURS}
                max={RANGE_HOURS}
                step={0.05}
                value={offset}
                onChange={(e) => {
                  setPlaying(false);
                  setOffset(Number(e.target.value));
                }}
                aria-valuetext={`${timeText}, ${offset === 0 ? "now" : `${offset > 0 ? "in" : ""} ${formatHours(Math.abs(offset))}${offset < 0 ? " ago" : ""}`}`}
                className="time-slider min-w-0 flex-1"
              />
              <span className="text-xs tabular-nums text-muted">+12h</span>
            </label>
            <div className="flex items-center gap-1" role="group" aria-label="Playback speed">
              {SPEEDS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSpeed(s)}
                  aria-pressed={speed === s}
                  className={`min-h-9 rounded-full px-2.5 text-xs tabular-nums transition-colors ${
                    speed === s ? "bg-ink/10 text-ink" : "text-muted hover:text-ink"
                  }`}
                >
                  {s === 0.5 ? "½" : s}×
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={goNow}
              className="flex min-h-11 items-center gap-1.5 rounded-full border border-cyan/40 px-4 text-sm text-cyan transition-colors hover:bg-cyan/10"
            >
              <ResetIcon size={15} />
              Now
            </button>
          </div>
        </div>

        {/* Desktop list */}
        <section aria-label="Where the constellations are" className="glass hidden self-start overflow-hidden rounded-2xl lg:sticky lg:top-[calc(var(--nav-height)+1rem)] lg:block">
          <div className="flex items-baseline justify-between px-4 pb-2 pt-4">
            <p className="label-caps">Where are they?</p>
            <p className="text-[0.65rem] text-muted">az · alt</p>
          </div>
          {list ?? <ConstellationSkeleton className="py-10" label="Loading constellations" />}
          <p className="px-4 py-3 text-xs text-muted">Hover a row to find it on the dome; click a constellation to follow it.</p>
        </section>
      </div>

      {/* Mobile bottom sheet */}
      <div className="fixed inset-x-0 bottom-0 z-30 rounded-t-3xl border-t border-line bg-[rgb(8_12_28/0.94)] shadow-[0_-20px_60px_rgb(0_0_0/0.5)] backdrop-blur-xl lg:hidden">
        <button
          type="button"
          onClick={() => setSheetOpen((o) => !o)}
          aria-expanded={sheetOpen}
          aria-controls="constellation-sheet"
          className="flex min-h-12 w-full items-center justify-between px-5"
        >
          <span className="label-caps">Where are they?</span>
          <ChevronUpIcon size={18} className={`text-muted transition-transform ${sheetOpen ? "rotate-180" : ""}`} />
        </button>
        <AnimatePresence initial={false}>
          {sheetOpen && (
            <motion.div
              id="constellation-sheet"
              initial={{ height: 0 }}
              animate={{ height: "auto" }}
              exit={{ height: 0 }}
              transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              className="max-h-[55vh] overflow-y-auto"
            >
              {list}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}

function formatHours(h: number): string {
  const total = Math.round(h * 60);
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  if (hours === 0) return `${minutes} min`;
  if (minutes === 0) return `${hours} ${hours === 1 ? "hour" : "hours"}`;
  return `${hours} h ${minutes} min`;
}
