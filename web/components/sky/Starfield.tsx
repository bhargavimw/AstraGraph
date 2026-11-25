"use client";

import { useEffect, useRef } from "react";
import { ciToRgb, randomCi, rgba, type RGB } from "@/lib/color";
import { useReducedMotion } from "@/hooks/useReducedMotion";

/**
 * Fixed, full-viewport animated starfield behind every page.
 *
 * - 400–900 stars, scaled to the viewport area and capped on very dense
 *   (high devicePixelRatio) screens to keep 60 fps.
 * - Each star twinkles on its own sine wave (random phase and speed).
 * - Three depth layers drift slowly and shift with the mouse (or device tilt
 *   on phones, where the browser allows it without a permission prompt).
 * - A shooting star crosses every 8–20 s.
 * - Glows are pre-rendered sprites per colour, drawn with drawImage
 *   (much cheaper than creating a gradient per star per frame).
 * - Rendering stops while the tab is hidden; with reduced motion, a single
 *   static frame is drawn (no twinkle, parallax, drift or shooting stars).
 */

interface Star {
  x: number; // 0..1 across the (padded) field
  y: number;
  layer: 0 | 1 | 2;
  radius: number; // CSS px
  alpha: number; // base brightness
  twinkleSpeed: number; // radians per second
  phase: number;
  sprite: number; // index into sprite list
}

interface ShootingStar {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number; // seconds elapsed
  duration: number;
  length: number;
}

const LAYER_PARALLAX = [6, 14, 26] as const; // px of shift at full pointer deflection
const LAYER_DRIFT = [1.2, 2.4, 4.0] as const; // px per second, upward
const PAD = 0.04; // extra field around the viewport so parallax never shows an edge
const SPRITE_BUCKETS = [-0.15, 0.15, 0.4, 0.65, 1.0, 1.5]; // colour index per sprite
const SPRITE_SIZE = 64;

function makeSprite(rgb: RGB): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = c.height = SPRITE_SIZE;
  const g = c.getContext("2d");
  if (!g) return c;
  const mid = SPRITE_SIZE / 2;
  const grad = g.createRadialGradient(mid, mid, 0, mid, mid, mid);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.08, rgba(rgb, 1));
  grad.addColorStop(0.22, rgba(rgb, 0.45));
  grad.addColorStop(0.5, rgba(rgb, 0.08));
  grad.addColorStop(1, rgba(rgb, 0));
  g.fillStyle = grad;
  g.fillRect(0, 0, SPRITE_SIZE, SPRITE_SIZE);
  return c;
}

function nearestSprite(ci: number): number {
  let best = 0;
  for (let i = 1; i < SPRITE_BUCKETS.length; i++) {
    if (Math.abs(SPRITE_BUCKETS[i]! - ci) < Math.abs(SPRITE_BUCKETS[best]! - ci)) best = i;
  }
  return best;
}

function starCount(width: number, height: number, dpr: number): number {
  const byArea = Math.round((width * height) / 2400);
  const capped = dpr > 2 ? Math.min(byArea, 650) : byArea;
  return Math.max(400, Math.min(900, capped));
}

function createStars(count: number): Star[] {
  const stars: Star[] = [];
  for (let i = 0; i < count; i++) {
    const r = Math.random();
    const layer: Star["layer"] = r < 0.6 ? 0 : r < 0.9 ? 1 : 2;
    // Most stars are faint; a few bright ones per layer.
    const bright = Math.random() < (layer === 2 ? 0.25 : 0.05);
    const ci = randomCi();
    stars.push({
      x: Math.random(),
      y: Math.random(),
      layer,
      radius: (bright ? 1.4 + Math.random() * 1.4 : 0.4 + Math.random() * 0.8) * (0.8 + layer * 0.25),
      alpha: bright ? 0.85 + Math.random() * 0.15 : 0.35 + Math.random() * 0.45,
      twinkleSpeed: 0.6 + Math.random() * 2.2,
      phase: Math.random() * Math.PI * 2,
      sprite: nearestSprite(ci),
    });
  }
  return stars;
}

