import type { TonightSummary } from "@/lib/types";

/**
 * Sample "Tonight's sky" data used until the API is wired in step 3.
 * Values are realistic for a January evening in New York.
 */
export const MOCK_TONIGHT: TonightSummary = {
  darkness: { state: "dark", minutesUntilDawn: 512 },
  moon: { phaseName: "Waxing Gibbous", illumination: 0.84, waxing: true },
  best: { name: "Orion", altitude: 46, azimuth: 151, direction: "SE" },
  brightestStars: ["Sirius", "Capella", "Rigel", "Procyon", "Betelgeuse"],
  upTonight: [
    { name: "Orion", direction: "SE" },
    { name: "Cassiopeia", direction: "NW" },
    { name: "Ursa Major", direction: "NE" },
    { name: "Ursa Minor", direction: "N" },
    { name: "Leo", direction: "E" },
  ],
};
