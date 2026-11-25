# AstraGraph Wallpaper Gallery — Frontend Handoff

Prepared for the Next.js frontend team (hosted on Vercel). This document
describes how to integrate the pre-rendered wallpaper gallery into your app.

**No Python backend is required on Vercel.** The recommended path is fully
static.

---

## The two integration paths

### Path A — STATIC (recommended for Vercel)

Copy `outputs/frontend_bundle/*` into your Next.js app's `public/` directory:

```
your-nextjs-app/
  public/
    manifest.json
    wallpapers/
      bengaluru_classic_phone.png
      ... (36 PNGs, 1080x2340)
    thumbs/
      bengaluru_classic_phone.webp
      ... (36 WebP thumbnails, 400px wide)
```

Then import `public/manifest.json` in your code (or fetch it at runtime:

```ts
const manifest = await fetch("/manifest.json").then((r) => r.json());
```

**Why this is the default:** the Python renderer needs Skyfield, the JPL DE421
ephemeris, numpy, and Pillow — none of which fit within Vercel Hobby function
limits. Pre-rendering removes the backend entirely: no cold starts, no timeouts,
instant image loads from the Vercel edge network.

### Path B — API (only for a future "create your own sky" form)

If you later want a custom-render form (user picks lat/lon/time/style), host
the FastAPI service separately — on Railway, Fly.io, or Render — **not** on
Vercel serverless.

- Docker image: `api/Dockerfile` (`python:3.11-slim`)
- Run: `uvicorn api.main:app --host 0.0.0.0 --port 8000`
- Endpoints (see table below)

Point your frontend at that host via `NEXT_PUBLIC_API_BASE_URL` (see `.env.example`).

---

## Manifest schema (TypeScript interfaces)

Copy these verbatim from `outputs/frontend_bundle/manifest.json`:

```ts
export interface Wallpaper {
  id: string;                    // e.g. "bengaluru_classic_phone"
  title: string;                 // e.g. "Bengaluru — Classic"
  city: string;                  // e.g. "Bengaluru"
  country: string;               // e.g. "India"
  lat: number;
  lon: number;
  timezone: string;              // IANA, e.g. "Asia/Kolkata"
  datetime_local: string;        // ISO8601 with offset, e.g. "2026-11-25T23:00:00+05:30"
  datetime_utc: string;          // ISO8601 UTC, e.g. "2026-11-25T17:30:00Z"
  style: string;                 // "classic" | "minimal" | "vintage" | "aurora"
  aspect: string;                // "phone"
  width: number;                 // 1080
  height: number;                // 2340
  filename: string;              // e.g. "bengaluru_classic_phone.png"
  path: string;                  // "/wallpapers/bengaluru_classic_phone.png"
  thumbnail: string;             // "/wallpapers/thumbs/bengaluru_classic_phone.webp"
  bytes: number;                 // file size in bytes
  featured: boolean;             // true for the featured 20
  hemisphere: string;            // "northern" | "southern"
  tags: string[];                // e.g. ["india", "city", "classic", "northern"]
  visible_constellations: string[]; // computed from SkyWorldModel
  moon_phase: string;            // e.g. "new", "waxing crescent", "full"
  caption: string;               // e.g. "Bengaluru · 25 Nov 2026 · 23:00 IST"
}

export interface GalleryManifest {
  generated_at: string;          // ISO8601 UTC
  engine: string;                // "AstraGraph SkyWorldModel (Skyfield + JPL DE421 + HYG v4.1)"
  count: number;                 // 36
  wallpapers: Wallpaper[];
}
```

Asset URLs are relative to your Next.js `public/` root:

- Full PNG: `${manifest.wallpapers[0].path}` → `/wallpapers/bengaluru_classic_phone.png`
- Thumbnail: `${manifest.wallpapers[0].thumbnail}` → `/wallpapers/thumbs/bengaluru_classic_phone.webp`

---

## Endpoint table (Path B — API only)

| Endpoint | Method | Query / Body | Response |
|----------|--------|--------------|----------|
| `/api/health` | GET | — | `{status, catalog_size, ephemeris}` |
| `/api/gallery` | GET | `?featured=true`, `?city=nyc` | Manifest (filtered) |
| `/api/wallpapers/{filename}` | GET | — | `image/png` |
| `/api/render` | POST | `{lat, lon, datetime_iso, timezone, style, aspect, overlays?}` | `image/png` |

Example request (custom render):

```json
POST /api/render
{
  "lat": 40.7128,
  "lon": -74.0060,
  "datetime_iso": "2026-11-25T23:00:00-05:00",
  "timezone": "America/New_York",
  "style": "classic",
  "aspect": "phone",
  "overlays": {
    "constellation_lines": true,
    "constellation_labels": true,
    "moon": true,
    "planets": false,
    "caption": true
  }
}
```

Invalid lat / unknown style / unknown aspect returns `422`.

---

## Asset facts

- **36 PNGs** at 1080×2340 (phone aspect), ~160–180 KB each
- **36 WebP thumbnails** at 400px wide, ~15–70 KB each
- **Total bundle:** ~5.8 MB
- **Manifest:** `manifest.json` (~38 KB)
- Suggested UX: render the grid using `thumbnail` WebP files; open the full `path` PNG in a lightbox or on download.

---

## Suggested UX

1. **Featured-20 grid** (default view): show only `featured === true` entries.
   - Group by city; Indian cities (Bengaluru, Mumbai, Chennai, Kolkata) clustered together.
2. **"Show all" toggle**: reveals all 36 entries.
3. **City filter**: dropdown of the 9 city IDs.
4. **Style filter**: classic / minimal / vintage / aurora.
5. **Lightbox**: clicking a wallpaper opens the full 1080×2340 PNG.
6. **Download button**: `href={wallpaper.path}` with `download` attribute.
7. **Shareable URL params**: `?city=bengaluru&style=classic` to pre-filter.

---

## React snippets

### Fetch manifest and render a grid

```tsx
import { Wallpaper } from "@/types/wallpaper";

export default function WallpaperGrid() {
  const [wallpapers, setWallpapers] = useState<Wallpaper[]>([]);
  const [featuredOnly, setFeaturedOnly] = useState(true);

  useEffect(() => {
    fetch("/manifest.json")
      .then((r) => r.json())
      .then((data: GalleryManifest) => setWallpapers(data.wallpapers));
  }, []);

  const visible = wallpapers.filter(
    (w) => !featuredOnly || w.featured
  );

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {visible.map((w) => (
        <Card key={w.id}>
          <img src={w.thumbnail} alt={w.title} loading="lazy" />
          <p>{w.title}</p>
          <p>{w.caption}</p>
          <a href={w.path} download={w.filename}>
            Download
          </a>
        </Card>
      ))}
    </div>
  );
}
```

### Download handler

```tsx
function handleDownload(wallpaper: Wallpaper) {
  const link = document.createElement("a");
  link.href = wallpaper.path;
  link.download = wallpaper.filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
```

---

## Attribution requirement (mandatory)

The star catalog is derived from the **HYG Database v4.1**, which is licensed
under **CC BY-SA 4.0** (https://github.com/astronexus/HYG-Database). Sky
positions are computed with **Skyfield** using the **JPL DE421 ephemeris**.

Your footer **must** credit:

```
Star data: HYG Database v4.1 (CC BY-SA 4.0)
Sky positions: Skyfield + JPL DE421 ephemeris
```

Link to https://github.com/astronexus/HYG-Database and
https://rhodesmill.org/skyfield/.

---

## `.env.example` for the frontend

```env
# Only needed for Path B (custom-render API). Leave unset for Path A (static).
NEXT_PUBLIC_API_BASE_URL=https://your-astragraph-api.example.com
```

---

## Summary checklist for the frontend team

- [ ] Copy `outputs/frontend_bundle/*` → `public/`
- [ ] Import `public/manifest.json` (or fetch at runtime)
- [ ] Build featured-20 grid using `thumbnail` URLs
- [ ] Link full-size PNGs via `path` URLs
- [ ] Add HYG / Skyfield / JPL DE421 attribution to the footer
- [ ] (Optional, Path B only) Set `NEXT_PUBLIC_API_BASE_URL` and wire up `/api/render`

---

**Questions?** Reach out to the AstraGraph backend team. Do not modify the
Python renderer or regenerate images unless instructed — the gallery is
deterministic and versioned.