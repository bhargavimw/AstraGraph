/**
 * Geometry and easing for the Live Camera overlay.
 *
 * `/frame` answers in the pixel space of the image we sent (e.g. 640 px wide).
 * The picture on screen is the original source (camera, photo or demo frame)
 * scaled into its element with object-fit cover or contain, so it may be
 * cropped or letterboxed. `overlayTransform` turns frame pixels into screen
 * pixels for exactly that case.
 *
 * Successive frames are blended: items with the same id (or name) glide from
 * their previous position, new ones fade in, vanished ones fade out.
 */

import type { ApiFrame } from "@/lib/types";

export type FitMode = "cover" | "contain";

export interface OverlayTransform {
  /** Screen px per frame px. */
  scale: number;
  dx: number;
  dy: number;
}

/**
 * Map frame pixels → element pixels.
 * @param source  intrinsic size of what is displayed (videoWidth/naturalWidth)
 * @param frame   size of the image sent to the API (response meta)
 * @param box     the element's on-screen size
 */
export function overlayTransform(
  source: { width: number; height: number },
  frame: { width: number; height: number },
  box: { width: number; height: number },
  mode: FitMode,
): OverlayTransform {
  const fit = mode === "cover"
    ? Math.max(box.width / source.width, box.height / source.height)
    : Math.min(box.width / source.width, box.height / source.height);
  const shownW = source.width * fit;
  const shownH = source.height * fit;
  return {
    scale: fit * (source.width / frame.width),
    dx: (box.width - shownW) / 2,
    dy: (box.height - shownH) / 2,
  };
}

export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

export interface Blended<T> {
  item: T;
  alpha: number;
}

/**
 * Blend two lists of overlay items at progress t (0 → previous, 1 → current).
 * Items found in both (by key) are interpolated with `mix`; the rest fade.
 */
export function blend<T>(
  prev: readonly T[],
  cur: readonly T[],
  key: (item: T) => string | number,
  mix: (a: T, b: T, t: number) => T,
  t: number,
): Blended<T>[] {
  const before = new Map(prev.map((p) => [key(p), p]));
  const out: Blended<T>[] = [];
  const seen = new Set<string | number>();
  for (const c of cur) {
    const k = key(c);
    seen.add(k);
    const p = before.get(k);
    out.push(p ? { item: mix(p, c, t), alpha: 1 } : { item: c, alpha: t });
  }
  for (const p of prev) if (!seen.has(key(p))) out.push({ item: p, alpha: 1 - t });
  return out.filter((b) => b.alpha > 0.01);
}

type Star = ApiFrame["stars"][number];
type Constellation = ApiFrame["constellations"][number];
type Ghost = ApiFrame["ghosts"][number];
type Satellite = ApiFrame["satellites"][number];
type Anomaly = ApiFrame["anomalies"][number];

export const mixStar = (a: Star, b: Star, t: number): Star => ({ ...b, x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t), r: lerp(a.r, b.r, t) });
export const mixGhost = (a: Ghost, b: Ghost, t: number): Ghost => ({ ...b, x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t) });
export const mixAnomaly = (a: Anomaly, b: Anomaly, t: number): Anomaly => ({ ...b, x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t) });
export const mixSatellite = (a: Satellite, b: Satellite, t: number): Satellite => ({
  ...b, x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t),
});
export function mixConstellation(a: Constellation, b: Constellation, t: number): Constellation {
  const sameShape = a.lines.length === b.lines.length;
  return {
    ...b,
    lines: sameShape
      ? b.lines.map((line, i) => {
          const from = a.lines[i]!;
          return [lerp(from[0], line[0], t), lerp(from[1], line[1], t), lerp(from[2], line[2], t), lerp(from[3], line[3], t)];
        })
      : b.lines,
    label: [lerp(a.label[0], b.label[0], t), lerp(a.label[1], b.label[1], t)],
  };
}

/** Ease-out cubic. */
export const easeOut = (t: number): number => 1 - Math.pow(1 - Math.max(0, Math.min(1, t)), 3);