export default function Starfield() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    const sprites = SPRITE_BUCKETS.map((ci) => makeSprite(ciToRgb(ci)));
    let width = 0;
    let height = 0;
    let dpr = 1;
    let stars: Star[] = [];
    let drift = 0; // accumulated upward drift, px
    const pointer = { x: 0, y: 0 }; // target, -1..1
    const offset = { x: 0, y: 0 }; // eased
    let shooting: ShootingStar | null = null;
    let nextShootAt = performance.now() + 8000 + Math.random() * 12000;
    let frame = 0;
    let last = performance.now();

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2.5);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const wanted = starCount(width, height, dpr);
      if (stars.length !== wanted) stars = createStars(wanted);
      if (reduced) draw(performance.now(), true);
    };

    const spawnShootingStar = () => {
      const angle = (Math.random() * 50 + 15) * (Math.PI / 180); // 15°–65° below horizontal
      const leftToRight = Math.random() < 0.5;
      const speed = 900 + Math.random() * 600; // px/s
      shooting = {
        x: leftToRight ? Math.random() * width * 0.6 : width * 0.4 + Math.random() * width * 0.6,
        y: Math.random() * height * 0.45,
        vx: Math.cos(angle) * speed * (leftToRight ? 1 : -1),
        vy: Math.sin(angle) * speed,
        life: 0,
        duration: 0.7 + Math.random() * 0.5,
        length: 120 + Math.random() * 120,
      };
    };

    const drawShootingStar = (s: ShootingStar) => {
      const progress = s.life / s.duration;
      const fade = progress < 0.15 ? progress / 0.15 : 1 - (progress - 0.15) / 0.85;
      const speed = Math.hypot(s.vx, s.vy);
      const tailX = s.x - (s.vx / speed) * s.length;
      const tailY = s.y - (s.vy / speed) * s.length;
      const grad = ctx.createLinearGradient(s.x, s.y, tailX, tailY);
      grad.addColorStop(0, `rgba(255,255,255,${0.95 * fade})`);
      grad.addColorStop(0.3, `rgba(200,225,255,${0.4 * fade})`);
      grad.addColorStop(1, "rgba(200,225,255,0)");
      ctx.strokeStyle = grad;
      ctx.lineWidth = 1.6;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(tailX, tailY);
      ctx.stroke();
      ctx.globalAlpha = fade;
      ctx.drawImage(sprites[2]!, s.x - 6, s.y - 6, 12, 12);
      ctx.globalAlpha = 1;
    };

    function draw(now: number, still = false) {
      const t = now / 1000;
      ctx!.clearRect(0, 0, width, height);
      const fieldW = width * (1 + PAD * 2);
      const fieldH = height * (1 + PAD * 2);
      for (const s of stars) {
        const px = still ? 0 : -offset.x * LAYER_PARALLAX[s.layer];
        const py = still ? 0 : -offset.y * LAYER_PARALLAX[s.layer];
        let y = s.y * fieldH - (still ? 0 : drift * LAYER_DRIFT[s.layer]);
        y = ((y % fieldH) + fieldH) % fieldH; // wrap vertically
        const x = s.x * fieldW - width * PAD + px;
        const sy = y - height * PAD + py;
        if (x < -10 || x > width + 10 || sy < -10 || sy > height + 10) continue;
        const twinkle = still ? 1 : 0.72 + 0.28 * Math.sin(t * s.twinkleSpeed + s.phase);
        const a = s.alpha * twinkle;
        if (s.radius < 0.9) {
          // Tiny stars: a dot is enough (and much cheaper).
          ctx!.globalAlpha = a;
          ctx!.fillStyle = "#e8ecf6";
          ctx!.fillRect(x - s.radius / 2, sy - s.radius / 2, s.radius, s.radius);
        } else {
          const size = s.radius * 9;
          ctx!.globalAlpha = a;
          ctx!.drawImage(sprites[s.sprite]!, x - size / 2, sy - size / 2, size, size);
        }
      }
      ctx!.globalAlpha = 1;
      if (!still && shooting) drawShootingStar(shooting);
    }

    const loop = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      drift += dt;
      // Ease toward the pointer target (slow and calm).
      offset.x += (pointer.x - offset.x) * Math.min(1, dt * 2.5);
      offset.y += (pointer.y - offset.y) * Math.min(1, dt * 2.5);
      if (shooting) {
        shooting.life += dt;
        shooting.x += shooting.vx * dt;
        shooting.y += shooting.vy * dt;
        if (shooting.life >= shooting.duration) shooting = null;
      } else if (now >= nextShootAt) {
        spawnShootingStar();
        nextShootAt = now + 8000 + Math.random() * 12000;
      }
      draw(now);
      frame = requestAnimationFrame(loop);
    };

    const start = () => {
      cancelAnimationFrame(frame);
      last = performance.now();
      frame = requestAnimationFrame(loop);
    };
    const onVisibility = () => {
      if (document.hidden) cancelAnimationFrame(frame);
      else if (!reduced) start();
    };
    const onPointer = (e: PointerEvent) => {
      pointer.x = (e.clientX / width) * 2 - 1;
      pointer.y = (e.clientY / height) * 2 - 1;
    };
    const onTilt = (e: DeviceOrientationEvent) => {
      if (e.gamma == null || e.beta == null) return;
      pointer.x = Math.max(-1, Math.min(1, e.gamma / 30));
      pointer.y = Math.max(-1, Math.min(1, (e.beta - 45) / 30));
    };

    // Start once the page has finished its own work (idle), so the starfield
    // never competes with the first render; it then fades in.
    const boot = () => {
      resize();
      window.addEventListener("resize", resize);
      canvas.style.opacity = "1";
      if (reduced) {
        draw(performance.now(), true);
      } else {
        window.addEventListener("pointermove", onPointer, { passive: true });
        // iOS needs an explicit permission prompt for tilt; we don't prompt,
        // so tilt parallax applies only where the browser allows it freely.
        window.addEventListener("deviceorientation", onTilt, { passive: true });
        document.addEventListener("visibilitychange", onVisibility);
        start();
      }
    };
    const hasIdle = typeof window.requestIdleCallback === "function";
    const idle: number = hasIdle ? window.requestIdleCallback(boot, { timeout: 1200 }) : window.setTimeout(boot, 300);

    return () => {
      if (hasIdle) window.cancelIdleCallback(idle);
      else window.clearTimeout(idle);
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("deviceorientation", onTilt);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [reduced]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      style={{ opacity: 0 }}
      className="pointer-events-none fixed inset-0 -z-10 h-full w-full transition-opacity duration-1000"
    />
  );
}
