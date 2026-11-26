/**
 * Shared types. Catalogue types mirror the repository's data files
 * (data/constellations.json, data/constellation_info.json); API types at the
 * end are inferred from the response schemas in lib/api-schemas.ts.
 */

import type { z } from "zod";
import type {
  ConstellationDetailSchema,
  ConstellationSummarySchema,
  DemoSkyInfoSchema,
  FrameResponseSchema,
  MoonSchema,
  QuizGradeSchema,
  QuizNewSchema,
  SkyResponseSchema,
  SkyStarSchema,
  TonightResponseSchema,
} from "@/lib/api-schemas";

/** Observer location shared through `useLocation()`. */
export interface ObserverLocation {
  /** Latitude in degrees, north positive, [-90, 90]. */
  lat: number;
  /** Longitude in degrees, east positive, [-180, 180]. */
  lon: number;
  /** IANA time zone, e.g. "America/New_York". */
  tz: string;
}

/** A catalog star as stored in data/constellations.json (J2000, degrees). */
export interface CatalogStar {
  name: string;
  designation?: string;
  ra: number;
  dec: number;
  magnitude: number;
}

/** A constellation stick figure as stored in data/constellations.json. */
export interface ConstellationRecord {
  abbreviation: string;
  stars: CatalogStar[];
  lines: [string, string][];
}

/** A star in the bundled catalogue (lib/data/sky-catalog.json), with colour index. */
export interface ChartStar extends CatalogStar {
  /** B−V colour index (drives star colour). */
  ci: number;
}

/** A constellation in the bundled catalogue. */
export interface ChartConstellation {
  abbreviation: string;
  stars: ChartStar[];
  lines: [string, string][];
  mythology: string;
}

/** Compact bright-star row: [name, ra°, dec°, magnitude, ci]. */
export type BrightStarRow = [string, number, number, number, number];

export interface SkyCatalog {
  source: string;
  stars: BrightStarRow[];
  constellations: Record<string, ChartConstellation>;
}

/** A point on the sky as seen by the observer (degrees). */
export interface HorizontalPosition {
  az: number;
  alt: number;
}

/** Everything <SkyDome /> needs to draw one moment of sky. */
export interface SkyScene {
  stars: Array<HorizontalPosition & { name: string; magnitude: number; ci: number }>;
  constellations: Array<{
    name: string;
    /** Star name → position, for drawing the lines. */
    points: Record<string, HorizontalPosition>;
    lines: [string, string][];
  }>;
  /** Sun altitude in degrees (drives the background tint); optional. */
  sunAltitude?: number;
}

/** Compass directions in 45° steps. */
export type Compass = "N" | "NE" | "E" | "SE" | "S" | "SW" | "W" | "NW";

/** "Tonight's sky" summary shown on the home page. */
export interface TonightSummary {
  darkness:
    | { state: "dark"; minutesUntilDawn: number }
    | { state: "light"; minutesUntilDark: number }
    | { state: "never-dark" };
  moon: {
    phaseName: string;
    /** Fraction of the disc lit, 0–1. */
    illumination: number;
    /** True while the Moon is growing (lit on the right, seen from the north). */
    waxing: boolean;
  };
  best: { name: string; altitude: number; azimuth: number; direction: Compass } | null;
  brightestStars: string[];
  upTonight: Array<{ name: string; direction: Compass }>;
}

// ------------------------------------------------------------------ API types
// Inferred from the runtime schemas in lib/api-schemas.ts, so the types and the
// validation can never drift apart.

export type ApiMoon = z.infer<typeof MoonSchema>;
export type ApiSkyStar = z.infer<typeof SkyStarSchema>;
export type ApiSky = z.infer<typeof SkyResponseSchema>;
export type ApiTonight = z.infer<typeof TonightResponseSchema>;
export type ApiConstellationSummary = z.infer<typeof ConstellationSummarySchema>;
export type ApiConstellationDetail = z.infer<typeof ConstellationDetailSchema>;
export type ApiQuiz = z.infer<typeof QuizNewSchema>;
export type ApiQuizGrade = z.infer<typeof QuizGradeSchema>;
export type ApiFrame = z.infer<typeof FrameResponseSchema>;
export type ApiDemoSkyInfo = z.infer<typeof DemoSkyInfoSchema>;
