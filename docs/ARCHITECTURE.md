# AstraGraph Architecture

AstraGraph rests on three pillars, each answering one question:

| Pillar | Question | Main modules |
| --- | --- | --- |
| Computer Vision | *Where are the stars in this image?* | `detect.py`, `track.py` |
| Graphs | *Which constellation is this, and what is happening?* | `temporal.py`, `matcher.py`, `reason.py`, `spatial_plan.py` |
| World Model | *Where will everything be at time t?* | `world_model.py` |

`pipeline.py` chains the first two per video frame; the Streamlit app
(`app/demo.py`) combines all three with the learning module (`academy.py`).

```
                        ┌──────────────────────────── per frame ────────────────────────────┐
 camera / photo / video │                                                                    │
 ───────────────────────▶ detect.py ──▶ track.py ──▶ temporal.py ──▶ matcher.py ──▶ reason.py │
                        │ stars        stable IDs    scene graph,    constellation   facts →   │
                        │ (x,y,mag)    trajectories  events,         + ghosts        conclusions│
                        │                            clusters                                 │
                        └────────────────────────────────────────┬───────────────────────────┘
                                                                 │ FrameReport
 data/constellations.json ──▶ constellation_db.py ───────────────┤
 data/bright_stars.csv ──┐                                        ▼
 JPL DE421 (skyfield) ───┴──▶ world_model.py ──────────▶ app/demo.py ◀── academy.py ◀── data/constellation_info.json
                              alt/az, rise/set,          Live Camera · Time Travel · Learn · Academy
                              Sun, best month
```

## Pillar 1: Computer Vision — detecting stars

**`detect.py` (`StarDetector`)**

1. Convert to grayscale and apply a 3×3 Gaussian blur to suppress sensor noise.
2. `cv2.SimpleBlobDetector` sweeps brightness thresholds to find bright,
   compact blobs.
3. Each candidate is measured on its thresholded connected component:
   - **aspect ratio** from second moments (principal axes) — above 2 means a
     streak (aircraft, satellite trail) and it is rejected;
   - **peak brightness** below `min_brightness` (180) — rejected as glow/noise;
   - **touching the image border** — rejected (only partly visible);
   - **area** below `min_size` (3 px) — rejected as a hot pixel.
4. Positions are refined to sub-pixel accuracy with an intensity-weighted
   centroid; detections are returned brightest first.

**`track.py` (`StarTracker`)** gives each star a stable ID across frames.
Every track predicts its next position from its last two (constant velocity:
stars stay put, satellites keep moving). Detections are assigned greedily to
the nearest prediction within `max_distance`. A track survives up to
`max_disappeared` frames without a detection, so a star behind a passing cloud
keeps its ID when it reappears.

## Pillar 2: Graphs — matching and reasoning

**Temporal scene graph (`temporal.py`).** Each frame becomes a graph `G_t`:
nodes are tracked stars, edges are `near(A, B)` (closer than
`cluster_distance`). Diffing `G_t` against `G_{t-1}` yields events:

| Event | Rule |
| --- | --- |
| `APPEARS` | visible for `debounce_frames` consecutive frames |
| `DISAPPEARS` | missing for `max_disappeared` frames (occlusion grace period) |
| `MOVES` | drifted more than `move_threshold` px relative to the star field |
| `LINEAR_TRAJECTORY` | straight path + steady speed above threshold → satellite |

Camera shake is removed first: the median frame-to-frame shift of all tracks
is treated as ego-motion, so panning the phone does not make every star move.
Satellites need a straight path *and* a steady per-frame speed (median, not
mean), so a star nudged once by hand shake is not mistaken for one.

**Union-find clustering.** `near` is reflexive and symmetric; its transitive
closure is an equivalence relation whose classes are star clusters. A
from-scratch disjoint-set forest (path compression + union by rank) computes
them in near-linear time.

**Constellation matching (`matcher.py`).** Constellations are stored as graphs
of real sky positions. Matching must ignore rotation, scale and position, cope
with hidden stars and ignore unrelated ones:

1. *Hypothesise.* Assume an observed pair of stars `(a, b)` is a template pair
   `(p, q)`. That fixes rotation, scale and translation (a similarity
   transform). Map all observed stars into the template plane and assign each
   to the nearest template star within tolerance. This is vectorised over all
   template pairs using complex arithmetic.
