#!/usr/bin/env python3
"""
custom_tiles.py -- Hand-drawn, arbitrary-shape / arbitrary-size tiles.

Every other tiling path in this project (qgis_export_tiles.py,
tile_grid_explore.py, boundary_prism.py --cols/--rows) assumes a uniform
rows x cols grid. This script is for the opposite case: you draw your own
tile outlines -- any shape, any size, following whatever line you want (a
ridge, a river, "give that sliver to its neighbour") -- and this turns each
one into the heightmap + cutting-prism pair that
scripts/blender_heightmap_to_mesh.py already knows how to consume via
--heightmaps / --prism-dir / --sizes-csv.

Author the shapes in QGIS
-------------------------
1. Layer > Create Layer > New GeoJSON Layer, Polygon, project CRS
   (EPSG:32610), one text field named `tile_id`.
2. Toggle editing, digitize one polygon per tile, give each a filesystem-safe
   tile_id (e.g. "r02c04_merged", "westhills_a"). Overlap the city boundary
   freely -- --clip (the default) trims each one to it for you, so you do not
   need to trace the coastline by hand. Pass --no-clip if you want the raw
   shapes used as-is (e.g. tiles that are meant to run past the boundary).
3. Save as data/vectors/<name>.geojson.

Two-step workflow, same shape as tile_grid_explore.py -> boundary_prism.py:

  check   Report each tile's ground size, how much of the drawn shape
          survives the boundary clip, and its printed footprint/diagonal at
          your scale -- flags the 200 mm hard cap and any tile-vs-tile
          overlap. Writes nothing.

  build   For each tile: clip a heightmap raster to its bounding box (plus a
          margin, so the boolean and the resample edge both have clean
          overhang -- the margin becomes part of the mesh footprint, same as
          the ~500 m margin the whole-map DEM already carries around the
          city), normalise it with the SAME project-wide ELEV_MIN_M /
          ELEV_MAX_M as qgis_export_tiles.py, and build a watertight cutting
          prism with the same code boundary_prism.py uses -- n-gon caps,
          forced CCW winding, signed-volume and manifold checks. A bad
          polygon is refused, not silently boolean'd into garbage, same as
          boundary_prism.py's own behaviour. Also writes tile_sizes.csv,
          because custom tiles are not one uniform footprint the way a grid
          is -- see blender_heightmap_to_mesh.py's --sizes-csv.

Usage
-----
  python3 scripts/custom_tiles.py check \\
      --shapes data/vectors/my_custom_tiles.geojson \\
      --boundary data/vectors/boundary_smoothed.geojson \\
      --scale-denom 92593

  python3 scripts/custom_tiles.py build \\
      --shapes data/vectors/my_custom_tiles.geojson \\
      --boundary data/vectors/boundary_smoothed.geojson \\
      --dem data/derived/portland_dem_smooth.tif \\
      --scale-denom 92593 \\
      --out-heightmaps data/heightmaps_custom \\
      --out-prisms data/prisms_custom

Then:
  blender -b -P scripts/blender_heightmap_to_mesh.py -- \\
      --heightmaps data/heightmaps_custom --pattern "*.png" \\
      --prism-dir data/prisms_custom \\
      --sizes-csv data/heightmaps_custom/tile_sizes.csv \\
      --tile-w 90 --tile-h 90 --relief-mm <full-range-relief-mm> \\
      --out data/tiles_custom
  (--tile-w/--tile-h there are only the fallback for a heightmap missing
  from tile_sizes.csv -- every tile listed in it uses its own size.)

--scale-denom is the same number topo_params.py prints as "Horizontal scale"
for whatever grid/exaggeration plan you're working from -- pass that value,
do not invent a new one, or a custom tile will not line up with the rest of
the map.
"""
from __future__ import annotations
import argparse, csv, json, os, sys

try:
    from shapely.geometry import shape
    from shapely.ops import unary_union, transform as shp_transform
except ImportError:
    sys.exit("Needs shapely:  pip install shapely")
try:
    import rasterio
    from rasterio.windows import Window
    from rasterio.transform import array_bounds
    import numpy as np
