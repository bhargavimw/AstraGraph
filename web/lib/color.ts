/**
 * Star colours from the B−V colour index (`ci`), following spectral type:
 * blue-white (ci < 0) → white (~0.3) → yellow (~0.6) → orange (~1.0) → red-orange (> 1.4).
 */

export type RGB = readonly [number, number, number];

const STOPS: ReadonlyArray<readonly [number, RGB]> = [
  [-0.3, [155, 188, 255]], // blue-white (O/B)
  [0.0, [202, 218, 255]],
  [0.3, [248, 247, 255]], // white (A/F)
  [0.6, [255, 241, 214]], // yellow (G)
  [1.0, [255, 210, 161]], // orange (K)
  [1.4, [255, 177, 120]], // red-orange (M)
  [2.0, [255, 150, 100]],
];

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));

/** Linear interpolation between the spectral colour stops. */
export function ciToRgb(ci: number): RGB {
  const first = STOPS[0]!;
  const last = STOPS[STOPS.length - 1]!;
  if (ci <= first[0]) return first[1];
  if (ci >= last[0]) return last[1];
  for (let i = 1; i < STOPS.length; i++) {
    const [c1, rgb1] = STOPS[i]!;
    const [c0, rgb0] = STOPS[i - 1]!;
    if (ci <= c1) {
      const t = (ci - c0) / (c1 - c0);
      return [
        Math.round(rgb0[0] + (rgb1[0] - rgb0[0]) * t),
        Math.round(rgb0[1] + (rgb1[1] - rgb0[1]) * t),
        Math.round(rgb0[2] + (rgb1[2] - rgb0[2]) * t),
      ];
    }
  }
  return last[1];
}

export const rgba = ([r, g, b]: RGB, alpha: number): string =>
  `rgba(${r}, ${g}, ${b}, ${clamp(alpha, 0, 1).toFixed(3)})`;

/** Apparent magnitude → drawing radius in CSS px (brighter = larger). */
export function magnitudeToRadius(mag: number, base = 1.0): number {
  return base * clamp(2.6 - 0.45 * mag, 0.35, 4.2);
}

/** A realistic random colour index for background stars (most stars look white-ish). */
export function randomCi(rand: () => number = Math.random): number {
  const r = rand();
  if (r < 0.12) return -0.2 + rand() * 0.2; // hot blue-white
  if (r < 0.62) return 0.1 + rand() * 0.4; // white
  if (r < 0.84) return 0.55 + rand() * 0.25; // yellow
  if (r < 0.96) return 0.9 + rand() * 0.4; // orange
  return 1.4 + rand() * 0.4; // red-orange
}