2. *Confirm.* NetworkX `GraphMatcher` checks the mapping is a subgraph
   monomorphism in which every edge length agrees with the template.
3. *Verify.* A least-squares similarity fit must leave a small residual. This
   rejects mirror images, which have identical edge lengths.
4. *Score.* `confidence = matched stars / template stars`. Each ignored
   (outlier) star must be paid for with an extra matched star unless the match
   is complete, which keeps the false-positive rate low.

Because the fit gives the full template-to-image transform, hidden template
stars are projected into the image as **ghosts** (the X-Ray overlay), and the
plate scale (degrees per pixel) converts satellite speeds to °/s.

**Rule engine (`reason.py`).** Scene facts are triples such as
`("velocity", "track:7", 3.2)`. Horn rules derive conclusions by forward
chaining to a fixpoint:

```
cluster_size(C, N) ∧ N ≥ 4 ∧ matches_pattern(C, K)           → identified_as(C, K)
identified_as(C, K) ∧ match_confidence(C, X) ∧ X < 0.6        → partial_view(C, K)
partial_view(C, K) ∧ hidden_star(C, H)                        → render_ghost(H, K)
trajectory_linear(T) ∧ velocity(T, V) ∧ V > 1.0               → is_satellite(T)
brightness(S, B) ∧ B > 230 ∧ not_in_catalog(S)                → is_anomaly(S)
```

Rules must be range-restricted (every conclusion variable is bound by a
premise), so derived facts only recombine existing constants: the fixpoint is
always reached and re-running the engine derives nothing new.

**Camera guidance (`spatial_plan.py`).** The sky is a grid graph of
azimuth/altitude cells with great-circle edge weights (wrapping through north).
Dijkstra from the target finds the nearest clear cell that keeps the target in
the field of view, returned as a pan/tilt suggestion.

## Pillar 3: World Model — predicting the sky

`world_model.py` (`SkyWorldModel`) is deterministic physics, not a learned
model:

- **Inputs:** the 300 brightest stars (HYG v4.1: J2000 position, proper
  motion, parallax), the JPL DE421 ephemeris for Earth's orbit (bundled by
  `skyfield-data`, so it works offline) and the observer's latitude,
  longitude and time.
- **Computation:** Skyfield applies proper motion, precession, nutation,
  aberration, light deflection and Earth's rotation, then converts to
  altitude/azimuth. Agreement with Astropy (an independent IAU SOFA
  implementation) is about 0.0001°.
- **Outputs:** visible stars, predictions `hours_ahead`, the IAU constellation
  in any direction, rise/set times (with standard refraction at the horizon),
  constellation centres, the best viewing month and the Sun's altitude
  (day / twilight / night).

Timezone-aware datetimes are required everywhere; naive datetimes are rejected
because their meaning is ambiguous.

## How the pillars work together

- **Live Camera:** Vision finds and tracks stars; Graphs identify the
  constellation, infer hidden stars and flag satellites and anomalies; the
  overlay draws the result. Everything runs locally — no frames leave the
  device.
- **Time Travel:** the World Model computes every star and constellation
  position for the chosen time, then draws the constellation graphs on a sky
  chart.
- **Learn / Academy:** the constellation graphs drive the connect-the-dots quiz
  (answers are graded as graphs: Jaccard similarity of edge sets, plus an
  isomorphism check for "right shape, wrong stars"), while the World Model
  supplies live positions, rise/set times and the best month to look.

## Design choices and limits

- **Shape matching, not compass trust.** The camera image determines which
  constellation is in view; no magnetometer is needed. Time and rough location
  are still needed for horizon-related features.
- **Pixel thresholds.** Clustering distance and satellite speed are in pixels,
  tuned for 720p–1080p frames (wider frames are downscaled with a
  peak-preserving max filter). Scaling them by field of view is future work.
- **Catalog scope.** Matching uses the 8 constellations in the database; the
  world model knows the 300 brightest stars and all 88 IAU boundaries.
- **Synthetic validation.** The vision pipeline is tested on rendered skies;
  tuning on real phone footage is the next step.
