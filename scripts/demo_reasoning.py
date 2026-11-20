"""Stage 2+3 demo: detector → tracker → temporal graph → matcher → reasoner.

Usage:
    python scripts/demo_reasoning.py                       # synthetic Orion clip
    python scripts/demo_reasoning.py --constellation "Ursa Major"
    python scripts/demo_reasoning.py --image sky.jpg
    python scripts/demo_reasoning.py --video sky.mp4

With no input file, a synthetic clip is rendered: the chosen constellation
with slight hand-shake drift, a cloud that hides two of its stars halfway
through (exercising DISAPPEARS events and X-Ray ghost stars; fewer for
small constellations so at least five stay visible), a satellite
crossing the field and a bright planet that is not in the catalog.

An annotated image of the final frame is written to ``outputs/`` (green
circles = stars, gold lines = constellation, cyan rings = ghost stars,
red = satellite track, magenta = anomaly).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astragraph.constellation_db import ConstellationDB  # noqa: E402
from astragraph.pipeline import FrameReport, PipelineConfig, SkyPipeline  # noqa: E402
from astragraph.synthetic import demo_sky_clip  # noqa: E402
from astragraph.temporal import EventType  # noqa: E402

WIDTH, HEIGHT = 960, 720
GREEN, GOLD, CYAN, RED, MAGENTA, WHITE = (
    (80, 220, 80), (40, 190, 255), (255, 220, 60), (60, 60, 255), (255, 80, 255), (235, 235, 235)
)


def synthetic_clip(
    db: ConstellationDB, name: str, frames: int, seed: int
) -> Iterator[NDArray[np.uint8]]:
    """Yield frames of a synthetic sky (see module docstring)."""
    return demo_sky_clip(db[name], frames, seed=seed, width=WIDTH, height=HEIGHT)


def read_video(path: Path) -> Iterator[NDArray[np.uint8]]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise SystemExit(f"Could not open video: {path}")
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            yield frame
    finally:
        capture.release()


def read_image(path: Path, repeats: int) -> Iterator[NDArray[np.uint8]]:
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        raise SystemExit(f"Could not read image: {path}")
    for _ in range(repeats):  # repeat so debounced events can fire
        yield frame


def draw_report(
    frame: NDArray[np.uint8], report: FrameReport, pipeline: SkyPipeline
) -> NDArray[np.uint8]:
    """Annotate a frame with stars, constellation lines, ghosts and flags."""
    canvas = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame.copy()
    satellites = {s.track_id for s in report.satellites}
    anomalies = set(report.anomalies)

    for match in report.constellations:
        for (x0, y0), (x1, y1) in match.line_segments:
            cv2.line(canvas, (int(x0), int(y0)), (int(x1), int(y1)), GOLD, 2, cv2.LINE_AA)
        for name, (gx, gy) in match.ghost_positions.items():
            cv2.circle(canvas, (int(gx), int(gy)), 9, CYAN, 1, cv2.LINE_AA)
            cv2.putText(canvas, f"{name} (ghost)", (int(gx) + 12, int(gy) + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, CYAN, 1, cv2.LINE_AA)
        xs = [p[0] for seg in match.line_segments for p in seg]
        ys = [p[1] for seg in match.line_segments for p in seg]
        label = f"{match.constellation} ({match.confidence:.2f})"
        cv2.putText(canvas, label, (int(min(xs)), max(int(min(ys)) - 14, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, GOLD, 2, cv2.LINE_AA)

    for track in report.tracks:
        if not track.visible:
            continue
        center = (int(round(track.x)), int(round(track.y)))
        if track.id in satellites:
            pts = np.array(track.trajectory, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(canvas, [pts], False, RED, 2, cv2.LINE_AA)
            cv2.circle(canvas, center, 8, RED, 2, cv2.LINE_AA)
            cv2.putText(canvas, "satellite", (center[0] + 10, center[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, RED, 1, cv2.LINE_AA)
        elif track.id in anomalies:
            cv2.circle(canvas, center, 10, MAGENTA, 2, cv2.LINE_AA)
            cv2.putText(canvas, "anomaly (not in catalog)", (center[0] + 12, center[1] + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, MAGENTA, 1, cv2.LINE_AA)
        else:
            cv2.circle(canvas, center, 7, GREEN, 1, cv2.LINE_AA)

    cv2.putText(canvas, f"frame {report.frame_idx}", (12, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 1, cv2.LINE_AA)
    return canvas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--image", type=Path, help="run on a single image")
    source.add_argument("--video", type=Path, help="run on a video file")
    parser.add_argument("--constellation", default="Orion",
                        help="constellation for the synthetic clip (default: Orion)")
    parser.add_argument("--frames", type=int, default=60, help="synthetic clip length")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "demo_reasoning.png")
    args = parser.parse_args(argv)

    db = ConstellationDB.from_config(args.config)
    db.load()
    config = PipelineConfig.from_file(args.config)
    pipeline = SkyPipeline(db, config)

    if args.image:
        frames = read_image(args.image, config.temporal.debounce_frames + 1)
        source_name = str(args.image)
    elif args.video:
        frames = read_video(args.video)
        source_name = str(args.video)
    else:
        if args.constellation not in db:
            raise SystemExit(
                f"Unknown constellation {args.constellation!r}. "
                f"Choose from: {', '.join(db.list_constellations())}"
            )
        frames = synthetic_clip(db, args.constellation, args.frames, args.seed)
        source_name = f"synthetic {args.constellation} clip ({args.frames} frames)"

    print(f"AstraGraph reasoning demo — {source_name}\n")
    event_counts: Counter[str] = Counter()
    reported_satellites: set[int] = set()
    report: FrameReport | None = None
    last_frame: NDArray[np.uint8] | None = None
    for idx, frame in enumerate(frames):
        report = pipeline.process(frame, idx)
        last_frame = frame
        for event in report.events:
            event_counts[event.type.value] += 1
            if event.type in (EventType.DISAPPEARS, EventType.LINEAR_TRAJECTORY):
                print(f"  [frame {event.t:3d}] {event.type.value:17s} track {event.args['id']}")
        for sat in report.satellites:
            if sat.track_id not in reported_satellites:
                reported_satellites.add(sat.track_id)
                print(f"  [frame {idx:3d}] {sat.describe()}")

    if report is None or last_frame is None:
        print("No frames to process.")
        return 1

    print("\nTemporal events:", ", ".join(f"{k}={v}" for k, v in sorted(event_counts.items()))
          or "none")
    print(f"Stars visible in final frame: {sum(t.visible for t in report.tracks)}\n")

    if report.constellations:
        for match in report.constellations:
            print(f"Detected constellation: {match.constellation} "
                  f"(confidence: {match.confidence:.2f})")
            if match.ghost_positions:
                hidden = ", ".join(sorted(match.ghost_positions))
                print(f"  X-Ray: inferred hidden stars → {hidden}")
    else:
        print("No constellation identified.")
    for sat in report.satellites:
        print(sat.describe())
    for track_id in report.anomalies:
        track = next(t for t in report.tracks if t.id == track_id)
        print(f"Anomaly: bright object not in catalog at ({track.x:.0f}, {track.y:.0f}) "
              f"— possibly a planet")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.output), draw_report(last_frame, report, pipeline))
    print(f"\nAnnotated frame written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
