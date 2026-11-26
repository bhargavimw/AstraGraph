"use client";

import { useEffect, useMemo } from "react";
import { magnitudeToRadius } from "@/lib/color";
import { getConstellation } from "@/lib/data/catalog";
import { chartProject, fitToBox } from "@/lib/sky-math";
import { drawStar } from "@/lib/star-sprites";
import { prepareContext, useCanvas } from "@/hooks/useCanvas";
import { useReducedMotion } from "@/hooks/useReducedMotion";

/**
 * Looping demo of the Live Camera inside a phone frame: stars fade in, green
 * detection rings pop on, gold constellation lines draw themselves, then the
 * name and confidence appear. Pure canvas animation — no camera needed.
 */

const LOOP_MS = 9000;
const GREEN = "92, 220, 120";
const GOLD = "245, 196, 81";

interface BackgroundStar { x: number; y: number; r: number; a: number; ci: number }

function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
}

export default function CameraDemo() {
  const { ref, size, visible } = useCanvas();
  const reduced = useReducedMotion();
  const orion = getConstellation("Orion");

  const background = useMemo<BackgroundStar[]>(() => {
    const rand = seeded(7);
    return Array.from({ length: 140 }, () => ({
      x: rand(), y: rand(), r: 0.3 + rand() * 0.9, a: 0.2 + rand() * 0.5, ci: rand() * 1.2,
    }));
  }, []);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !orion || size.width < 2) return;
    const { width, height } = size;
    const layout = fitToBox(chartProject(orion.stars), width, height, Math.min(width, height) * 0.16);
    const pos = new Map(orion.stars.map((s, i) => [s.name, layout[i]!]));
    const order = [...orion.stars].sort((a, b) => a.magnitude - b.magnitude).map((s) => s.name);

    const draw = (t: number) => {
      const ctx = prepareContext(canvas, size);
      if (!ctx) return;
      const phase = t % LOOP_MS;
      const fadeOut = phase > LOOP_MS - 900 ? (LOOP_MS - phase) / 900 : 1;
      const shakeX = reduced ? 0 : Math.sin(t / 900) * 1.6;
      const shakeY = reduced ? 0 : Math.cos(t / 1100) * 1.2;

      // Sensor-noise sky
      const sky = ctx.createLinearGradient(0, 0, 0, height);
      sky.addColorStop(0, "#060915");
      sky.addColorStop(1, "#0d1330");
      ctx.fillStyle = sky;
      ctx.fillRect(0, 0, width, height);
      for (const b of background) {
        drawStar(ctx, b.x * width + shakeX, b.y * height + shakeY, b.r, b.ci, b.a);
      }

      // Constellation stars
      const starsIn = Math.min(1, phase / 1200);
      for (const s of orion.stars) {
        const p = pos.get(s.name)!;
        drawStar(ctx, p.x + shakeX, p.y + shakeY, magnitudeToRadius(s.magnitude, 1.1), s.ci, starsIn);
      }

      ctx.save();
      ctx.globalAlpha = fadeOut;
      // Green detection rings, one by one
      order.forEach((name, i) => {
        const start = 1400 + i * 160;
        const k = Math.max(0, Math.min(1, (phase - start) / 400));
        if (k <= 0) return;
        const p = pos.get(name)!;
        const ease = 1 - Math.pow(1 - k, 3);
        ctx.strokeStyle = `rgba(${GREEN}, ${0.9 * ease})`;
        ctx.lineWidth = 1.2;
        ctx.shadowColor = `rgba(${GREEN}, 0.7)`;
        ctx.shadowBlur = 6;
        ctx.beginPath();
        ctx.arc(p.x + shakeX, p.y + shakeY, 7 + (1 - ease) * 10, 0, Math.PI * 2);
        ctx.stroke();
      });
      ctx.shadowBlur = 0;

      // Gold lines drawing themselves
      const lineStart = 3000;
      const perLine = 260;
      orion.lines.forEach(([a, b], i) => {
        const k = Math.max(0, Math.min(1, (phase - lineStart - i * perLine) / perLine));
        if (k <= 0) return;
        const A = pos.get(a)!;
        const B = pos.get(b)!;
        ctx.strokeStyle = `rgba(${GOLD}, 0.9)`;
        ctx.shadowColor = `rgba(${GOLD}, 0.6)`;
        ctx.shadowBlur = 5;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.moveTo(A.x + shakeX, A.y + shakeY);
        ctx.lineTo(A.x + (B.x - A.x) * k + shakeX, A.y + (B.y - A.y) * k + shakeY);
        ctx.stroke();
      });
      ctx.shadowBlur = 0;

      // Name and confidence
      const labelK = Math.max(0, Math.min(1, (phase - (lineStart + orion.lines.length * perLine)) / 600));
      if (labelK > 0) {
        const top = Math.min(...layout.map((p) => p.y));
        ctx.globalAlpha = fadeOut * labelK;
        ctx.fillStyle = `rgb(${GOLD})`;
        ctx.font = "500 15px var(--font-space-grotesk), system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("O R I O N", width / 2 + shakeX, top - 22 + (1 - labelK) * 6);
        ctx.fillStyle = "rgba(232, 236, 246, 0.75)";
        ctx.font = "11px var(--font-inter), system-ui, sans-serif";
        ctx.fillText("confidence 100%", width / 2 + shakeX, top - 6 + (1 - labelK) * 6);
      }
      ctx.restore();

      // HUD corners
      ctx.strokeStyle = "rgba(232, 236, 246, 0.35)";
      ctx.lineWidth = 1.2;
      const m = 14, l = 16;
      for (const [x, y, dx, dy] of [[m, m, 1, 1], [width - m, m, -1, 1], [m, height - m, 1, -1], [width - m, height - m, -1, -1]] as const) {
        ctx.beginPath();
        ctx.moveTo(x, y + dy * l);
        ctx.lineTo(x, y);
        ctx.lineTo(x + dx * l, y);
        ctx.stroke();
      }
    };

    if (reduced || !visible) {
      draw(reduced ? LOOP_MS - 1000 : 0); // reduced motion: show the finished overlay
      return;
    }
    let frame = 0;
    const t0 = performance.now();
    const loop = () => {
      draw(performance.now() - t0);
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [ref, size, visible, reduced, orion, background]);

  return (
    <div className="mx-auto w-[min(19rem,78vw)]">
      <div className="relative rounded-[2.6rem] border border-ink/15 bg-[#05070f] p-2.5 shadow-[0_40px_120px_rgb(0_0_0/0.6),0_0_0_1px_rgb(232_236_246/0.04)]">
        <div className="absolute left-1/2 top-4 z-10 h-1.5 w-16 -translate-x-1/2 rounded-full bg-ink/15" aria-hidden="true" />
        <div className="overflow-hidden rounded-[2.1rem]">
          <canvas
            ref={ref}
            role="img"
            aria-label="Demo: the live camera finding Orion, with green rings on stars and gold constellation lines"
            className="block aspect-[9/19] w-full"
          />
        </div>
      </div>
    </div>
  );
}
