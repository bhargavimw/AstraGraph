"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef } from "react";
import { magnitudeToRadius } from "@/lib/color";
import { catalog } from "@/lib/data/catalog";
import { fitTransform, makeChartProjection } from "@/lib/sky-math";
import { drawStar } from "@/lib/star-sprites";
import type { ApiConstellationSummary } from "@/lib/types";
import { prepareContext, useCanvas } from "@/hooks/useCanvas";
import { useReducedMotion } from "@/hooks/useReducedMotion";

/**
 * Large chart of one constellation. Stars are sized by magnitude and coloured
 * by colour index, with the faint real stars around them for context. Lines
 * trace themselves whenever the constellation changes; the brightest stars are
 * labelled with their magnitude. Hovering (or tapping) a star shows a glass
 * tooltip. East is on the left, as when facing the sky.
 */

type ChartStar = ApiConstellationSummary["stars"][number];

const DEFAULT_CI = 0.6;
const KEY_STARS = 4;

/** Plain-words star colour from the B−V colour index. */
export function colourWord(ci: number | null): string {
  if (ci === null) return "";
  if (ci < 0) return "Blue-white";
  if (ci < 0.3) return "White";
  if (ci < 0.6) return "Yellow-white";
  if (ci < 1.0) return "Yellow";
  if (ci < 1.4) return "Orange";
  return "Red-orange";
}