except ImportError:
    sys.exit("Needs rasterio and numpy:  pip install rasterio numpy")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boundary_prism import build_ngon, signed_volume, edge_report_faces, write_obj
try:
    from topo_params import ELEV_MIN_M, ELEV_MAX_M
    _ELEV_SRC = "topo_params.py"
except Exception:
    ELEV_MIN_M, ELEV_MAX_M = 0.19, 362.0
    _ELEV_SRC = "fallback (could not import topo_params.py)"


def load_tiles(path):
    with open(path) as f:
        gj = json.load(f)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    tiles = []
    for i, ft in enumerate(feats):
        geom = shape(ft["geometry"])
        tid = (ft.get("properties") or {}).get("tile_id") or f"tile{i + 1:02d}"
        tiles.append((str(tid), geom))
    if not tiles:
        sys.exit(f"  [X] no polygon features found in {path}")
    seen = set()
    for tid, _ in tiles:
        if tid in seen:
            sys.exit(f"  [X] duplicate tile_id '{tid}' -- every tile needs a "
                      f"unique id, it becomes the output filename stem")
        seen.add(tid)
    return tiles


def load_boundary(path):
    if not path:
        return None
    with open(path) as f:
        gj = json.load(f)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    return unary_union([shape(ft["geometry"]) for ft in feats if ft.get("geometry")])


def safe_name(tid):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in tid)


def clip_to_boundary(geom, boundary, no_clip):
    if boundary is None or no_clip:
        return geom
    return geom.intersection(boundary)


def cmd_check(a):
    tiles = load_tiles(a.shapes)
    boundary = load_boundary(a.boundary)
    print(f"{len(tiles)} tile(s) in {a.shapes}")
    if boundary is None and not a.no_clip:
        print("  (no --boundary given -- shapes used exactly as drawn)")
    print()

    clipped = {}
    issues = 0
    for tid, geom in tiles:
        g = clip_to_boundary(geom, boundary, a.no_clip)
        clipped[tid] = g
        if g.is_empty or g.area <= 0:
            print(f"  {tid:20s} EMPTY after clipping to the boundary -- nothing to cut")
            issues += 1
            continue
        minx, miny, maxx, maxy = g.bounds
        w_m, h_m = maxx - minx, maxy - miny
        area_km2 = g.area / 1e6
        fill_pct = 100 * g.area / geom.area if geom.area else 0
        w_mm = w_m * 1000 / a.scale_denom
        h_mm = h_m * 1000 / a.scale_denom
        diag_mm = (w_mm ** 2 + h_mm ** 2) ** 0.5
        over_cap = max(w_mm, h_mm, diag_mm) > a.max_mm
        flag = "  [!] EXCEEDS the printer cap" if over_cap else ""
        print(f"  {tid:20s} {w_m:7,.0f} x {h_m:7,.0f} m  ({area_km2:6.3f} km2, "
              f"{fill_pct:5.1f}% of the drawn shape survives the clip)")
        print(f"  {'':20s} -> {w_mm:6.1f} x {h_mm:6.1f} mm  diagonal "
              f"{diag_mm:6.1f} mm{flag}")
        if over_cap:
            issues += 1

    ids = list(clipped)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            gi, gj_ = clipped[ids[i]], clipped[ids[j]]
            if gi.is_empty or gj_.is_empty:
                continue
            inter_area = gi.intersection(gj_).area
            if inter_area > 1.0:   # ignore sub-m2 touching-edge rounding
                print(f"\n  [!] {ids[i]} and {ids[j]} OVERLAP by "
                      f"{inter_area:.0f} m2 -- that ground gets modelled twice.")
                issues += 1

    print(f"\n{'All clear.' if not issues else str(issues) + ' issue(s) above.'}")


