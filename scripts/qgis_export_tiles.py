#!/usr/bin/env python3
"""
qgis_export_tiles.py -- Cut a cleaned DEM into per-tile 16-bit heightmaps
with SHARED EDGE PIXELS, so adjacent tiles mesh without a seam.

Run in the QGIS Python console, or with QGIS's bundled python. Also works with
plain rasterio outside QGIS.

  python3 scripts/qgis_export_tiles.py \
      --dem data/derived/portland_dem_smooth.tif \
      --out data/heightmaps \
      --cols 4 --rows 3 --phase pilot

Two things this script exists to get right
------------------------------------------
1. PROJECT-WIDE NORMALISATION. Elevation is normalised against the whole
   project's min/max, never per tile. Per-tile normalisation is the classic
   error: every tile uses the full 16-bit range and the terrain no longer
   lines up across seams.

2. SHARED EDGE PIXELS. Each tile is cut with a one-pixel overlap onto its
   neighbours, so both tiles generate their boundary vertices from identical
   elevation values. Independently cropped tiles produce a visible ridge or
   gutter at every joint.
"""

from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys

try:
    import numpy as np
    import rasterio
    from rasterio.windows import Window
except ImportError:
    sys.exit("Needs rasterio and numpy:  pip install rasterio numpy")

# Project elevation datum. Imported from topo_params.py rather than copied --
# these two used to be duplicated here, and a drift between them silently
# renormalises every tile so the terrain no longer lines up across seams.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from topo_params import ELEV_MIN_M, ELEV_MAX_M
    _ELEV_SRC = "topo_params.py"
except Exception:
    ELEV_MIN_M = 0.19
    ELEV_MAX_M = 362.0
    _ELEV_SRC = "fallback (could not import topo_params.py)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dem", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cols", type=int, required=True)
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--phase", default="pilot")
    ap.add_argument("--overlap-px", type=int, default=1,
                    help="shared edge pixels; 1 is correct, 0 will show seams")
    ap.add_argument("--elev-min", type=float, default=ELEV_MIN_M)
    ap.add_argument("--elev-max", type=float, default=ELEV_MAX_M)
    ap.add_argument("--png", action="store_true",
                    help="also write a 16-bit PNG beside each GeoTIFF. Blender "
                         "cannot decode single-band 16-bit DEFLATE GeoTIFFs -- "
                         "it silently loads them as 0x0 and displaces nothing.")
    ap.add_argument("--bounds", nargs=4, type=float, metavar=("XMIN","YMIN","XMAX","YMAX"),
                    help="tile THIS ground extent (CRS units) instead of the "
                         "whole raster. The raster carries margin around the "
                         "city, so dividing it puts empty ground inside the "
                         "outer tiles. Fit the grid to the boundary instead. "
                         "Must match boundary_prism.py --bounds exactly.")
    ap.add_argument("--auto-range", action="store_true",
                    help="use the DEM's own min/max instead of project constants")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)

    with rasterio.open(a.dem) as src:
        H, W = src.height, src.width
        prof = src.profile.copy()

        if a.auto_range:
            band = src.read(1, masked=True)
            lo, hi = float(band.min()), float(band.max())
            print(f"auto range from DEM: {lo:.2f} -> {hi:.2f}")
        else:
            lo, hi = a.elev_min, a.elev_max
            print(f"project range: {lo:.2f} -> {hi:.2f} m  [{_ELEV_SRC}]")

        rng = hi - lo
        if rng <= 0:
            sys.exit("Bad elevation range")

        if hi > 1000:
            print("\n  [!] Max elevation exceeds 1000. This DEM may be in FEET.")
            print("      Convert to metres before tiling.\n")

        # Window the grid to an explicit ground extent when asked. Everything
        # downstream -- prisms, tile footprints, seams -- must be cut on the
        # SAME rectangle, so this is expressed in CRS units rather than pixels.
        if a.bounds:
            bx0, by0, bx1, by1 = a.bounds
            inv = ~src.transform
            px0, py0 = inv * (bx0, by1)          # top-left
            px1, py1 = inv * (bx1, by0)          # bottom-right
            gx0, gy0 = int(round(px0)), int(round(py0))
            gx1, gy1 = int(round(px1)), int(round(py1))
            if not (0 <= gx0 < gx1 <= W and 0 <= gy0 < gy1 <= H):
                sys.exit(f"\n  [X] --bounds falls outside the raster.\n"
                         f"      raster px 0..{W} x 0..{H}, requested "
                         f"{gx0}..{gx1} x {gy0}..{gy1}\n")
            print(f"grid extent {bx1-bx0:,.0f} x {by1-by0:,.0f} m "
                  f"= px {gx1-gx0} x {gy1-gy0} of {W} x {H}")
        else:
            gx0, gy0, gx1, gy1 = 0, 0, W, H
            print("grid extent: the whole raster (includes margin around the "
                  "city -- consider --bounds)")

        GW, GH = gx1 - gx0, gy1 - gy0
        tw = GW // a.cols
        th = GH // a.rows
        print(f"DEM {W} x {H} px  ->  {a.cols} x {a.rows} tiles "
              f"of ~{tw} x {th} px  (+{a.overlap_px} px shared edge)\n")

        for r in range(a.rows):
            for c in range(a.cols):
                x0 = gx0 + c * tw
                y0 = gy0 + r * th
                x1 = gx1 if c == a.cols - 1 else x0 + tw + a.overlap_px
                y1 = gy1 if r == a.rows - 1 else y0 + th + a.overlap_px
                x1, y1 = min(x1, gx1), min(y1, gy1)

                win = Window(x0, y0, x1 - x0, y1 - y0)
                data = src.read(1, window=win, masked=True)

                filled = np.ma.filled(data, lo).astype("float64")
                norm = (filled - lo) / rng
                np.clip(norm, 0.0, 1.0, out=norm)
                u16 = (norm * 65535.0).round().astype("uint16")

                name = f"pdx_{a.phase}_r{r+1:02d}c{c+1:02d}.tif"
                path = os.path.join(a.out, name)

                p = prof.copy()
                p.update(driver="GTiff", dtype="uint16", count=1, nodata=None,
                         height=u16.shape[0], width=u16.shape[1],
                         transform=src.window_transform(win),
                         compress="deflate")
                with rasterio.open(path, "w", **p) as dst:
                    dst.write(u16, 1)

                if a.png:
                    if not shutil.which("gdal_translate"):
                        sys.exit("--png needs gdal_translate on PATH")
                    png = os.path.splitext(path)[0] + ".png"
                    subprocess.run(["gdal_translate", "-q", "-of", "PNG",
                                    "-ot", "UInt16", path, png], check=True)

                real_max = float(filled.max())
                print(f"  {name}  {u16.shape[1]}x{u16.shape[0]} px  "
                      f"max elev {real_max:7.1f} m  "
                      f"({100*(real_max-lo)/rng:5.1f}% of range)")

    print("\nNext: feed these to scripts/blender_heightmap_to_mesh.py")
    print("Blender cannot read these GeoTIFFs -- use --png and point")
    print("--pattern at '*.png', or it will displace by zero and give you a")
    print("flat sheet with no error.")
    print("Remember --relief-mm is the FULL project relief, same for every tile.")


if __name__ == "__main__":
    main()
