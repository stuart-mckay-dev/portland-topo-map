#!/usr/bin/env python3
"""
tile_grid_explore.py -- Choose a tile grid that produces real sections, not
off-cuts, and see it before committing.

The problem
-----------
The default grid divides the RASTER extent. That extent carries ~500 m of
margin on every side (the bbox was sized to clear the city limits), so the
outer tiles spend part of their footprint on empty ground. Combined with a
boundary cut, some tiles come back holding a few percent of city -- slivers
that read as offcuts rather than as panels of a map.

What this does
--------------
Fits the grid to the BOUNDARY's extent instead, and searches sub-tile offsets
to find the placement that maximises the weakest tile. Scores each candidate
by how many tiles land in the "offcut" band, then renders the result.

Usage
-----
  # search: rank grid shapes and offsets
  python3 scripts/tile_grid_explore.py \\
      --boundary data/vectors/boundary_smoothed.geojson --search

  # render one specific choice
  python3 scripts/tile_grid_explore.py \\
      --boundary data/vectors/boundary_smoothed.geojson \\
      --cols 4 --rows 3 --offset-x 0.0 --offset-y 0.0 \\
      --png data/grid_4x3.png --grid-out data/vectors/grid_4x3.geojson

The GeoJSON drops straight into QGIS over the boundary layer.
"""
from __future__ import annotations
import argparse, json, sys

try:
    from shapely.geometry import shape, box, mapping
    from shapely.ops import unary_union
except ImportError:
    sys.exit("Needs shapely:  pip install shapely")


def load_polygon(path):
    with open(path) as f:
        gj = json.load(f)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    g = unary_union([shape(ft["geometry"]) for ft in feats if ft.get("geometry")])
    crs = gj.get("crs")
    return g, crs


def make_grid(poly, cols, rows, fx, fy, margin):
    """Tiles sized to the boundary extent plus margin, shifted by a fraction
    of a tile. fx/fy in [-0.5, 0.5]."""
    x0, y0, x1, y1 = poly.bounds
    x0 -= margin; y0 -= margin; x1 += margin; y1 += margin
    tw = (x1 - x0) / cols
    th = (y1 - y0) / rows
    ox = x0 + fx * tw
    oy = y0 + fy * th
    # widen so the shifted grid still covers everything
    ncols = cols + (1 if fx > 0 else 0) + (1 if fx < 0 else 0)
    nrows = rows + (1 if fy > 0 else 0) + (1 if fy < 0 else 0)
    if fx > 0: ox -= tw
    if fy > 0: oy -= th
    cells = []
    for r in range(nrows):
        for c in range(ncols):
            cx = ox + c * tw
            cy = oy + r * th
            cells.append((r, c, box(cx, cy, cx + tw, cy + th)))
    return cells, tw, th


