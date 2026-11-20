# AstraGraph

**Learn & explore the night sky.** AstraGraph finds constellations in camera
images by matching the *shape* of the stars rather than trusting the phone's
compass, predicts where everything will be at any time, and teaches the
connections behind it.

## What it does

- **Live Camera (SkyFinder)**: detects stars in a webcam stream, photo or
  video, identifies the constellation and draws it. It still works when clouds
  hide some stars: the hidden ones are inferred and drawn as "ghosts".
  Satellites (fast, straight-line movers) and bright objects missing from the
  catalog (such as planets) are flagged.
- **Time Travel**: slide up to 12 hours either way to see the predicted sky,
  e.g. *"In 3 hours, Orion will be at azimuth 220°, altitude 45°."*
- **Learn**: key stars, the best month to look, where a constellation is right
  now and when it rises and sets tonight.

## Why it is useful

- **Works without a reliable compass**: constellations are recognised from
  the geometry of the stars themselves, so a drifting magnetometer does not
  point you at the wrong part of the sky.
- **Robust to the real world**: clouds, trees and hand shake are expected,
  not errors.
- **Accurate predictions**: positions come from real astronomy (Skyfield +
  JPL DE421) and agree with an independent implementation to about 0.0001°.
- **Private by design**: every computation runs locally; no images or
  location data are sent anywhere.

## Installation

Requires Python 3.10 or newer.

```bash
git clone https://github.com/bhargavimw/AstraGraph.git
cd AstraGraph
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Everything needed at runtime is installed by pip; the JPL ephemeris comes with
the `skyfield-data` package, so no downloads happen when the app runs.

## Running the app

```bash
streamlit run app/demo.py
```

or `python scripts/run_app.py`. Streamlit opens http://localhost:8501.

- **Live Camera**: choose *Demo sky* to see the full pipeline on a rendered
  sky, *Webcam* for a live stream (allow camera access; browsers only allow it
  on `localhost` or HTTPS), or upload a photo/video.
- Set your location and time zone in the sidebar for Time Travel and Learn.

Command-line demos and tests:

```bash
python scripts/demo_reasoning.py            # detection → tracking → reasoning
python scripts/demo_world_model.py          # visible constellations + sky map
python scripts/visualize_db.py              # render the constellation database
pytest                                      # full test suite
```

## Architecture

```
 camera frame
      │
      ▼
┌─────────────────────┐   ┌──────────────────────┐   ┌───────────────────────────┐
│ Computer Vision     │   │ Graphs & Reasoning   │   │ World Model               │
│                     │   │                      │   │                           │
│ detect.py           │──▶│ temporal.py          │   │ world_model.py (Skyfield) │
│  OpenCV blobs,      │   │  scene graph diffs,  │   │  star catalog + DE421     │
│  noise filters      │   │  union-find clusters,│   │  → alt/az at any time     │
│ track.py            │   │  APPEARS/DISAPPEARS/ │   │  → rise/set, best month   │
│  stable IDs,        │   │  MOVES/satellites    │   │  → constellation lookup   │
│  trajectories       │   │ matcher.py           │   │                           │
│                     │   │  geometric subgraph  │   │                           │
│                     │   │  matching (NetworkX) │   │                           │
│                     │   │ reason.py            │   │                           │
│                     │   │  forward-chaining    │   │                           │
│                     │   │  Horn rules          │   │                           │
└─────────────────────┘   └──────────┬───────────┘   └─────────────┬─────────────┘
                                     │                             │
                                     ▼                             ▼
                          ┌───────────────────────────────────────────────┐
                          │ app/demo.py (Streamlit)                       │
                          │ Live Camera · Time Travel · Learn             │
                          └───────────────────────────────────────────────┘
```

| Module | Role |
| --- | --- |
| `constellation_db.py` | 8 constellations as NetworkX graphs (J2000 star positions + stick-figure lines) |
| `detect.py` | Star detection with OpenCV `SimpleBlobDetector`; rejects trails, faint blobs, border blobs, hot pixels |
| `track.py` | Centroid tracking with velocity prediction; stable IDs through short occlusions |
| `temporal.py` | Temporal scene graph, debounced events, union-find clustering, satellite detection with camera-motion compensation |
| `matcher.py` | Rotation/scale-invariant constellation matching, partial views, mirror rejection, ghost-star projection |
| `reason.py` | Forward-chaining rule engine with fixpoint iteration |
| `spatial_plan.py` | Dijkstra over a sky-region graph to suggest a camera pan around obstructions |
| `pipeline.py` | Runs detector → tracker → temporal graph → matcher → reasoner per frame |
| `world_model.py` | Star positions, visibility, constellation lookup, rise/set times, Sun altitude |
| `app/` | Streamlit app and OpenCV overlay helpers |

## Screenshots

> _Screenshots coming soon._
>
> - Live Camera: constellation overlay with ghost stars and a satellite
> - Time Travel: predicted sky chart
> - Learn: constellation card with rise/set times

## Configuration

All thresholds live in `config.yaml`: detector brightness/size/aspect limits,
tracking grace periods, clustering distance, matcher tolerances, reasoning
thresholds and the default location for the world model.

## Future work

- Test and tune on real night-sky footage from phones (current tests use
  rendered skies).
- Make pixel thresholds (clustering distance, satellite speed) scale with the
  camera's field of view instead of being fixed in pixels.
- Use the phone's rough orientation as a prior so matching can draw on the
  full star catalog, not just the 8 constellations in the database.
- Live satellite passes (ISS, Starlink) from downloaded orbital elements,
  computed on the device.
- Add planets and the Moon to Time Travel.
- Package as a mobile app with on-device processing.

## Credits

- Star data: [HYG Database](https://github.com/astronexus/HYG-Database) v4.1, CC BY-SA 4.0.
- Ephemeris: JPL DE421 via [Skyfield](https://rhodesmill.org/skyfield/) and `skyfield-data`.
- Constellation boundaries: IAU, via Skyfield.