def clip_heightmap(dem_path, bbox, margin_m, out_stem):
    minx, miny, maxx, maxy = bbox
    minx -= margin_m; miny -= margin_m; maxx += margin_m; maxy += margin_m
    with rasterio.open(dem_path) as src:
        inv = ~src.transform
        px0, py0 = inv * (minx, maxy)          # top-left
        px1, py1 = inv * (maxx, miny)          # bottom-right
        gx0, gy0 = max(0, int(np.floor(px0))), max(0, int(np.floor(py0)))
        gx1 = min(src.width, int(np.ceil(px1)))
        gy1 = min(src.height, int(np.ceil(py1)))
        if gx0 >= gx1 or gy0 >= gy1:
            sys.exit(f"  [X] {out_stem}: requested extent falls outside {dem_path}")
        win = Window(gx0, gy0, gx1 - gx0, gy1 - gy0)
        data = src.read(1, window=win, masked=True)
        rng = ELEV_MAX_M - ELEV_MIN_M
        filled = np.ma.filled(data, ELEV_MIN_M).astype("float64")
        norm = (filled - ELEV_MIN_M) / rng
        np.clip(norm, 0.0, 1.0, out=norm)
        u16 = (norm * 65535.0).round().astype("uint16")
        transform = src.window_transform(win)
        prof = src.profile.copy()
        prof.update(driver="GTiff", dtype="uint16", count=1, nodata=None,
                    height=u16.shape[0], width=u16.shape[1],
                    transform=transform, compress="deflate")
        tif_path = out_stem + ".tif"
        with rasterio.open(tif_path, "w", **prof) as dst:
            dst.write(u16, 1)
        bounds = array_bounds(u16.shape[0], u16.shape[1], transform)  # l,b,r,t

    import shutil, subprocess
    png_path = out_stem + ".png"
    if shutil.which("gdal_translate"):
        subprocess.run(["gdal_translate", "-q", "-of", "PNG", "-ot", "UInt16",
                         tif_path, png_path], check=True)
    else:
        print(f"  [!] gdal_translate not found -- only wrote {tif_path}. "
              f"Blender cannot read compressed 16-bit GeoTIFF; install GDAL "
              f"or convert to PNG before importing, or it will silently "
              f"displace nothing.")
        png_path = None
    return tif_path, png_path, bounds


