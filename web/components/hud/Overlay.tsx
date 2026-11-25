"use client";

import { useEffect, type RefObject } from "react";
import { prepareContext, useCanvas } from "@/hooks/useCanvas";
import {
  blend,
  easeOut,
  mixAnomaly,
  mixConstellation,
  mixGhost,
  mixSatellite,
  mixStar,
  overlayTransform,
  type FitMode,
} from "@/lib/overlay";
import type { ApiFrame } from "@/lib/types";

export type Layer = "stars" | "lines" | "ghosts" | "satellites" | "anomalies";
export type Layers = Record<Layer, boolean>;

/** The two latest answers from /frame, and when the newer one arrived. */
export interface FrameHistory {
  prev: ApiFrame | null;
  cur: ApiFrame | null;
  at: number;
}

export const COLORS = {
  star: "92, 220, 120",
  gold: "245, 196, 81",
  cyan: "92, 225, 230",
  red: "255, 92, 92",
  amber: "255, 176, 64",
} as const;

const TWEEN_MS = 280;

/**
 * Canvas drawn over the camera picture. Redrawn every animation frame from the
 * latest /frame answers, gliding each item from where it was in the previous
 * answer, scaled to the picture's displayed rectangle (cropped or letterboxed).
 */
export default function Overlay({
  history,
  sourceSize,
  fit,
  layers,
  reduced,
}: {
  history: RefObject<FrameHistory>;
  /** Intrinsic size of what is on screen (video / image), or null if unknown yet. */
  sourceSize: () => { width: number; height: number } | null;
  fit: FitMode;
  layers: Layers;
  reduced: boolean;
}) {
  const { ref, size } = useCanvas();

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || size.width < 2) return;
    let frame = 0;
    let avoid: Rect[] = [];
    const blocked = (r: Rect) => avoid.some((a) => r.x < a.x + a.w && r.x + r.w > a.x && r.y < a.y + a.h && r.y + r.h > a.y);

    const draw = (now: number) => {
      frame = requestAnimationFrame(draw);
      const ctx = prepareContext(canvas, size);
      const { prev, cur, at } = history.current;
      const source = sourceSize();
      if (!ctx || !cur || !source || source.width === 0) return;

      const tf = overlayTransform(source, cur.meta, size, fit);
      const X = (x: number) => tf.dx + x * tf.scale;
      const Y = (y: number) => tf.dy + y * tf.scale;
      const t = reduced ? 1 : easeOut((now - at) / TWEEN_MS);
      const pulse = reduced ? 0.5 : 0.5 + 0.5 * Math.sin(now / 420);
      const p = prev ?? cur;
      // Controls drawn over the picture (marked data-hud) that labels must not hide under.
      const box = canvas.getBoundingClientRect();
      avoid = [...(canvas.parentElement?.querySelectorAll<HTMLElement>("[data-hud]") ?? [])].map((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.left - box.left - 6, y: r.top - box.top - 6, w: r.width + 12, h: r.height + 12 };
      });

      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      // Constellation lines, node dots and labels (gold).
      if (layers.lines) {
        for (const { item: c, alpha } of blend(p.constellations, cur.constellations, (c) => c.name, mixConstellation, t)) {
          ctx.strokeStyle = `rgba(${COLORS.gold}, ${0.9 * alpha})`;
          ctx.shadowColor = `rgba(${COLORS.gold}, ${0.6 * alpha})`;
          ctx.shadowBlur = 6;
          ctx.lineWidth = 1.6;
          for (const [x1, y1, x2, y2] of c.lines) {
            ctx.beginPath();
            ctx.moveTo(X(x1), Y(y1));
            ctx.lineTo(X(x2), Y(y2));
            ctx.stroke();
          }
          ctx.shadowBlur = 0;
          ctx.fillStyle = `rgba(${COLORS.gold}, ${alpha})`;
          for (const [x1, y1, x2, y2] of c.lines) {
            for (const [x, y] of [[x1, y1], [x2, y2]] as const) {
              ctx.beginPath();
              ctx.arc(X(x), Y(y), 2.2, 0, Math.PI * 2);
              ctx.fill();
            }
          }
          // Above the figure; else below it; else just clear of the control in the way.
          const lx = X(c.label[0]);
          const above = Y(c.label[1]) - 18;
          const below = Y(Math.max(...c.lines.flatMap((l) => [l[1], l[3]]))) + 26;
          const at = (y: number): Rect => ({ x: lx - 110, y: y - 12, w: 220, h: 24 });
          let ly = above;
          if (blocked(at(above))) {
            if (!blocked(at(below))) ly = below;
            else {
              const r = at(above);
              const over = avoid.filter((a) => r.x < a.x + a.w && r.x + r.w > a.x && a.y < r.y + r.h);
              ly = Math.max(...over.map((a) => a.y + a.h)) + 16;
            }
          }
          drawLabel(ctx, c.name, c.confidence, lx, ly + (1 - alpha) * 8, alpha, size.width);
        }
      }

      // Detected stars (green rings).
      if (layers.stars) {
        ctx.lineWidth = 1.2;
        for (const { item: s, alpha } of blend(p.stars, cur.stars, (s) => s.id, mixStar, t)) {
          ctx.strokeStyle = `rgba(${COLORS.star}, ${0.85 * alpha})`;
          ctx.shadowColor = `rgba(${COLORS.star}, ${0.6 * alpha})`;
          ctx.shadowBlur = 5;
          ctx.beginPath();
          ctx.arc(X(s.x), Y(s.y), Math.max(6, s.r * tf.scale + 3), 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.shadowBlur = 0;
      }

      // Ghost (inferred, hidden) stars: dashed cyan rings, slow pulse.
      if (layers.ghosts) {
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1.3;
        ctx.font = "11px var(--font-inter), system-ui, sans-serif";
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        for (const { item: g, alpha } of blend(p.ghosts, cur.ghosts, (g) => g.name, mixGhost, t)) {
          const r = Math.max(8, g.r * tf.scale) * (1 + 0.18 * pulse);
          ctx.strokeStyle = `rgba(${COLORS.cyan}, ${(0.55 + 0.35 * pulse) * alpha})`;
          ctx.beginPath();
          ctx.arc(X(g.x), Y(g.y), r, 0, Math.PI * 2);
          ctx.stroke();
          ctx.fillStyle = `rgba(${COLORS.cyan}, ${0.85 * alpha})`;
          ctx.fillText(`${g.name} (hidden)`, X(g.x) + r + 6, Y(g.y));
        }
        ctx.setLineDash([]);
      }

      // Satellites: fading trail, red marker, velocity arrow, speed label.
      if (layers.satellites) {
        for (const { item: s, alpha } of blend(p.satellites, cur.satellites, (s) => s.id, mixSatellite, t)) {
          const n = s.trail.length;
          for (let i = 1; i < n; i++) {
            const a = s.trail[i - 1]!;
            const b = s.trail[i]!;
            ctx.strokeStyle = `rgba(${COLORS.red}, ${(i / n) * 0.7 * alpha})`;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(X(a[0]), Y(a[1]));
            ctx.lineTo(X(b[0]), Y(b[1]));
            ctx.stroke();
          }
          const x = X(s.x);
          const y = Y(s.y);
          ctx.fillStyle = `rgba(${COLORS.red}, ${alpha})`;
          ctx.shadowColor = `rgba(${COLORS.red}, 0.8)`;
          ctx.shadowBlur = 10;
          ctx.beginPath();
          ctx.arc(x, y, 5, 0, Math.PI * 2);
          ctx.fill();
          ctx.shadowBlur = 0;
          const len = Math.hypot(s.vx, s.vy);
          if (len > 0) {
            const ux = s.vx / len;
            const uy = s.vy / len;
            const ex = x + ux * 42;
            const ey = y + uy * 42;
            ctx.strokeStyle = `rgba(${COLORS.red}, ${0.95 * alpha})`;
            ctx.lineWidth = 1.6;
            ctx.beginPath();
            ctx.moveTo(x + ux * 9, y + uy * 9);
            ctx.lineTo(ex, ey);
            ctx.moveTo(ex, ey);
            ctx.lineTo(ex - ux * 8 - uy * 5, ey - uy * 8 + ux * 5);
            ctx.moveTo(ex, ey);
            ctx.lineTo(ex - ux * 8 + uy * 5, ey - uy * 8 - ux * 5);
            ctx.stroke();
          }
          const unit = s.speed_unit === "deg/s" ? "°/s" : " px/s";
          const text = `Satellite · ${s.speed.toFixed(1)}${unit}${s.direction ? ` ${s.direction}` : ""}`;
          tag(ctx, text, x, y, COLORS.red, alpha, size.width, blocked);
        }
      }

      // Not-in-catalog objects: amber diamonds.
      if (layers.anomalies) {
        for (const { item: a, alpha } of blend(p.anomalies, cur.anomalies, (a) => a.id, mixAnomaly, t)) {
          const x = X(a.x);
          const y = Y(a.y);
          const d = 9;
          ctx.strokeStyle = `rgba(${COLORS.amber}, ${0.95 * alpha})`;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(x, y - d);
          ctx.lineTo(x + d, y);
          ctx.lineTo(x, y + d);
          ctx.lineTo(x - d, y);
          ctx.closePath();
          ctx.stroke();
          tag(ctx, a.label, x, y, COLORS.amber, alpha, size.width, blocked);
        }
      }
    };

    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [ref, size, history, sourceSize, fit, layers, reduced]);

  return <canvas ref={ref} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true" />;
}

