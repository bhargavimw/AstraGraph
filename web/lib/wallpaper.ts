/**
 * Wallpaper gallery: types for public/manifest.json (pre-rendered by the
 * AstraGraph backend; see docs/frontend_handoff.md on feature/wallpaper-gallery)
 * and small helpers for filtering. Fully static — no API is involved.
 */

export interface Wallpaper {
  id: string;
  title: string;
  city: string;
  country: string;
  lat: number;
  lon: number;
  timezone: string;
  datetime_local: string;
  datetime_utc: string;
  style: string;
  aspect: string;
  width: number;
  height: number;
  filename: string;
  path: string;
  thumbnail: string;
  bytes: number;
  featured: boolean;
  hemisphere: string;
  tags: string[];
  visible_constellations: string[];
  moon_phase: string;
  caption: string;
}

export interface GalleryManifest {
  generated_at: string;
  engine: string;
  count: number;
  wallpapers: Wallpaper[];
}

export const STYLES = ["classic", "minimal", "vintage", "aurora"] as const;

/** City id used in URLs: the id without its style and aspect ("nyc_classic_phone" → "nyc"). */
export function cityId(w: Wallpaper): string {
  const suffix = `_${w.style}_${w.aspect}`;
  return w.id.endsWith(suffix) ? w.id.slice(0, -suffix.length) : w.city.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

export interface CityOption {
  id: string;
  name: string;
  country: string;
}

/** Cities in display order: Indian cities first (grouped together), then the rest A–Z. */
export function citiesOf(wallpapers: Wallpaper[]): CityOption[] {
  const byId = new Map<string, CityOption>();
  for (const w of wallpapers) byId.set(cityId(w), { id: cityId(w), name: w.city, country: w.country });
  return [...byId.values()].sort((a, b) => {
    const ai = a.country === "India" ? 0 : 1;
    const bi = b.country === "India" ? 0 : 1;
    return ai - bi || a.name.localeCompare(b.name);
  });
}

/** Wallpaper with style order applied (classic, minimal, vintage, aurora). */
export const styleRank = (style: string): number => {
  const i = (STYLES as readonly string[]).indexOf(style);
  return i === -1 ? STYLES.length : i;
};

export const capitalise = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

/** Light runtime check so a broken manifest shows an error instead of crashing. */
export function isManifest(v: unknown): v is GalleryManifest {
  if (typeof v !== "object" || v === null) return false;
  const m = v as Record<string, unknown>;
  return Array.isArray(m.wallpapers) && m.wallpapers.every((w: unknown) => {
    if (typeof w !== "object" || w === null) return false;
    const x = w as Record<string, unknown>;
    return typeof x.id === "string" && typeof x.path === "string" && typeof x.thumbnail === "string"
      && typeof x.filename === "string" && typeof x.city === "string" && typeof x.style === "string"
      && typeof x.featured === "boolean" && Array.isArray(x.visible_constellations);
  });
}
