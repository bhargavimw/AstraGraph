import type { ApiTonight, TonightSummary } from "@/lib/types";

/** API /tonight response → the shape the Tonight strip renders. */
export function toTonightSummary(api: ApiTonight): TonightSummary {
  const d = api.darkness;
  return {
    darkness:
      d.state === "dark"
        ? { state: "dark", minutesUntilDawn: d.minutes_until_dawn }
        : d.state === "light"
          ? { state: "light", minutesUntilDark: d.minutes_until_dark }
          : { state: "never-dark" },
    moon: { phaseName: api.moon.phase_name, illumination: api.moon.illumination, waxing: api.moon.waxing },
    best: api.best
      ? { name: api.best.name, altitude: api.best.altitude, azimuth: api.best.azimuth, direction: api.best.direction }
      : null,
    brightestStars: api.brightest_stars,
    upTonight: api.up_tonight,
  };
}
