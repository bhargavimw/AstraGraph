"use client";

import { useEffect, useRef } from "react";
import { magnitudeToRadius } from "@/lib/color";
import { chartProject, fitToBox } from "@/lib/sky-math";
import { drawStar } from "@/lib/star-sprites";
import type { ChartConstellation } from "@/lib/types";
import { prepareContext, useCanvas } from "@/hooks/useCanvas";
import { useReducedMotion } from "@/hooks/useReducedMotion";

/**
 * A constellation chart whose lines trace themselves one after another when
 * it scrolls into view (or when `constellation` changes). Stars are coloured
 * by colour index and sized by magnitude; east is on the left, as in the sky.
 */
export default function ConstellationTrace({
  constellation,
  name,
  durationMs = 2600,
  showNames = false,
  className = "",
}: {
  constellation: ChartConstellation;
  name: string;
  durationMs?: number;
  showNames?: boolean;
  className?: string;
}) {
  const { ref, size, visible } = useCanvas();
  const reduced = useReducedMotion();
  const startedAt = useRef<number | null>(null);
  const lastName = useRef<string | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || size.width < 2) return;
    if (lastName.current !== name) {
      lastName.current = name;
      startedAt.current = null; // retrace when the constellation changes
    }
    const projected = fitToBox(chartProject(constellation.stars), size.width, size.height, 36);
    const pos = new Map(constellation.stars.map((s, i) => [s.name, projected[i]!]));

    const draw = (progress: number) => {
      const ctx = prepareContext(canvas, size);
      if (!ctx) return;
      const total = constellation.lines.length;
      const drawnLines = progress * total;
      ctx.lineCap = "round";
      ctx.strokeStyle = "rgba(245, 196, 81, 0.85)";
      ctx.shadowColor = "rgba(245, 196, 81, 0.6)";
      ctx.shadowBlur = 6;
      ctx.lineWidth = 1.4;
      constellation.lines.forEach(([a, b], i) => {
        const part = Math.max(0, Math.min(1, drawnLines - i));
        if (part <= 0) return;
        const A = pos.get(a)!;
        const B = pos.get(b)!;
        ctx.beginPath();
        ctx.moveTo(A.x, A.y);
        ctx.lineTo(A.x + (B.x - A.x) * part, A.y + (B.y - A.y) * part);
        ctx.stroke();
      });
      ctx.shadowBlur = 0;
      const starAlpha = Math.min(1, progress * 4 + 0.35);
      for (const s of constellation.stars) {
        const p = pos.get(s.name)!;
        drawStar(ctx, p.x, p.y, magnitudeToRadius(s.magnitude, 1.25), s.ci, starAlpha);
        if (showNames) {
          ctx.fillStyle = `rgba(232, 236, 246, ${0.7 * Math.min(1, progress * 1.5)})`;
          ctx.font = "12px var(--font-inter), system-ui, sans-serif";
          ctx.textAlign = "left";
          ctx.textBaseline = "middle";
          ctx.fillText(s.name, p.x + 10, p.y - 10);
        }
      }
    };

    if (reduced) {
      draw(1);
      return;
    }
    if (!visible) {
      draw(startedAt.current === null ? 0 : 1);
      return;
    }
    if (startedAt.current === null) startedAt.current = performance.now();
    let frame = 0;
    const tick = () => {
      const p = Math.min(1, (performance.now() - (startedAt.current ?? 0)) / durationMs);
      draw(p);
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [ref, size, visible, reduced, constellation, name, durationMs, showNames]);

  return (
    <canvas
      ref={ref}
      role="img"
      aria-label={`${name} constellation chart`}
      className={`block h-full w-full ${className}`}
    />
  );
}
