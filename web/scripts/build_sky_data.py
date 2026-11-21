"""Build web/lib/data/sky-catalog.json: the static star data bundled with the site.

Combines:
  * data/constellations.json      – the 8 constellation stick figures (J2000)
  * data/bright_stars.csv         – the 300 brightest stars (HYG v4.1 subset)
  * data/constellation_info.json  – mythology text
  * hygdata_v41.csv               – B−V colour index (ci) for star colours

HYG: https://github.com/astronexus/HYG-Database (CC BY-SA 4.0).

Usage (from the repository root):
    python web/scripts/build_sky_data.py path/to/hygdata_v41.csv
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "lib" / "data" / "sky-catalog.json"


def load_hyg(path: Path) -> tuple[dict[int, dict], list[dict]]:
    by_hip: dict[int, dict] = {}
    bright: list[dict] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["id"] == "0" or not row["mag"]:
                continue
            mag = float(row["mag"])
            if mag > 5.5:  # every constellation star is brighter than this
                continue
            entry = {
                "ra": float(row["ra"]) * 15.0,
                "dec": float(row["dec"]),
                "mag": mag,
                "ci": float(row["ci"]) if row["ci"] else 0.6,
            }
            bright.append(entry)
            if row["hip"]:
                by_hip[int(float(row["hip"]))] = entry
    return by_hip, bright


def separation(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def nearest_ci(name: str, ra: float, dec: float, mag: float, bright: list[dict]) -> float:
    """Colour index of the matching HYG star (position and brightness).

    Matching on brightness too means a small position error in the source data
    still finds the right star instead of a faint neighbour; the error is
    reported so the data can be corrected.
    """
    nearby = [s for s in bright if separation(ra, dec, s["ra"], s["dec"]) <= 1.5]
    if not nearby:
        raise ValueError(f"No HYG star near {name} (RA {ra}, Dec {dec})")
    best = min(nearby, key=lambda s: separation(ra, dec, s["ra"], s["dec"])
               + 2.0 * abs(s["mag"] - mag))
    gap = separation(ra, dec, best["ra"], best["dec"])
    if gap > 1.5:
        raise ValueError(f"No HYG star near {name} (RA {ra}, Dec {dec})")
    if gap > 0.2:
        print(f"WARNING: {name} in data/constellations.json is {gap:.2f}° from the "
              f"HYG position (RA {best['ra']:.4f}, Dec {best['dec']:.4f}); check the data.")
    return best["ci"]


def main(hyg_path: str) -> None:
    by_hip, bright = load_hyg(Path(hyg_path))

    stars = []
    with (ROOT / "data" / "bright_stars.csv").open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(line for line in handle if not line.startswith("#"))
        for row in rows:
            hyg = by_hip.get(int(row["hip"]))
            stars.append([
                row["name"],
                round(float(row["ra_hours"]) * 15.0, 4),
                round(float(row["dec_degrees"]), 4),
                float(row["magnitude"]),
                round(hyg["ci"], 3) if hyg else 0.6,
            ])

    figures = json.loads((ROOT / "data" / "constellations.json").read_text(encoding="utf-8"))
    info = json.loads((ROOT / "data" / "constellation_info.json").read_text(encoding="utf-8"))
    constellations = {}
    for name, record in figures["constellations"].items():
        constellations[name] = {
            "abbreviation": record["abbreviation"],
            "stars": [
                {
                    "name": s["name"],
                    "designation": s.get("designation", ""),
                    "ra": s["ra"],
                    "dec": s["dec"],
                    "magnitude": s["magnitude"],
                    "ci": round(nearest_ci(s["name"], s["ra"], s["dec"], s["magnitude"], bright), 3),
                }
                for s in record["stars"]
            ],
            "lines": record["lines"],
            "mythology": info["constellations"].get(name, {}).get("mythology", ""),
        }

    payload = {
        "source": "AstraGraph data/ (J2000 ICRS degrees); colour index from HYG v4.1 (CC BY-SA 4.0)",
        "stars": stars,
        "constellations": constellations,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB): {len(stars)} stars, "
          f"{len(constellations)} constellations")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
