import type { ApiSky, Compass, SkyScene } from "@/lib/types";
import { compassFor } from "@/lib/sky-math";

/**
 * Blend two API sky snapshots so stars glide smoothly between keyframes.
 * Azimuth is interpolated the short way round (359° → 1° passes north).
 */

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export function lerpAzimuth(a: number, b: number, t: number): number {
  const delta = ((((b - a) % 360) + 540) % 360) - 180; // shortest signed difference
  return (((a + delta * t) % 360) + 360) % 360;
}

export interface ConstellationRow {
  name: string;
  abbreviation: string;
  az: number;
  alt: number;
  direction: Compass;
  visible: boolean;
}

export interface InterpolatedSky {
  scene: SkyScene;
  rows: ConstellationRow[];
  sunAltitude: number;
}

/** Interpolate snapshot `a` → `b` by `t` (0..1). `b` may be the same as `a`. */
export function interpolateSky(a: ApiSky, b: ApiSky, t: number, minAltitude = 10): InterpolatedSky {
  const bStars = new Map(b.stars.map((s) => [s.name, s]));
  // A star only in one snapshot (crossing the horizon) fades in from/out to that position.
  const names = new Set([...a.stars.map((s) => s.name), ...b.stars.map((s) => s.name)]);
  const aStars = new Map(a.stars.map((s) => [s.name, s]));
  const stars: SkyScene["stars"] = [];
  for (const name of names) {
    const sa = aStars.get(name) ?? bStars.get(name)!;
    const sb = bStars.get(name) ?? sa;
    stars.push({
      name,
      magnitude: sa.magnitude,
      ci: sa.ci ?? 0.6,
      az: lerpAzimuth(sa.az, sb.az, t),
      alt: lerp(sa.alt, sb.alt, t),
    });
  }

  const bCons = new Map(b.constellations.map((c) => [c.name, c]));
  const constellations: SkyScene["constellations"] = [];
  const rows: ConstellationRow[] = [];
  for (const ca of a.constellations) {
    const cb = bCons.get(ca.name) ?? ca;
    const bPoints = new Map(cb.stars.map((s) => [s.name, s]));
    const points: SkyScene["constellations"][number]["points"] = {};
    for (const s of ca.stars) {
      const sb = bPoints.get(s.name) ?? s;
      const position = { az: lerpAzimuth(s.az, sb.az, t), alt: lerp(s.alt, sb.alt, t) };
      points[s.name] = position;
      // Constellation stars are drawn too, even if fainter than the bright-star list.
      if (!aStars.has(s.name) && !bStars.has(s.name)) {
        stars.push({ name: s.name, magnitude: s.magnitude, ci: s.ci ?? 0.6, ...position });
      }
    }
    constellations.push({ name: ca.name, points, lines: ca.lines });
    const az = lerpAzimuth(ca.az, cb.az, t);
    const alt = lerp(ca.alt, cb.alt, t);
    rows.push({ name: ca.name, abbreviation: ca.abbreviation, az, alt, direction: compassFor(az), visible: alt > minAltitude });
  }
  const sunAltitude = lerp(a.sun_altitude, b.sun_altitude, t);
  return { scene: { stars, constellations, sunAltitude }, rows, sunAltitude };
}