def cmd_build(a):
    tiles = load_tiles(a.shapes)
    boundary = load_boundary(a.boundary)
    os.makedirs(a.out_heightmaps, exist_ok=True)
    os.makedirs(a.out_prisms, exist_ok=True)
    print(f"elevation range {ELEV_MIN_M:.2f} .. {ELEV_MAX_M:.2f} m  [{_ELEV_SRC}]")
    print(f"scale  1 : {a.scale_denom:,.0f}   margin {a.margin_m:.0f} m\n")

    sizes_rows = []
    for tid, geom in tiles:
        g = clip_to_boundary(geom, boundary, a.no_clip)
        if g.is_empty or g.area <= 0:
            print(f"  {tid:20s} EMPTY after clipping -- skipped")
            continue

        name = "pdx_custom_" + safe_name(tid)
        stem = os.path.join(a.out_heightmaps, name)
        tif_path, png_path, bounds = clip_heightmap(a.dem, g.bounds, a.margin_m, stem)
        left, bottom, right, top = bounds
        rw, rh = right - left, top - bottom

        # The RASTER's clipped extent (margin included) becomes the mesh's
        # full footprint -- exactly like the whole-map pipeline, where the
        # DEM carries margin around the city and the prism trims it down.
        # Deriving tile_w/h from the drawn polygon's own (unbuffered) bounds
        # instead would leave the raster covering MORE ground than the mesh
        # claims to be, and the UV 0..1 -> mm mapping would drift off by
        # exactly the margin.
        tile_w_mm = rw * 1000 / a.scale_denom
        tile_h_mm = rh * 1000 / a.scale_denom
        sx, sy = tile_w_mm / rw, tile_h_mm / rh
        if abs(sx - sy) / max(sx, sy) > 0.01:
            print(f"  {tid:20s} [!] X/Y scale differ by "
                  f"{100 * abs(sx - sy) / max(sx, sy):.2f}% -- rounding in the "
                  f"raster clip. Usually harmless at this margin; check if "
                  f"it looks stretched.")

        def to_mm(x, y, z=None, _left=left, _bottom=bottom, _sx=sx, _sy=sy,
                  _tw=tile_w_mm, _th=tile_h_mm):
            return ((x - _left) * _sx - _tw / 2.0, (y - _bottom) * _sy - _th / 2.0)

        poly_mm = shp_transform(to_mm, g)
        verts, faces = build_ngon(poly_mm, a.z_min, a.z_max)
        nedges, nbad = edge_report_faces(faces)
        vol = signed_volume(verts, faces)
        tag = "watertight" if nbad == 0 else f"[!] {nbad} NON-MANIFOLD"
        print(f"  {tid:20s} footprint {tile_w_mm:6.1f} x {tile_h_mm:6.1f} mm  "
              f"signed volume {vol:+,.0f} mm3  {tag}")
        if vol <= 0:
            sys.exit(f"\n  [X] {tid}: NEGATIVE signed volume -- prism is "
                      f"inside-out. It will render fine and boolean to "
                      f"nothing. See boundary_prism.py's note on ring "
                      f"winding.\n")
        if nbad and not a.force:
            sys.exit(f"\n  [X] {tid}: refusing to write a non-manifold prism "
                      f"({nbad} bad edges) -- a leaky cutter makes Blender's "
                      f"boolean emit garbage rather than fail. Almost always "
                      f"shapely < 2.1; see boundary_prism.py's fallback "
                      f"warning. Override with --force only if you know why.\n")

        prism_path = os.path.join(a.out_prisms, name + "_prism.obj")
        write_obj(prism_path, verts, faces, name=name)
        sizes_rows.append((name, f"{tile_w_mm:.3f}", f"{tile_h_mm:.3f}"))
        if max(tile_w_mm, tile_h_mm) > a.max_mm:
            print(f"  {'':20s} [!] {max(tile_w_mm, tile_h_mm):.1f} mm exceeds "
                  f"the {a.max_mm:.0f} mm printer cap")

    if not sizes_rows:
        sys.exit("\n  [X] nothing built -- every tile was empty after clipping.\n")

    sizes_csv = os.path.join(a.out_heightmaps, "tile_sizes.csv")
    with open(sizes_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "tile_w_mm", "tile_h_mm"])
        w.writerows(sizes_rows)

    print(f"\nwrote {len(sizes_rows)} tile(s) to {a.out_heightmaps} / {a.out_prisms}")
    print(f"wrote {sizes_csv}")
    print("\nNext:")
    print(f"  blender -b -P scripts/blender_heightmap_to_mesh.py -- \\")
    print(f"      --heightmaps {a.out_heightmaps} --pattern '*.png' \\")
    print(f"      --prism-dir {a.out_prisms} --sizes-csv {sizes_csv} \\")
    print(f"      --tile-w 90 --tile-h 90 --relief-mm <full-range-relief-mm> \\")
    print(f"      --out data/tiles_custom")
    print("  (--tile-w/--tile-h there are only the fallback for a tile NOT")
    print("   in tile_sizes.csv -- every listed one uses its own size.)")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="report sizes/fit, write nothing")
    p_check.add_argument("--shapes", required=True)
    p_check.add_argument("--boundary", default=None)
    p_check.add_argument("--no-clip", action="store_true")
    p_check.add_argument("--scale-denom", type=float, required=True)
    p_check.add_argument("--max-mm", type=float, default=200.0)
    p_check.set_defaults(func=cmd_check)

    p_build = sub.add_parser("build", help="write heightmaps + prisms + sizes csv")
    p_build.add_argument("--shapes", required=True)
    p_build.add_argument("--boundary", default=None)
    p_build.add_argument("--no-clip", action="store_true")
    p_build.add_argument("--dem", required=True)
    p_build.add_argument("--scale-denom", type=float, required=True)
    p_build.add_argument("--margin-m", type=float, default=150.0,
                          help="ground margin clipped around each tile's bbox "
                               "for clean resampling + boolean overhang -- "
                               "becomes part of the mesh footprint")
    p_build.add_argument("--z-min", type=float, default=-5.0)
    p_build.add_argument("--z-max", type=float, default=60.0)
    p_build.add_argument("--max-mm", type=float, default=200.0)
    p_build.add_argument("--force", action="store_true")
    p_build.add_argument("--out-heightmaps", required=True)
    p_build.add_argument("--out-prisms", required=True)
    p_build.set_defaults(func=cmd_build)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