/** Constellation name in spaced capitals with a confidence badge. */
function drawLabel(ctx: CanvasRenderingContext2D, name: string, confidence: number, x: number, y: number, alpha: number, width: number) {
  const title = name.toUpperCase().split("").join(" ");
  const badge = `${Math.round(confidence * 100)}%`;
  ctx.font = "500 15px var(--font-space-grotesk), system-ui, sans-serif";
  const tw = ctx.measureText(title).width;
  ctx.font = "600 10px var(--font-inter), system-ui, sans-serif";
  const bw = ctx.measureText(badge).width + 12;
  const total = tw + 8 + bw;
  const left = Math.max(8, Math.min(width - total - 8, x - total / 2));

  ctx.textBaseline = "middle";
  ctx.textAlign = "left";
  ctx.shadowColor = "rgba(5, 7, 15, 0.9)";
  ctx.shadowBlur = 6;
  ctx.font = "500 15px var(--font-space-grotesk), system-ui, sans-serif";
  ctx.fillStyle = `rgba(${COLORS.gold}, ${alpha})`;
  ctx.fillText(title, left, y);
  ctx.shadowBlur = 0;

  const bx = left + tw + 8;
  ctx.fillStyle = `rgba(${COLORS.gold}, ${0.16 * alpha})`;
  ctx.strokeStyle = `rgba(${COLORS.gold}, ${0.55 * alpha})`;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(bx, y - 9, bw, 18, 9);
  ctx.fill();
  ctx.stroke();
  ctx.font = "600 10px var(--font-inter), system-ui, sans-serif";
  ctx.fillStyle = `rgba(${COLORS.gold}, ${alpha})`;
  ctx.fillText(badge, bx + 6, y + 0.5);
}

interface Rect { x: number; y: number; w: number; h: number }

/**
 * Small coloured text tag with a dark halo under a marker at (x, y), kept
 * inside the canvas; moved above the marker if a control would hide it.
 */
function tag(ctx: CanvasRenderingContext2D, text: string, x: number, markerY: number, rgb: string, alpha: number,
  width: number, blocked: (r: Rect) => boolean) {
  ctx.font = "11px var(--font-inter), system-ui, sans-serif";
  const w = ctx.measureText(text).width;
  const left = Math.max(6, Math.min(width - w - 6, x - w / 2));
  // Below the marker, else above it, else beside it (on whichever side is free).
  let y = markerY + 22;
  let lx = left;
  if (blocked({ x: lx, y: y - 8, w, h: 16 })) {
    y = markerY - 22;
    if (blocked({ x: lx, y: y - 8, w, h: 16 })) {
      y = markerY;
      lx = x + 16 + w < width ? x + 16 : x - 16 - w;
    }
  }
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.shadowColor = "rgba(5, 7, 15, 0.95)";
  ctx.shadowBlur = 5;
  ctx.fillStyle = `rgba(${rgb}, ${alpha})`;
  ctx.fillText(text, lx, y);
  ctx.shadowBlur = 0;
}
