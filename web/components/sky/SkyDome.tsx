"use client";

import { useEffect, useRef } from "react";
import { magnitudeToRadius } from "@/lib/color";
import { domeProject } from "@/lib/sky-math";
import { drawStar } from "@/lib/star-sprites";
import type { SkyScene } from "@/lib/types";
import { prepareContext, useCanvas } from "@/hooks/useCanvas";
import { useReducedMotion } from "@/hooks/useReducedMotion";

/**
 * Canvas planetarium chart: zenith in the centre, horizon on the rim, north up
 * and east on the LEFT (as seen when looking up). Altitude rings at 30° and
 * 60°, compass labels, stars coloured by colour index and sized by magnitude,
 * constellation lines, and labels that fade in as a constellation rises.
 *
 * Pass a static `scene`, or `sceneAt(seconds)` to animate. Animation pauses
 * when the dome is off-screen or the tab is hidden; with reduced motion a
 * single frame is drawn.
 */

export interface SkyDomeProps {
  scene?: SkyScene;
  sceneAt?: (seconds: number) => SkyScene;
  highlight?: string | null;
  showLabels?: boolean;
  /** Smaller type and fewer details for small domes. */
  compact?: boolean;
  className?: string;
  ariaLabel?: string;
  /** Called with the constellation under a click (or null for empty sky). */
  onConstellationClick?: (name: string | null) => void;
}

const GOLD = "245, 196, 81";
const INK = "232, 236, 246";

/** Night → twilight → day sky colours for the dome interior, by Sun altitude. */
function domeColors(sunAltitude: number | undefined): { inner: string; outer: string } {
  const s = sunAltitude ?? -30;
  if (s <= -18) return { inner: "rgba(14, 22, 52, 0.85)", outer: "rgba(5, 7, 15, 0.92)" };
  if (s <= -6) {
    const t = (s + 18) / 12; // 0 at astronomical night, 1 at civil twilight
    return {
      inner: `rgba(${Math.round(14 + 30 * t)}, ${Math.round(22 + 18 * t)}, ${Math.round(52 + 40 * t)}, 0.88)`,
      outer: `rgba(${Math.round(5 + 70 * t)}, ${Math.round(7 + 30 * t)}, ${Math.round(15 + 25 * t)}, 0.92)`,
    };
  }
  if (s <= 0) return { inner: "rgba(58, 52, 104, 0.88)", outer: "rgba(150, 82, 52, 0.85)" };
  return { inner: "rgba(70, 104, 150, 0.85)", outer: "rgba(110, 140, 175, 0.85)" };
}

