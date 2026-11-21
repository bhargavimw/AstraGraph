# AstraGraph API (FastAPI)

An HTTP API around the existing `astragraph` Python package, used by the
Next.js website (`web/`). It reuses the same detector, tracker, matcher, rule
engine, world model and academy as the Streamlit app; nothing is reimplemented.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate            # Windows (Git Bash): source .venv/Scripts/activate
pip install -r api/requirements.txt
uvicorn api.main:app --reload --port 8000
```

Open http://localhost:8000/docs for interactive documentation of every
endpoint. The website expects `NEXT_PUBLIC_API_URL=http://localhost:8000`.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness check |
| POST | `/frame` | Multipart `image` (JPEG/PNG) + `session_id`. Detects stars, tracks them per session, identifies constellations, infers hidden (ghost) stars, flags satellites and anomalies. Coordinates are in the sent image's pixels. |
| GET | `/sky?lat&lon&tz&offset_hours[&at]` | Bright stars and all constellations (alt/az, colour index, lines), Sun altitude, darkness, Moon |
| GET | `/tonight?lat&lon&tz[&at]` | Tonight's summary: darkness countdown, Moon, best constellation, brightest stars, what's up |
| GET | `/constellations` | All constellations with chart data (thumbnails, pickers) |
| GET | `/constellation/{name}?lat&lon&tz[&at]` | Chart, key-star facts and distances, mythology, best season and month, current position, tonight's rise/transit/set |
| GET | `/quiz/new?mode=easy\|hard[&constellation]` | Connect-the-dots puzzle (the answer and distractor flags are not sent) |
| POST | `/quiz/grade` | JSON `{id, edges}` → correct / missing / extra lines, score, "right shape, wrong stars" hint |
| GET | `/demo-sky` | Describes the synthetic demo clip |
| GET | `/demo-sky/frame?constellation&index` | One demo frame as JPEG; play the demo by POSTing these to `/frame` |

Notes:
- `at` is optional (defaults to now) and must include a UTC offset, e.g.
  `2024-01-15T21:00:00-05:00`. Naive times are rejected so results never shift
  silently by hours.
- `/frame` keeps each `session_id`'s tracking state in memory (expires after
  10 idle minutes). Send one frame at a time per session.
- `plan` in `/frame` responses is always `null`: a camera-pan suggestion needs
  the camera's pointing direction, which a single image does not provide.

## Configuration (environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `ASTRAGRAPH_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated origins allowed by CORS. Add your Vercel URL, e.g. `https://astragraph.vercel.app,http://localhost:3000`. |
| `ASTRAGRAPH_MAX_UPLOAD_MB` | `4` | Largest accepted `/frame` image |
| `ASTRAGRAPH_MAX_SESSIONS` | `50` | Live camera sessions kept in memory |
| `ASTRAGRAPH_SESSION_TTL` | `600` | Seconds before an idle session is dropped |

## Deploy free on Render

1. Push this branch to GitHub.
2. On https://render.com choose **New → Blueprint**, pick the repository and
   this branch. Render reads `render.yaml` at the repository root.
3. When asked, set `ASTRAGRAPH_ALLOWED_ORIGINS` to your website's address
   (for example `https://your-app.vercel.app`).
4. After the first deploy, open `https://<your-service>.onrender.com/health`.
5. In Vercel, set `NEXT_PUBLIC_API_URL` to `https://<your-service>.onrender.com`.

Manual setup instead of the blueprint: a Python web service with build command
`pip install -r api/requirements.txt` and start command
`uvicorn api.main:app --host 0.0.0.0 --port $PORT`.

Free Render services sleep after ~15 idle minutes; the first request then takes
30–60 s while it wakes up (the website shows "Waking the telescope…").

## Data

`api/data/star_colors.json` holds B−V colour indexes for star colours, built by
`api/scripts/build_star_colors.py` from HYG v4.1 (CC BY-SA 4.0).

## Tests

```bash
pip install pytest httpx
pytest tests/test_api.py
```