export default function ConstellationChart({
  constellation,
  activeStar,
  onActiveStarChange,
}: {
  constellation: ApiConstellationSummary;
  activeStar: string | null;
  onActiveStarChange: (name: string | null) => void;
}) {
  const { ref, size, visible } = useCanvas();
  const reduced = useReducedMotion();
  const trace = useRef<{ name: string; startedAt: number | null }>({ name: "", startedAt: null });

  const layout = useMemo(() => {
    const { width, height } = size;
    if (width < 2) return null;
    const project = makeChartProjection(constellation.stars);
    const projected = constellation.stars.map((s) => project(s) ?? { x: 0, y: 0 });
    const pad = Math.max(56, Math.min(width, height) * 0.14);
    const fit = fitTransform(projected, width, height, pad);
    const stars = constellation.stars.map((s, i) => ({ star: s, ...fit(projected[i]!) }));
    const own = new Set(constellation.stars.map((s) => s.name));
    const field = catalog.stars.flatMap(([name, ra, dec, mag, ci]) => {
      if (own.has(name) || mag > 4.6) return [];
      const p = project({ ra, dec });
      if (!p) return [];
      const q = fit(p);
      return q.x > -10 && q.x < width + 10 && q.y > -10 && q.y < height + 10 ? [{ ...q, mag, ci }] : [];
    });
    const keyStars = new Set(
      [...constellation.stars].sort((a, b) => a.magnitude - b.magnitude).slice(0, KEY_STARS).map((s) => s.name),
    );
    const centre = {
      x: stars.reduce((t, s) => t + s.x, 0) / stars.length,
      y: stars.reduce((t, s) => t + s.y, 0) / stars.length,
    };
    return { stars, field, keyStars, centre, pos: new Map(stars.map((s) => [s.star.name, s])) };
  }, [constellation, size]);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !layout) return;
    if (trace.current.name !== constellation.name) trace.current = { name: constellation.name, startedAt: null };
    const duration = 700 + constellation.lines.length * 230;

    const draw = (progress: number) => {
      const ctx = prepareContext(canvas, size);
      if (!ctx) return;
      for (const f of layout.field) drawStar(ctx, f.x, f.y, magnitudeToRadius(f.mag, 0.8), f.ci, 0.45);

      // Lines, one after another.
      const drawn = progress * constellation.lines.length;
      ctx.lineCap = "round";
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = "rgba(245, 196, 81, 0.8)";
      ctx.shadowColor = "rgba(245, 196, 81, 0.55)";
      ctx.shadowBlur = 8;
      constellation.lines.forEach(([a, b], i) => {
        const part = Math.max(0, Math.min(1, drawn - i));
        const A = layout.pos.get(a);
        const B = layout.pos.get(b);
        if (part <= 0 || !A || !B) return;
        ctx.beginPath();
        ctx.moveTo(A.x, A.y);
        ctx.lineTo(A.x + (B.x - A.x) * part, A.y + (B.y - A.y) * part);
        ctx.stroke();
      });
      ctx.shadowBlur = 0;

      // Stars, then the active-star ring.
      const starAlpha = Math.min(1, 0.35 + progress * 3);
      for (const { star, x, y } of layout.stars) {
        drawStar(ctx, x, y, magnitudeToRadius(star.magnitude, 1.6), star.ci ?? DEFAULT_CI, starAlpha);
      }
      const active = activeStar ? layout.pos.get(activeStar) : undefined;
      if (active) {
        ctx.strokeStyle = "rgba(92, 225, 230, 0.85)";
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(active.x, active.y, magnitudeToRadius(active.star.magnitude, 1.6) * 2.4 + 8, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Key-star labels with magnitude, fading in as the trace finishes.
      // Each label sits on the side facing away from the figure's centre, with
      // a dark halo so it stays readable over lines and stars.
      const labelAlpha = Math.max(0, Math.min(1, (progress - 0.55) / 0.45));
      if (labelAlpha > 0) {
        ctx.textBaseline = "middle";
        ctx.shadowColor = "rgba(5, 7, 15, 0.95)";
        ctx.shadowBlur = 6;
        for (const { star, x, y } of layout.stars) {
          if (!layout.keyStars.has(star.name) || star.name === activeStar) continue;
          let right = x >= layout.centre.x;
          if (right && x > size.width - 110) right = false;
          if (!right && x < 110) right = true;
          const below = y > layout.centre.y;
          const gap = magnitudeToRadius(star.magnitude, 1.6) + 9;
          const lx = x + (right ? gap : -gap);
          const ly = y + (below ? 14 : -14);
          ctx.textAlign = right ? "left" : "right";
          ctx.fillStyle = `rgba(232, 236, 246, ${0.92 * labelAlpha})`;
          ctx.font = "500 13px var(--font-space-grotesk), system-ui, sans-serif";
          ctx.fillText(star.name, lx, ly - 7);
          ctx.fillStyle = `rgba(139, 149, 176, ${labelAlpha})`;
          ctx.font = "11px var(--font-inter), system-ui, sans-serif";
          ctx.fillText(`mag ${star.magnitude.toFixed(2)}`, lx, ly + 8);
        }
        ctx.shadowBlur = 0;
      }
    };

    if (reduced) {
      draw(1);
      return;
    }
    if (!visible) {
      draw(trace.current.startedAt === null ? 0 : 1);
      return;
    }
    if (trace.current.startedAt === null) trace.current.startedAt = performance.now();
    let frame = 0;
    const tick = () => {
      const p = Math.min(1, (performance.now() - (trace.current.startedAt ?? 0)) / duration);
      draw(1 - Math.pow(1 - p, 2)); // ease out
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [ref, size, visible, reduced, layout, constellation, activeStar]);

  /** Nearest constellation star within reach of the pointer. */
  const hitTest = (clientX: number, clientY: number, reach: number): string | null => {
    const canvas = ref.current;
    if (!canvas || !layout) return null;
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    let best: string | null = null;
    let bestD = reach;
    for (const s of layout.stars) {
      const d = Math.hypot(s.x - x, s.y - y);
      if (d < bestD) {
        bestD = d;
        best = s.star.name;
      }
    }
    return best;
  };

  const active = activeStar && layout ? layout.pos.get(activeStar) : undefined;
  const flipX = active ? active.x > size.width * 0.6 : false;
  const flipY = active ? active.y < 120 : false;

  return (
    <div className="relative h-full w-full">
      <canvas
        ref={ref}
        role="img"
        aria-label={`Chart of ${constellation.name}: ${constellation.stars.length} stars joined by ${constellation.lines.length} lines. Use the star list below to read about each star.`}
        className="block h-full w-full touch-manipulation"
        onPointerMove={(e) => {
          if (e.pointerType !== "mouse") return;
          const hit = hitTest(e.clientX, e.clientY, 24);
          e.currentTarget.style.cursor = hit ? "pointer" : "default";
          if (hit !== activeStar) onActiveStarChange(hit);
        }}
        onPointerLeave={(e) => e.pointerType === "mouse" && onActiveStarChange(null)}
        onClick={(e) => {
          const hit = hitTest(e.clientX, e.clientY, 34);
          onActiveStarChange(hit === activeStar ? null : hit);
        }}
      />
      <AnimatePresence>
        {active && (
          <motion.div
            key={active.star.name}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="glass pointer-events-none absolute z-10 w-60 rounded-2xl px-4 py-3"
            style={{
              left: active.x,
              top: active.y,
              transform: `translate(${flipX ? "calc(-100% - 22px)" : "22px"}, ${flipY ? "8px" : "calc(-100% - 8px)"})`,
            }}
            role="status"
          >
            <StarFacts star={active.star} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function StarFacts({ star }: { star: ChartStar }) {
  const colour = colourWord(star.ci);
  return (
    <>
      <p className="font-display text-base text-ink">{star.name}</p>
      {star.designation && <p className="text-xs text-muted">{star.designation}</p>}
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        <dt className="text-muted">Magnitude</dt>
        <dd className="tabular-nums text-ink">{star.magnitude.toFixed(2)}</dd>
        {star.distance_ly !== null && (
          <>
            <dt className="text-muted">Distance</dt>
            <dd className="tabular-nums text-ink">{star.distance_ly.toLocaleString("en-US")} light-years</dd>
          </>
        )}
        {colour && (
          <>
            <dt className="text-muted">Colour</dt>
            <dd className="text-ink">{colour}</dd>
          </>
        )}
      </dl>
    </>
  );
}