def score(poly, cells, tw, th, offcut_lo, offcut_hi):
    out = []
    area = tw * th
    for r, c, cell in cells:
        inter = poly.intersection(cell)
        frac = inter.area / area if area else 0.0
        out.append((r, c, cell, frac))
    used = [t for t in out if t[3] >= offcut_lo]
    offcuts = [t for t in used if t[3] < offcut_hi]
    empties = [t for t in out if t[3] < offcut_lo]
    worst = min((t[3] for t in used), default=0.0)
    mean = sum(t[3] for t in used) / len(used) if used else 0.0
    return out, used, offcuts, empties, worst, mean


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boundary", required=True)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--offset-x", type=float, default=0.0)
    ap.add_argument("--offset-y", type=float, default=0.0)
    ap.add_argument("--margin-m", type=float, default=200.0,
                    help="ground margin added around the boundary extent")
    ap.add_argument("--offcut-lo", type=float, default=0.02,
                    help="below this fraction a tile counts as EMPTY, not printed")
    ap.add_argument("--offcut-hi", type=float, default=0.25,
                    help="below this a printed tile reads as an OFFCUT")
    ap.add_argument("--search", action="store_true")
    ap.add_argument("--png")
    ap.add_argument("--grid-out")
    a = ap.parse_args()

    poly, crs = load_polygon(a.boundary)
    bx0, by0, bx1, by1 = poly.bounds
    print(f"\n  boundary extent {bx1-bx0:,.0f} x {by1-by0:,.0f} m   "
          f"area {poly.area/1e6:,.1f} km2")

    if a.search:
        print(f"\n  Searching. A tile below {100*a.offcut_hi:.0f}% city is an")
        print(f"  OFFCUT; below {100*a.offcut_lo:.0f}% it is empty and simply "
              f"not printed.\n")
        print(f"  {'grid':>6} {'off x':>6} {'off y':>6} {'print':>6} "
              f"{'empty':>6} {'offcut':>7} {'worst':>7} {'mean':>7}")
        print("  " + "-" * 62)
        results = []
        for cols, rows in [(4, 3), (3, 3), (3, 2), (4, 4), (5, 4), (2, 2)]:
            for fx in (-0.25, 0.0, 0.25):
                for fy in (-0.25, 0.0, 0.25):
                    cells, tw, th = make_grid(poly, cols, rows, fx, fy, a.margin_m)
                    _, used, off, emp, worst, mean = score(
                        poly, cells, tw, th, a.offcut_lo, a.offcut_hi)
                    results.append((len(off), -worst, cols, rows, fx, fy,
                                    len(used), len(emp), worst, mean, tw, th))
        results.sort()
        for (noff, _nw, cols, rows, fx, fy, nused, nemp,
             worst, mean, tw, th) in results[:14]:
            print(f"  {cols}x{rows:<4} {fx:6.2f} {fy:6.2f} {nused:6d} "
                  f"{nemp:6d} {noff:7d} {100*worst:6.1f}% {100*mean:6.1f}%")
        print("\n  Ranked by fewest offcuts, then by the strongest weakest tile.")
        print("  Re-run with --cols/--rows/--offset-x/--offset-y and --png to see one.\n")
        return

    cells, tw, th = make_grid(poly, a.cols, a.rows, a.offset_x, a.offset_y, a.margin_m)
    allt, used, off, emp, worst, mean = score(poly, cells, tw, th,
                                              a.offcut_lo, a.offcut_hi)
    print(f"  grid {a.cols}x{a.rows}  offset ({a.offset_x:+.2f}, {a.offset_y:+.2f})")
    print(f"  tile ground {tw:,.0f} x {th:,.0f} m")
    print(f"  printed {len(used)}   empty {len(emp)}   offcuts {len(off)}")
    print(f"  weakest printed tile {100*worst:.1f}%   mean {100*mean:.1f}%\n")
    for r, c, cell, frac in sorted(allt, key=lambda t: (t[0], t[1])):
        tag = "EMPTY " if frac < a.offcut_lo else ("offcut" if frac < a.offcut_hi else "")
        print(f"    r{r+1:02d}c{c+1:02d}  {100*frac:6.1f}%  {tag}")

    if a.grid_out:
        feats = []
        for r, c, cell, frac in allt:
            feats.append({"type": "Feature",
                          "properties": {"row": r + 1, "col": c + 1,
                                         "coverage": round(frac, 4)},
                          "geometry": mapping(cell)})
        out = {"type": "FeatureCollection"}
        if crs: out["crs"] = crs
        out["features"] = feats
        with open(a.grid_out, "w") as f:
            json.dump(out, f)
        print(f"\n  wrote {a.grid_out}  (load over the boundary in QGIS)")

    if a.png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPoly
        fig, ax = plt.subplots(figsize=(11, 10))
        def draw(p, **kw):
            xs, ys = p.exterior.xy
            ax.add_patch(MplPoly(list(zip(xs, ys)), **kw))
        parts = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
        for p in parts:
            draw(p, facecolor="#7ba6d0", edgecolor="#1b3a57", lw=1.2, zorder=2)
        for r, c, cell, frac in allt:
            if frac < a.offcut_lo:
                fc, ec, tc = "#00000000", "#999999", "#999999"
            elif frac < a.offcut_hi:
                fc, ec, tc = "#ff000018", "#cc2200", "#cc2200"
            else:
                fc, ec, tc = "#00000000", "#333333", "#222222"
            draw(cell, facecolor=fc, edgecolor=ec, lw=1.6, zorder=3)
            cx = cell.bounds[0] + (cell.bounds[2] - cell.bounds[0]) / 2
            cy = cell.bounds[1] + (cell.bounds[3] - cell.bounds[1]) / 2
            ax.text(cx, cy, f"r{r+1:02d}c{c+1:02d}\n{100*frac:.0f}%",
                    ha="center", va="center", fontsize=9, color=tc, zorder=4,
                    fontweight="bold" if frac >= a.offcut_hi else "normal")
        ax.set_aspect("equal")
        ax.autoscale_view()
        ax.set_title(f"{a.cols}x{a.rows} grid, offset ({a.offset_x:+.2f}, "
                     f"{a.offset_y:+.2f})   |   {len(used)} printed, "
                     f"{len(emp)} empty, {len(off)} offcut   |   "
                     f"weakest {100*worst:.0f}%", fontsize=11)
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values(): sp.set_visible(False)
        fig.tight_layout()
        fig.savefig(a.png, dpi=130)
        print(f"  wrote {a.png}")


if __name__ == "__main__":
    main()