export default function SkyDome({
  scene,
  sceneAt,
  highlight = null,
  showLabels = true,
  compact = false,
  className = "",
  ariaLabel = "Interactive sky chart",
  onConstellationClick,
}: SkyDomeProps) {
  const { ref, size, visible } = useCanvas();
  const reduced = useReducedMotion();
  const started = useRef<number | null>(null);
  // Geometry of the last frame drawn, for hit-testing clicks.
  const lastFrame = useRef<{ scene: SkyScene; cx: number; cy: number; radius: number } | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || size.width < 2) return;

    const draw = (current: SkyScene) => {
      const ctx = prepareContext(canvas, size);
      if (!ctx) return;
      const { width, height } = size;
      const margin = compact ? 18 : 30;
      const radius = Math.min(width, height) / 2 - margin;
      const cx = width / 2;
      const cy = height / 2;
      const font = compact ? 10 : 12;
      lastFrame.current = { scene: current, cx, cy, radius };

      // Dome interior, tinted by the Sun's altitude.
      const colors = domeColors(current.sunAltitude);
      const bg = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
      bg.addColorStop(0, colors.inner);
      bg.addColorStop(1, colors.outer);
      ctx.fillStyle = bg;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fill();

      // Grid: altitude rings at 30° and 60°, meridians.
      ctx.strokeStyle = `rgba(${INK}, 0.08)`;
      ctx.lineWidth = 1;
      for (const alt of [30, 60]) {
        ctx.beginPath();
        ctx.arc(cx, cy, ((90 - alt) / 90) * radius, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.moveTo(cx - radius, cy);
      ctx.lineTo(cx + radius, cy);
      ctx.moveTo(cx, cy - radius);
      ctx.lineTo(cx, cy + radius);
      ctx.stroke();
      // Horizon rim
      ctx.strokeStyle = `rgba(${INK}, 0.22)`;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.stroke();

      // Compass labels (east on the left).
      ctx.fillStyle = `rgba(${INK}, 0.7)`;
      ctx.font = `500 ${font + 1}px var(--font-space-grotesk), system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const labelR = radius + margin * 0.55;
      ctx.fillText("N", cx, cy - labelR);
      ctx.fillText("S", cx, cy + labelR);
      ctx.fillText("E", cx - labelR, cy);
      ctx.fillText("W", cx + labelR, cy);
      if (!compact) {
        ctx.fillStyle = `rgba(${INK}, 0.28)`;
        ctx.font = `${font - 2}px var(--font-inter), system-ui, sans-serif`;
        ctx.fillText("60°", cx + 4, cy - (30 / 90) * radius - 7);
        ctx.fillText("30°", cx + 4, cy - (60 / 90) * radius - 7);
      }

      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.clip();

      // Constellation lines.
      for (const c of current.constellations) {
        const isHighlight = c.name === highlight;
        ctx.strokeStyle = isHighlight ? `rgba(${GOLD}, 0.95)` : `rgba(${INK}, 0.32)`;
        ctx.lineWidth = isHighlight ? 1.8 : 1;
        ctx.shadowColor = isHighlight ? `rgba(${GOLD}, 0.8)` : "transparent";
        ctx.shadowBlur = isHighlight ? 8 : 0;
        ctx.beginPath();
        for (const [a, b] of c.lines) {
          const pa = c.points[a];
          const pb = c.points[b];
          if (!pa || !pb || pa.alt < 0 || pb.alt < 0) continue;
          const A = domeProject(pa, cx, cy, radius);
          const B = domeProject(pb, cx, cy, radius);
          ctx.moveTo(A.x, A.y);
          ctx.lineTo(B.x, B.y);
        }
        ctx.stroke();
      }
      ctx.shadowBlur = 0;

      // Stars.
      const scale = compact ? 0.75 : 1;
      for (const s of current.stars) {
        if (s.alt < 0) continue;
        const p = domeProject(s, cx, cy, radius);
        const horizonFade = Math.min(1, s.alt / 6 + 0.25); // extinction near the horizon
        drawStar(ctx, p.x, p.y, magnitudeToRadius(s.magnitude, scale), s.ci, horizonFade);
      }
      ctx.restore();

      // Constellation names, fading in with altitude.
      if (showLabels) {
        ctx.font = `500 ${font}px var(--font-space-grotesk), system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        for (const c of current.constellations) {
          const up = Object.values(c.points).filter((p) => p.alt > 0);
          if (up.length === 0) continue;
          const top = up.reduce((a, b) => (b.alt > a.alt ? b : a));
          // Only label constellations that are properly up, and keep the label inside the rim.
          const fade = Math.max(0, Math.min(1, (top.alt - 4) / 10));
          if (fade <= 0.02) continue;
          const p = domeProject(top, cx, cy, radius);
          if (Math.hypot(p.x - cx, p.y - 14 - cy) > radius - 4) continue;
          const isHighlight = c.name === highlight;
          ctx.fillStyle = isHighlight ? `rgba(${GOLD}, ${fade})` : `rgba(${INK}, ${0.75 * fade})`;
          ctx.fillText(c.name.toUpperCase().split("").join(" "), p.x, p.y - 8);
        }
      }
    };

    if (!sceneAt) {
      if (scene) draw(scene);
      return;
    }
    if (reduced || !visible) {
      draw(sceneAt(started.current === null ? 0 : (performance.now() - started.current) / 1000));
      return;
    }
    if (started.current === null) started.current = performance.now();
    let frame = 0;
    const loop = () => {
      draw(sceneAt((performance.now() - (started.current ?? 0)) / 1000));
      frame = requestAnimationFrame(loop);
    };
    const onVisibility = () => {
      cancelAnimationFrame(frame);
      if (!document.hidden) frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [ref, size, visible, reduced, scene, sceneAt, highlight, showLabels, compact]);

  /** Constellation whose star is nearest the pointer (within 18 px), if any. */
  const hitTest = (clientX: number, clientY: number): string | null => {
    const frame = lastFrame.current;
    const canvas = ref.current;
    if (!frame || !canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    let best: { name: string; d: number } | null = null;
    for (const c of frame.scene.constellations) {
      for (const p of Object.values(c.points)) {
        if (p.alt < 0) continue;
        const q = domeProject(p, frame.cx, frame.cy, frame.radius);
        const d = Math.hypot(q.x - x, q.y - y);
        if (d < 18 && (!best || d < best.d)) best = { name: c.name, d };
      }
    }
    return best?.name ?? null;
  };

  return (
    <canvas
      ref={ref}
      role="img"
      aria-label={ariaLabel}
      className={`block aspect-square w-full ${className}`}
      onClick={onConstellationClick ? (e) => onConstellationClick(hitTest(e.clientX, e.clientY)) : undefined}
      onPointerMove={
        onConstellationClick
          ? (e) => {
              e.currentTarget.style.cursor = hitTest(e.clientX, e.clientY) ? "pointer" : "default";
            }
          : undefined
      }
    />
  );
}
