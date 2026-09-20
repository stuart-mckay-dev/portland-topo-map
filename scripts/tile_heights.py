#!/usr/bin/env python3
"""
tile_heights.py -- Report the printed Z height each tile will actually reach,
and recommend a hollowing strategy per tile.

Only the tile containing the West Hills high point needs full height; most are
far shorter. Use this to plan plate packing, to seed csv/tiles.csv, and to
choose per-tile hollowing (see docs/10-hollow-base-strategies.md).

  python3 scripts/tile_heights.py --heightmaps data/heightmaps --relief-mm 193.2
  python3 scripts/tile_heights.py --heightmaps data/heightmaps --relief-mm 193.2 --stats
  python3 scripts/tile_heights.py --heightmaps data/heightmaps --relief-mm 193.2 --csv
"""
from __future__ import annotations
import argparse, glob, os, sys

try:
    import numpy as np, rasterio
except ImportError:
    sys.exit("Needs rasterio and numpy:  pip install rasterio numpy")

# Crossover from docs/10: below this mean height RIB_BOX wins, above it
# RIB_SHELL / SHELL_SUP win. Regenerate with:
#   python3 scripts/hollow_model.py --crossover
CROSSOVER_MM = 60.0


def strategy(mean_z):
    return "RIB_BOX" if mean_z < CROSSOVER_MM else "RIB_SHELL"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--heightmaps", required=True)
    ap.add_argument("--relief-mm", type=float, required=True,
                    help="FULL project relief in mm at the chosen exaggeration")
    ap.add_argument("--base-mm", type=float, default=10.0)
    ap.add_argument("--csv", action="store_true")
    ap.add_argument("--stats", action="store_true",
                    help="also report min/mean fractions for hollow_model.py")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.heightmaps, "*.tif")))
    if not files:
        sys.exit("no heightmaps found")

    rows = []
    for f in files:
        with rasterio.open(f) as src:
            arr = src.read(1).astype("float64") / 65535.0
        n_min, n_mean, n_max = float(arr.min()), float(arr.mean()), float(arr.max())
        rows.append({
            "tile": os.path.splitext(os.path.basename(f))[0],
            "n_min": n_min, "n_mean": n_mean, "n_max": n_max,
            "z_min": a.base_mm + n_min * a.relief_mm,
            "z_mean": a.base_mm + n_mean * a.relief_mm,
            "z_max": a.base_mm + n_max * a.relief_mm,
        })

    if a.csv:
        print("tile_id,z_min_mm,z_mean_mm,z_max_mm,n_min,n_mean,n_max,strategy")
        for r in rows:
            print(f"{r['tile']},{r['z_min']:.2f},{r['z_mean']:.2f},"
                  f"{r['z_max']:.2f},{r['n_min']:.4f},{r['n_mean']:.4f},"
                  f"{r['n_max']:.4f},{strategy(r['z_mean'])}")
        return

    print(f"\n{'tile':<24} {'Z min':>8} {'Z mean':>8} {'Z max':>8} {'strategy':>11}")
    print("-" * 64)
    for r in sorted(rows, key=lambda x: -x["z_max"]):
        print(f"{r['tile']:<24} {r['z_min']:>6.1f}mm {r['z_mean']:>6.1f}mm "
              f"{r['z_max']:>6.1f}mm {strategy(r['z_mean']):>11}")
    print("-" * 64)
    tallest = max(r["z_max"] for r in rows)
    print(f"tallest {tallest:.1f}mm | expected peak "
          f"{a.base_mm + a.relief_mm:.1f}mm")
    if tallest < a.base_mm + a.relief_mm * 0.98:
        print("[!] No tile reaches the project high point -- check normalisation.")

    n_box = sum(1 for r in rows if strategy(r["z_mean"]) == "RIB_BOX")
    print(f"\nhollowing split: {n_box} x RIB_BOX, {len(rows)-n_box} x RIB_SHELL")
    print("see docs/10-hollow-base-strategies.md")

    if a.stats:
        print("\nArchetypes for scripts/hollow_model.py "
              "(replace the placeholders in tiles()):")
        srt = sorted(rows, key=lambda x: x["z_mean"])
        for label, r in [("flats", srt[0]),
                         ("mixed", srt[len(srt) // 2]),
                         ("hills", srt[-1])]:
            print(f'  Tile("{label.upper()} TILE ({r["tile"]})", w, h, '
                  f'{r["n_min"]:.4f}, {r["n_mean"]:.4f}, {r["n_max"]:.4f}),')
        counts = {}
        for r in rows:
            k = "flats" if r["z_mean"] < 25 else ("mixed" if r["z_mean"] < CROSSOVER_MM else "hills")
            counts[k] = counts.get(k, 0) + 1
        print(f"\n  BUILD_MIX = {[(k, v) for k, v in counts.items()]}")
    print()


if __name__ == "__main__":
    main()
