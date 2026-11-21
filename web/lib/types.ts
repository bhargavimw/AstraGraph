/**
 * Shared types. API response types are added in step 3, when the client is
 * wired to the backend; shapes mirror the repository's data files
 * (data/constellations.json, data/constellation_info.json).
 */

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
