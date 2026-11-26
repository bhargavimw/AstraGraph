import { ciToRgb, rgba } from "@/lib/color";

/**
 * Pre-rendered radial-gradient star glows, cached per colour-index bucket.
 * Drawing a cached sprite with drawImage is far cheaper than creating a new
 * gradient for every star on every frame.
 */

const SIZE = 64;
const cache = new Map<number, HTMLCanvasElement>();

export function starSprite(ci: number): HTMLCanvasElement {
  const key = Math.round(Math.max(-0.4, Math.min(2.0, ci)) * 10) / 10;
  const hit = cache.get(key);
  if (hit) return hit;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const rgb = ciToRgb(key);
    const mid = SIZE / 2;
    const g = ctx.createRadialGradient(mid, mid, 0, mid, mid, mid);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.1, rgba(rgb, 1));
    g.addColorStop(0.25, rgba(rgb, 0.5));
    g.addColorStop(0.55, rgba(rgb, 0.1));
    g.addColorStop(1, rgba(rgb, 0));
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, SIZE, SIZE);
  }
  cache.set(key, canvas);
  return canvas;
}

/** Draw a star glow centred at (x, y); `radius` is the core radius in CSS px. */
export function drawStar(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  ci: number,
  alpha = 1,
): void {
  const size = radius * 8;
  ctx.globalAlpha = alpha;
  ctx.drawImage(starSprite(ci), x - size / 2, y - size / 2, size, size);
  ctx.globalAlpha = 1;
}
