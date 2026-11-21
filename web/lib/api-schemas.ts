/**
 * Runtime schemas for every AstraGraph API response (see api/schemas.py on the
 * fastapi-backend branch). Responses are validated as they arrive, so the rest
 * of the app works with checked, fully typed data. Field names are snake_case,
 * exactly as the API sends them.
 */

import { z } from "zod";

export const CompassSchema = z.enum(["N", "NE", "E", "SE", "S", "SW", "W", "NW"]);

export const HealthSchema = z.object({ status: z.literal("ok"), version: z.string() });

export const SkyStarSchema = z.object({
  name: z.string(),
  az: z.number(),
  alt: z.number(),
  magnitude: z.number(),
  ci: z.number().nullable(),
});

export const MoonSchema = z.object({
  phase_name: z.string(),
  phase_degrees: z.number(),
  illumination: z.number().min(0).max(1),
  waxing: z.boolean(),
  altitude: z.number(),
});

const Pair = z.tuple([z.string(), z.string()]);

// ------------------------------------------------------------------ /sky
export const SkyConstellationSchema = z.object({
  name: z.string(),
  abbreviation: z.string(),
  az: z.number(),
  alt: z.number(),
  direction: CompassSchema,
  visible: z.boolean(),
  stars: z.array(SkyStarSchema),
  lines: z.array(Pair),
});

export const SkyResponseSchema = z.object({
  time_utc: z.string(),
  time_local: z.string(),
  tz: z.string(),
  lat: z.number(),
  lon: z.number(),
  sun_altitude: z.number(),
  darkness: z.enum(["day", "twilight", "night"]),
  moon: MoonSchema,
  stars: z.array(SkyStarSchema),
  constellations: z.array(SkyConstellationSchema),
});

// -------------------------------------------------------------- /tonight
export const TonightResponseSchema = z.object({
  darkness: z.discriminatedUnion("state", [
    z.object({ state: z.literal("dark"), minutes_until_dawn: z.number().int() }),
    z.object({ state: z.literal("light"), minutes_until_dark: z.number().int() }),
    z.object({ state: z.literal("never-dark") }),
  ]),
  dusk_utc: z.string().nullable(),
  dawn_utc: z.string().nullable(),
  moon: MoonSchema,
  best: z
    .object({ name: z.string(), altitude: z.number(), azimuth: z.number(), direction: CompassSchema })
    .nullable(),
  brightest_stars: z.array(z.string()),
  up_tonight: z.array(z.object({ name: z.string(), direction: CompassSchema })),
});

// -------------------------------------------------------- constellations
export const ChartStarSchema = z.object({
  name: z.string(),
  designation: z.string(),
  ra: z.number(),
  dec: z.number(),
  magnitude: z.number(),
  ci: z.number().nullable(),
  distance_ly: z.number().int().nullable(),
  fact: z.string().nullable(),
});

export const ConstellationSummarySchema = z.object({
  name: z.string(),
  abbreviation: z.string(),
  stars: z.array(ChartStarSchema),
  lines: z.array(Pair),
});

export const ConstellationListSchema = z.array(ConstellationSummarySchema);

export const ConstellationDetailSchema = ConstellationSummarySchema.extend({
  mythology: z.string(),
  best_season: z.string(),
  fun_fact: z.string(),
  best_month: z.object({ month: z.number().int().min(1).max(12), altitude: z.number() }).nullable(),
  now: z.object({ az: z.number(), alt: z.number(), direction: CompassSchema, visible: z.boolean() }),
  tonight: z.object({
    rise_utc: z.string().nullable(),
    transit_utc: z.string().nullable(),
    set_utc: z.string().nullable(),
    transit_altitude: z.number().nullable(),
    circumpolar: z.boolean(),
    never_rises: z.boolean(),
  }),
});

// ------------------------------------------------------------------ quiz
export const QuizNewSchema = z.object({
  id: z.string(),
  constellation: z.string(),
  mode: z.enum(["easy", "hard"]),
  stars: z.array(
    z.object({ name: z.string(), x: z.number(), y: z.number(), magnitude: z.number(), ci: z.number().nullable() }),
  ),
  line_count: z.number().int(),
});

export const QuizGradeSchema = z.object({
  constellation: z.string(),
  score: z.number(),
  perfect: z.boolean(),
  correct: z.array(Pair),
  missing: z.array(Pair),
  extra: z.array(Pair),
  isomorphic_hint: z.boolean(),
});

// ---------------------------------------------------------------- /frame
const Point = z.tuple([z.number(), z.number()]);

export const FrameResponseSchema = z.object({
  stars: z.array(z.object({ id: z.number().int(), x: z.number(), y: z.number(), r: z.number(), brightness: z.number() })),
  constellations: z.array(
    z.object({
      name: z.string(),
      confidence: z.number(),
      matched: z.number().int(),
      total: z.number().int(),
      lines: z.array(z.tuple([z.number(), z.number(), z.number(), z.number()])),
      label: Point,
      stars: z.array(z.object({ id: z.number().int(), name: z.string() })),
      partial: z.boolean(),
    }),
  ),
  ghosts: z.array(z.object({ name: z.string(), x: z.number(), y: z.number(), r: z.number() })),
  satellites: z.array(
    z.object({
      id: z.number().int(),
      x: z.number(),
      y: z.number(),
      vx: z.number(),
      vy: z.number(),
      speed: z.number(),
      speed_unit: z.enum(["deg/s", "px/s"]),
      direction: CompassSchema.nullable(),
      trail: z.array(Point),
    }),
  ),
  anomalies: z.array(z.object({ id: z.number().int(), x: z.number(), y: z.number(), label: z.string() })),
  events: z.array(z.object({ type: z.string(), id: z.number().int() })),
  plan: z.null(),
  meta: z.object({
    width: z.number().int(),
    height: z.number().int(),
    frame_index: z.number().int(),
    processing_ms: z.number(),
  }),
});

export const DemoSkyInfoSchema = z.object({
  constellations: z.array(z.string()),
  frame_count: z.number().int(),
  fps: z.number(),
  width: z.number().int(),
  height: z.number().int(),
});
