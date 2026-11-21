/**
 * Small, dependency-free sky maths for drawing.
 *
 * Accuracy is ~0.5° (no precession, nutation or refraction): plenty for
 * illustrations and animations. Exact positions come from the backend API.
 */

import type { Compass, HorizontalPosition } from "@/lib/types";

const DEG = Math.PI / 180;
const COMPASS: Compass[] = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

/** Julian Date for a JavaScript Date. */
export function julianDate(date: Date): number {
  return date.getTime() / 86400000 + 2440587.5;
}

/** Greenwich mean sidereal time in degrees [0, 360). */
export function gmstDegrees(date: Date): number {
  const d = julianDate(date) - 2451545.0;
  const gmst = 280.46061837 + 360.98564736629 * d;
  return ((gmst % 360) + 360) % 360;
}

/** Equatorial (RA/Dec, degrees) → horizontal (azimuth from north via east, altitude). */
export function toHorizontal(
  raDeg: number,
  decDeg: number,
  latDeg: number,
  lonDeg: number,
  date: Date,
): HorizontalPosition {
  const lst = gmstDegrees(date) + lonDeg;
  const ha = (lst - raDeg) * DEG;
  const dec = decDeg * DEG;
  const lat = latDeg * DEG;
  const sinAlt = Math.sin(dec) * Math.sin(lat) + Math.cos(dec) * Math.cos(lat) * Math.cos(ha);
  const alt = Math.asin(Math.max(-1, Math.min(1, sinAlt)));
  const az = Math.atan2(
    -Math.sin(ha) * Math.cos(dec),
    Math.cos(lat) * Math.sin(dec) - Math.sin(lat) * Math.cos(dec) * Math.cos(ha),
  );
  return { az: ((az / DEG) % 360 + 360) % 360, alt: alt / DEG };
}

/** 8-point compass label for an azimuth. */
export function compassFor(azimuth: number): Compass {
  return COMPASS[Math.floor((((azimuth % 360) + 360) % 360 + 22.5) / 45) % 8]!;
}

/**
 * Planisphere projection used by the sky dome: zenith at the centre, horizon
 * on the rim, north up and EAST ON THE LEFT (as seen looking up).
 * Returns pixel coordinates; objects below the horizon land outside the rim.
 */
export function domeProject(
  { az, alt }: HorizontalPosition,
  cx: number,
  cy: number,
  radius: number,
): { x: number; y: number } {
  const r = ((90 - alt) / 90) * radius;
  const a = az * DEG;
  return { x: cx - r * Math.sin(a), y: cy - r * Math.cos(a) };
}

/**
 * Tangent-plane (gnomonic) projection of sky points around their centre,
 * oriented like the sky: east left, north up. Returns coordinates in degrees
 * with y growing upward.
 */
export function chartProject(
  points: Array<{ ra: number; dec: number }>,
): Array<{ x: number; y: number }> {
  if (points.length === 0) return [];
  let sx = 0, sy = 0, sz = 0;
  for (const p of points) {
    sx += Math.cos(p.dec * DEG) * Math.cos(p.ra * DEG);
    sy += Math.cos(p.dec * DEG) * Math.sin(p.ra * DEG);
    sz += Math.sin(p.dec * DEG);
  }
  const ra0 = Math.atan2(sy, sx);
  const dec0 = Math.atan2(sz, Math.hypot(sx, sy));
  return points.map((p) => {
    const ra = p.ra * DEG;
    const dec = p.dec * DEG;
    const cosC = Math.sin(dec0) * Math.sin(dec) + Math.cos(dec0) * Math.cos(dec) * Math.cos(ra - ra0);
    const xi = (Math.cos(dec) * Math.sin(ra - ra0)) / cosC;
    const eta = (Math.cos(dec0) * Math.sin(dec) - Math.sin(dec0) * Math.cos(dec) * Math.cos(ra - ra0)) / cosC;
    return { x: -xi / DEG, y: eta / DEG };
  });
}

/** Fit projected points into a box (preserving aspect), returning pixel coords. */
export function fitToBox(
  points: Array<{ x: number; y: number }>,
  width: number,
  height: number,
  padding: number,
): Array<{ x: number; y: number }> {
  if (points.length === 0) return [];
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  const scale = Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY);
  const offX = (width - spanX * scale) / 2;
  const offY = (height - spanY * scale) / 2;
  return points.map((p) => ({ x: offX + (p.x - minX) * scale, y: offY + (maxY - p.y) * scale }));
}
