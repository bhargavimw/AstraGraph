import { catalog } from "@/lib/data/catalog";
import { toHorizontal } from "@/lib/sky-math";
import type { SkyScene } from "@/lib/types";

/**
 * Build a SkyScene from the bundled catalogue for a time and place
 * (client-side approximation, ~0.5°). Used for demos and decoration; the
 * Time Travel page uses the API's positions.
 */
export function sceneFromCatalog(date: Date, lat: number, lon: number, maxMagnitude = 3.6): SkyScene {
  const stars = catalog.stars
    .filter((row) => row[3] <= maxMagnitude)
    .map(([name, ra, dec, magnitude, ci]) => ({
      name,
      magnitude,
      ci,
      ...toHorizontal(ra, dec, lat, lon, date),
    }));
  const constellations = Object.entries(catalog.constellations).map(([name, c]) => {
    const points: SkyScene["constellations"][number]["points"] = {};
    for (const s of c.stars) points[s.name] = toHorizontal(s.ra, s.dec, lat, lon, date);
    return { name, points, lines: c.lines };
  });
  // Approximate Sun position: good enough to tint the dome.
  const sunAltitude = sunAltitudeApprox(date, lat, lon);
  return { stars, constellations, sunAltitude };
}

/** Low-precision solar position (~1°), for background tinting only. */
export function sunAltitudeApprox(date: Date, lat: number, lon: number): number {
  const d = date.getTime() / 86400000 + 2440587.5 - 2451545.0;
  const g = ((357.529 + 0.98560028 * d) * Math.PI) / 180;
  const q = 280.459 + 0.98564736 * d;
  const L = ((q + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * Math.PI) / 180;
  const e = ((23.439 - 0.00000036 * d) * Math.PI) / 180;
  const ra = (Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L)) * 180) / Math.PI;
  const dec = (Math.asin(Math.sin(e) * Math.sin(L)) * 180) / Math.PI;
  return toHorizontal(((ra % 360) + 360) % 360, dec, lat, lon, date).alt;
}
