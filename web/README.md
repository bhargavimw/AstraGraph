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

## Configuration

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | Base URL of the AstraGraph Python API, without a trailing slash. |
| `NEXT_PUBLIC_SITE_URL` | Optional: public site URL, used for absolute share-image links. |

The API must send CORS headers allowing this site's origin (for example
`https://<your-app>.vercel.app` and `http://localhost:3000`).

## Structure

```
app/(routes)/        pages: /, /live, /time-travel, /learn, /academy
app/layout.tsx       fonts, metadata, starfield, nav, location provider
app/template.tsx     page-enter transition
components/sky/      Starfield (later: SkyDome)
components/ui/       TopNav, LocationPopover, Logo, icons
components/hud/      Live Camera overlay (step 6)
hooks/               useLocation, useReducedMotion, useAnimationFrame
lib/                 types, star colours (later: api client, sky maths)
```

## Deploying on Vercel

Import the repository, set the project root to `web/`, and add
`NEXT_PUBLIC_API_URL` in the project's environment variables. Everything is
statically rendered; no server-side Node features are required. The Live Camera
page needs HTTPS (Vercel provides it) because browsers only allow camera access
on secure origins.
