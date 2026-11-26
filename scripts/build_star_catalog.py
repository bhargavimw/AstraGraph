"""Build ``data/bright_stars.csv`` from the HYG star database.

The bundled catalog is a subset of HYG v4.1 (https://github.com/astronexus/HYG-Database,
CC BY-SA 4.0): the brightest stars by apparent magnitude, excluding the Sun
and entries without a Hipparcos number (duplicate companion entries).

Usage:
    curl -L -o hygdata_v41.csv \\
      https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT/hygdata_v41.csv
    python scripts/build_star_catalog.py hygdata_v41.csv --count 300

Columns written:
    name          proper name, else Bayer/Flamsteed designation, else "HIP <n>"
    hip           Hipparcos catalog number
    ra_hours      right ascension, J2000.0, hours
    dec_degrees   declination, J2000.0, degrees
    magnitude     apparent visual magnitude
    pmra_mas      proper motion in RA (mu_alpha * cos dec), mas/year
    pmdec_mas     proper motion in Dec, mas/year
    parallax_mas  parallax, mas (from HYG distance in parsecs)
    constellation IAU constellation abbreviation
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "name", "hip", "ra_hours", "dec_degrees", "magnitude",
    "pmra_mas", "pmdec_mas", "parallax_mas", "constellation",
]


def display_name(row: dict[str, str]) -> str:
    """Proper name, else a tidy Bayer/Flamsteed label ("9Alp CMa" → "Alp CMa")."""
    if row["proper"].strip():
        return row["proper"].strip()
    designation = re.sub(r"^\d+", "", row["bf"].strip()).strip()
    if designation:
        return re.sub(r"\s+", " ", designation)
    return f"HIP {int(float(row['hip']))}"


def build(source: Path, count: int) -> list[dict[str, str]]:
    with source.open(newline="", encoding="utf-8") as handle:
        rows = [
            r for r in csv.DictReader(handle)
            if r["id"] != "0" and r["hip"].strip() and r["mag"].strip()
        ]
    rows.sort(key=lambda r: float(r["mag"]))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        name = display_name(row)
        if name in seen:
            name = f"{name} (HIP {int(float(row['hip']))})"
        seen.add(name)
        dist = float(row["dist"]) if row["dist"].strip() else 0.0
        parallax = 1000.0 / dist if 0.0 < dist < 100000.0 else 0.0
        out.append({
            "name": name,
            "hip": str(int(float(row["hip"]))),
            "ra_hours": f"{float(row['ra']):.6f}",
            "dec_degrees": f"{float(row['dec']):.6f}",
            "magnitude": f"{float(row['mag']):.2f}",
            "pmra_mas": f"{float(row['pmra'] or 0):.2f}",
            "pmdec_mas": f"{float(row['pmdec'] or 0):.2f}",
            "parallax_mas": f"{parallax:.3f}",
            "constellation": row["con"].strip(),
        })
        if len(out) == count:
            break
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract bright stars from HYG.")
    parser.add_argument("source", type=Path, help="path to hygdata_v41.csv")
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "bright_stars.csv")
    args = parser.parse_args(argv)

    stars = build(args.source, args.count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        handle.write(
            "# Brightest stars from the HYG database v4.1 "
            "(https://github.com/astronexus/HYG-Database), CC BY-SA 4.0.\n"
            "# Regenerate with scripts/build_star_catalog.py. J2000.0 ICRS.\n"
        )
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(stars)
    print(f"Wrote {len(stars)} stars (faintest magnitude "
          f"{stars[-1]['magnitude']}) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
