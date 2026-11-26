# AstraGraph web (Next.js)

The immersive frontend for AstraGraph: Next.js (App Router) + TypeScript (strict)
+ Tailwind CSS v4 + Framer Motion, with Canvas 2D for the sky.

## Run locally

```bash
cd web
npm install
cp .env.example .env.local   # then set NEXT_PUBLIC_API_URL
npm run dev                  # http://localhost:3000
```

Other scripts: `npm run build` (production build), `npm start` (serve the build),
`npm run typecheck`.

Every page except the gallery and the home-page animations needs the AstraGraph
API running (branch `fastapi-backend`: `uvicorn api.main:app --port 8000`).

## Configuration

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | Base URL of the AstraGraph Python API, without a trailing slash. |
| `NEXT_PUBLIC_SITE_URL` | Optional: public site URL, used for absolute share-image links. |

The API must send CORS headers allowing this site's origin: set
`ASTRAGRAPH_ALLOWED_ORIGINS` on the API to e.g.
`https://<your-app>.vercel.app,http://localhost:3000`.

## Pages

| Route | What it does | Data |
| --- | --- | --- |
| `/` | Hero, tonight's sky strip, animated feature demos | API `/tonight` |
| `/live` | Live Camera: webcam, upload or demo sky with a detection overlay | API `/frame`, `/demo-sky` |
| `/time-travel` | Planetarium dome, −12 h … +12 h | API `/sky` |
| `/learn` | Constellation charts, star facts, best month, rise/transit/set | API `/constellations`, `/constellation/{name}` |
| `/gallery` | 36 pre-rendered sky wallpapers with filters, lightbox and download | Static: `public/manifest.json` |

## Structure

```
app/(routes)/          the pages above
app/layout.tsx         fonts, metadata, starfield, nav, location provider
app/template.tsx       page-enter transition
app/opengraph-image.tsx  generated share image
app/not-found.tsx      404 page
components/sky/        Starfield, SkyDome, ConstellationTrace
components/home/       home-page sections and demos, footer
components/time-travel/, learn/, live/, gallery/   page components
components/hud/        Live Camera overlay, readout and legend
components/ui/         TopNav, LocationPopover, loading states, icons
hooks/                 useLocation, useApiResource, useSkyKeyframes, useCamera, useCanvas…
lib/                   API client + zod schemas, types, sky maths, colours, overlay geometry
public/                gallery: manifest.json, wallpapers/*.png, wallpapers/thumbs/*.webp
```

## Attribution

Required on every deployment (shown in the site footer):

- Star data: HYG Database v4.1 (CC BY-SA 4.0) — https://github.com/astronexus/HYG-Database
- Sky positions: Skyfield + JPL DE421 ephemeris — https://rhodesmill.org/skyfield/

## Deploy checklist

1. **API on Render** (free plan): New → Blueprint → this repository, branch
   `fastapi-backend` (it reads `render.yaml`). Set `ASTRAGRAPH_ALLOWED_ORIGINS`
   to `http://localhost:3000` for now. When it is live, `https://<api>/health`
   returns `{"status":"ok",…}`.
2. **Website on Vercel**: Add New → Project → this repository.
   - Root Directory: `web`
   - Production branch: `nextjs-frontend` (Settings → Git, if it is not the default)
   - Environment variable: `NEXT_PUBLIC_API_URL=https://<api>` (no trailing slash)
3. **Connect them**: on Render, set `ASTRAGRAPH_ALLOWED_ORIGINS` to
   `https://<your-app>.vercel.app,http://localhost:3000`.
4. **Check**: open every page on a laptop and a phone. The first visit after a
   quiet spell shows "Waking the telescope…" for up to a minute while the free
   API starts — that is expected.

Everything is statically rendered; no server-side Node features are needed.
The Live Camera page needs HTTPS (Vercel provides it) because browsers only
allow the camera on secure pages.
