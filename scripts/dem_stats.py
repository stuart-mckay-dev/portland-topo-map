#!/usr/bin/env python3
"""
dem_stats.py -- Report the statistics topo_params.py needs to stop guessing.

The important output is `mean_fraction`: where the mean elevation sits within
the full elevation range. topo_params.py uses it to estimate filament mass and
print time, and ships with a placeholder of 0.17. Replace it with the real
number as soon as you have a DEM.

Usage:
  python3 dem_stats.py data/derived/portland_dem.tif
  python3 dem_stats.py data/derived/portland_dem.tif --hist

Requires rasterio and numpy:  pip install rasterio numpy
"""

from __future__ import annotations
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from topo_params import (BBOX_W_M, BBOX_H_M,       # single source of truth
                             ELEV_MIN_M, ELEV_MAX_M)
except Exception:
    BBOX_W_M = BBOX_H_M = ELEV_MIN_M = ELEV_MAX_M = None

try:
    import numpy as np
    import rasterio
except ImportError:
    sys.exit("Needs rasterio and numpy:  pip install rasterio numpy")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dem")
    ap.add_argument("--hist", action="store_true", help="print an ASCII histogram")
    ap.add_argument("--bands", type=int, default=6,
                    help="suggest N equal-population elevation bands")
    a = ap.parse_args()

    with rasterio.open(a.dem) as src:
        arr = src.read(1, masked=True)
        crs, res = src.crs, src.res
        bounds = src.bounds
        geographic = bool(crs and crs.is_geographic)
        grid_cells = src.height * src.width

    # Ground extent, so we can tell a project-wide DEM from a test crop.
    if geographic:
        midlat = (bounds.bottom + bounds.top) / 2.0
        ext_w = (bounds.right - bounds.left) * 111_320.0 * math.cos(math.radians(midlat))
        ext_h = (bounds.top - bounds.bottom) * 111_320.0
    else:
        ext_w = bounds.right - bounds.left
        ext_h = bounds.top - bounds.bottom
    coverage = None
    if BBOX_W_M:
        coverage = (ext_w * ext_h) / (BBOX_W_M * BBOX_H_M)

    v = arr.compressed().astype("float64")
    lo, hi = float(v.min()), float(v.max())
    rng = hi - lo
    mean = float(v.mean())
    frac = (mean - lo) / rng if rng else 0.0

    print()
    print(f"  file            {a.dem}")
    print(f"  CRS             {crs}")
    if geographic:
        midlat = (bounds.bottom + bounds.top) / 2.0
        gx = res[0] * 111_320.0 * math.cos(math.radians(midlat))
        gy = res[1] * 111_320.0
        print(f"  pixel size      {res[0]:.6f} x {res[1]:.6f} DEGREES "
              f"(~{gx:.1f} x {gy:.1f} m)")
        print(f"  [!] GEOGRAPHIC CRS. Reproject to a projected CRS (EPSG:32610 or")
        print(f"      6559) BEFORE any resample, buffer or slope step. A -tr in")
        print(f"      degrees is not a ground resolution.")
    else:
        print(f"  pixel size      {res[0]:.3f} x {res[1]:.3f} (CRS units)")
    print(f"  ground extent   {ext_w:,.0f} x {ext_h:,.0f} m")
    if coverage is not None:
        print(f"  project cover   {100*coverage:.1f}% of the {BBOX_W_M:,.0f} x "
              f"{BBOX_H_M:,.0f} m bbox")
    fill = v.size / grid_cells if grid_cells else 1.0
    print(f"  valid cells     {v.size:,} of {grid_cells:,} grid cells "
          f"({100*fill:.1f}% filled)")
    print()
    print(f"  min             {lo:>12.3f}")
    print(f"  max             {hi:>12.3f}")
    print(f"  range           {rng:>12.3f}")
    print(f"  mean            {mean:>12.3f}")
    print(f"  median          {float(np.median(v)):>12.3f}")
    print()
    print(f"  >>> mean_fraction = {frac:.4f}")
    if fill > 0.90:
        print()
        print(f"      *** NOT YET -- this raster is not masked. ***")
        print(f"      {100*fill:.1f}% of the grid carries data, so this is still the raw")
        print(f"      rectangle. If the map is cut to a boundary, mask FIRST:")
        print(f"      mean_fraction is a property of the PRINTED object, and it")
        print(f"      shifts when terrain outside the line is removed.")
        print(f"      A boundary-masked Portland DEM should come back roughly")
        print(f"      50-60% filled, not {100*fill:.0f}%.")
    elif coverage is not None and coverage < 0.8:
        print()
        print(f"      *** DO NOT PASTE THIS. ***")
        print(f"      This raster covers only {100*coverage:.1f}% of the project bbox.")
        print(f"      mean_fraction is a WHOLE-MAP statistic -- it is the share of")
        print(f"      the elevation range the average cell sits at, and it drives")
        print(f"      every filament and print-time estimate in topo_params.py.")
        print(f"      A hilly test crop reads high; the flat eastside reads low.")
        print(f"      Re-run this against the FULL project DEM before touching")
        print(f"      MEAN_ELEV_FRACTION.")
    else:
        print(f"      Paste into MEAN_ELEV_FRACTION in scripts/topo_params.py")
        print(f"      and set MEAN_ELEV_FRACTION_IS_ESTIMATE = False")
    print()

    if ELEV_MAX_M is not None and (hi > ELEV_MAX_M + 0.5 or lo < ELEV_MIN_M - 0.5):
        print("  [!] OUTSIDE THE PROJECT ELEVATION CONSTANTS")
        print(f"      topo_params.py: ELEV_MIN_M = {ELEV_MIN_M}, ELEV_MAX_M = {ELEV_MAX_M}")
        print(f"      this raster:    min = {lo:.3f}, max = {hi:.3f}")
        if hi > ELEV_MAX_M + 0.5:
            over = int((v > ELEV_MAX_M).sum())
            print(f"      {over:,} cells ({100.0*over/v.size:.4f}%) sit above ELEV_MAX_M.")
            print("      qgis_export_tiles.py CLIPS normalisation to [0,1], so every")
            print("      one of those would print as a FLAT PLATEAU at full height.")
        print("      If the map is being cut to a boundary, mask FIRST -- the")
        print("      overshoot may be terrain that gets removed anyway. Then")
        print("      re-run this and set the constants from the masked DEM.")
        print()

    if hi > 1000:
        print("  [!] Max exceeds 1000 -- this DEM is probably in FEET, not metres.")
        print(f"      In metres that would be {hi * 0.3048:.1f} m.")
        print("      Convert before scaling. See docs/03-qgis-workflow.md.")
        print()

    qs = [1, 5, 25, 50, 75, 95, 99]
    print("  percentiles")
    for q in qs:
        print(f"    p{q:<3} {float(np.percentile(v, q)):>10.2f}")
    print()

    print(f"  equal-population band edges for {a.bands} AMS colours")
    edges = [float(np.percentile(v, 100.0 * i / a.bands))
             for i in range(a.bands + 1)]
    for i in range(a.bands):
        print(f"    band {i+1}   {edges[i]:>8.1f} -> {edges[i+1]:>8.1f}")
    print("    (equal-population bands give each colour equal AREA on the map;")
    print("     compare against the elevation-natural bands in docs/07.)")
    print()

    if a.hist:
        counts, bins = np.histogram(v, bins=40)
        peak = counts.max()
        print("  distribution")
        for c, b in zip(counts, bins):
            print(f"    {b:>8.1f} | {'#' * int(60 * c / peak)}")
        print()


if __name__ == "__main__":
    main()
