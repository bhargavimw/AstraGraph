"""Build api/data/star_colors.json: B−V colour index (ci) for every star the API returns.

Covers the bright-star catalogue (data/bright_stars.csv, matched by Hipparcos
number) and every constellation star (data/constellations.json, matched by
position and brightness). Source: HYG v4.1, CC BY-SA 4.0.

Usage (from the repository root):
    python api/scripts/build_star_colors.py path/to/hygdata_v41.csv
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "api" / "data" / "star_colors.json"


def separation(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def main(hyg_path: str) -> None:
    by_hip: dict[int, float] = {}
    bright: list[tuple[float, float, float, float]] = []  # ra, dec, mag, ci
    with Path(hyg_path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["id"] == "0" or not row["mag"] or not row["ci"]:
                continue
            mag = float(row["mag"])
            if mag > 5.5:
                continue
            ci = float(row["ci"])
            if row["hip"]:
                by_hip[int(float(row["hip"]))] = ci
            bright.append((float(row["ra"]) * 15.0, float(row["dec"]), mag, ci))

    colors: dict[str, float] = {}
    with (ROOT / "data" / "bright_stars.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(line for line in handle if not line.startswith("#")):
            ci = by_hip.get(int(row["hip"]))
            if ci is not None:
                colors[row["name"]] = round(ci, 3)

    figures = json.loads((ROOT / "data" / "constellations.json").read_text(encoding="utf-8"))
    for record in figures["constellations"].values():
        for s in record["stars"]:
            nearby = [b for b in bright if separation(s["ra"], s["dec"], b[0], b[1]) <= 1.5]
            if not nearby:
                raise SystemExit(f"No HYG star near {s['name']}")
            best = min(nearby, key=lambda b: separation(s["ra"], s["dec"], b[0], b[1])
                       + 2.0 * abs(b[2] - s["magnitude"]))
            colors[s["name"]] = round(best[3], 3)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(sorted(colors.items())), indent=0) + "\n", encoding="utf-8")
    print(f"Wrote {len(colors)} colour indexes to {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
