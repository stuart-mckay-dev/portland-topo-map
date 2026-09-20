#!/usr/bin/env python3
"""
smooth_boundary.py -- Turn a jagged jurisdictional boundary into an outline
that prints, and report how far it moved.

The problem this solves
-----------------------
Douglas-Peucker (QGIS "Simplify") only DELETES vertices. On a directional
zig-zag -- Portland's western, southern and south-eastern limits, which
staircase along PLSS section lines and annexation seams -- deleting vertices
leaves a staircase with fewer, bigger steps. It never produces the smooth
directional line the eye reads as "the edge of the city".

Three operations that actually do, applied in order:

1. MORPHOLOGICAL OPEN + CLOSE at radius D.
   close = buffer(+D).buffer(-D)   fills notches narrower than 2D
   open  = buffer(-D).buffer(+D)   removes spurs  narrower than 2D
   This deletes features by SIZE rather than by vertex count, which is the
   principled way to say "anything smaller than D is below print resolution".
   It is also self-correcting: open-then-close neither systematically inflates
   nor shrinks the polygon the way a one-sided buffer does.

2. CHAIKIN CORNER-CUTTING.
   Each iteration replaces every vertex with two points at 1/4 and 3/4 along
   its adjacent segments. The limit curve is a quadratic B-spline. Applied to a
   staircase it converges on the staircase's MEAN PATH -- which is the
   "line of best fit through the zig-zag" behaviour you want, obtained
   geometrically rather than by regression.

3. DOUGLAS-PEUCKER, last and light.
   Only to drop the redundant vertices that 1 and 2 introduce. Never as the
   primary smoother.

Why not least-squares / R^2
---------------------------
R^2 measures how well a LINE explains a set of points, and assumes y is a
function of x. A closed boundary is not a function -- it doubles back, and the
western limit runs nearly north-south, where a y-on-x fit is degenerate. The
honest analogues for "how well does this outline represent the real one" are
both reported below:

  HAUSDORFF DISTANCE  worst-case displacement, metres. The single furthest the
                      smoothed line strays from the original anywhere.
  MEAN DISPLACEMENT   symmetric-difference area / original perimeter, metres.
                      The average sideways movement. Analogous to RMSE.
  AREA RETAINED       guards against the smoother quietly eating the city.

Both distances are also printed in PRINTED MILLIMETRES at your scale, which is
the number that actually decides whether a deviation is visible.

Usage
-----
  python3 scripts/smooth_boundary.py \\
      --in  data/vectors/portland_city_limits.geojson \\
      --out data/vectors/boundary_smoothed.geojson \\
      --scale 92593 --sweep

  --sweep   try a ladder of D values, print the metrics table, write nothing
  --d 120   commit to one radius and write the output

Needs shapely. Input and output are GeoJSON in a PROJECTED CRS (EPSG:32610).
Reproject before running: metres in, metres out.
"""
from __future__ import annotations
import argparse, json, os, sys

try:
    from shapely.geometry import shape, mapping, Polygon, MultiPolygon
    from shapely.ops import unary_union
except ImportError:
    sys.exit("Needs shapely:  pip install shapely")


def load(path):
    """Returns (geometry, crs_member).

    The GeoJSON spec defaults to WGS84 lat/lon and RFC 7946 removed the `crs`
    member outright -- but GDAL and QGIS still honour the legacy one, and
    ArcGIS still writes it when you ask for a projected outSR. If we drop it,
    QGIS reads projected metres as degrees and the layer renders nowhere.
    So: carry it through.
    """
    with open(path) as f:
        gj = json.load(f)
    crs_member = gj.get("crs")
    geoms = []
    if gj.get("type") == "FeatureCollection":
        geoms = [shape(ft["geometry"]) for ft in gj["features"] if ft.get("geometry")]
    elif gj.get("type") == "Feature":
        geoms = [shape(gj["geometry"])]
    else:
        geoms = [shape(gj)]
    g = unary_union(geoms)
    if g.geom_type == "GeometryCollection":
        g = unary_union([p for p in g.geoms if p.geom_type in ("Polygon", "MultiPolygon")])
    return g, crs_member


def drop_holes(g):
    """Keep exterior rings only. Maywood Park and the unincorporated pockets go."""
    if g.geom_type == "Polygon":
        return Polygon(g.exterior)
    return MultiPolygon([Polygon(p.exterior) for p in g.geoms])


def parts(g):
    return [g] if g.geom_type == "Polygon" else list(g.geoms)


def part_report(g, label, mm):
    """Multipart boundaries are the norm here. Never drop a part silently."""
    ps = sorted(parts(g), key=lambda p: -p.area)
    print(f"  {label}: {len(ps)} part(s)")
    for i, p in enumerate(ps[:6]):
        w = p.bounds[2] - p.bounds[0]
        h = p.bounds[3] - p.bounds[1]
        print(f"      [{i}] {p.area/1e6:9,.3f} km2   bbox {w:7,.0f} x {h:7,.0f} m"
              f"   ({w/mm:5.1f} x {h/mm:5.1f} mm printed)")
    if len(ps) > 6:
        rest = sum(p.area for p in ps[6:])
        print(f"      ... {len(ps)-6} more, {rest/1e6:,.3f} km2 combined")
    return ps


def largest_part(g):
    if g.geom_type == "Polygon":
        return g
    return max(g.geoms, key=lambda p: p.area)


def drop_specks(g, mm, min_mm2):
    """Remove parts too small to print, BEFORE measuring anything.

    This is not cosmetic. Hausdorff distance on a multipart geometry is
    hijacked by deleted parts: once a stray 60 m sliver is removed, the
    metric reports the distance to that sliver -- a constant -- instead of
    how far the outline actually moved. Clear the specks first and the
    number means what it says again.
    """
    ps = parts(g)
    keep, drop = [], []
    for p in ps:
        (keep if p.area / (mm * mm) >= min_mm2 else drop).append(p)
    if drop:
        print(f"  dropped {len(drop)} part(s) below {min_mm2:g} mm2 printed:")
        for p in sorted(drop, key=lambda q: -q.area):
            print(f"      {p.area/1e6:9.4f} km2 = {p.area/(mm*mm):6.2f} mm2 printed")
    if not keep:
        return g
    return keep[0] if len(keep) == 1 else MultiPolygon(keep)


def chaikin_ring(coords, iters, closed=True):
    pts = list(coords)
    if closed and pts[0] == pts[-1]:
        pts = pts[:-1]
    for _ in range(iters):
        out = []
        n = len(pts)
        for i in range(n if closed else n - 1):
            p, q = pts[i], pts[(i + 1) % n]
            out.append((0.75 * p[0] + 0.25 * q[0], 0.75 * p[1] + 0.25 * q[1]))
            out.append((0.25 * p[0] + 0.75 * q[0], 0.25 * p[1] + 0.75 * q[1]))
        pts = out
    return pts + [pts[0]]


def chaikin(g, iters):
    if iters <= 0:
        return g
    if g.geom_type == "Polygon":
        return Polygon(chaikin_ring(g.exterior.coords, iters))
    return MultiPolygon([Polygon(chaikin_ring(p.exterior.coords, iters)) for p in g.geoms])


def _pick_nearest(components, pt):
    """The component containing the point, else the nearest one."""
    if not components:
        return None
    inside = [c for c in components if c.contains(pt)]
    if inside:
        return max(inside, key=lambda c: c.area)
    return min(components, key=lambda c: c.distance(pt))


def spot_edit(g, action, x, y, radius, mm):
    """One targeted fix at one location, instead of a global threshold.

    A blanket area threshold cannot express "these five places" -- Portland's
    outline has dozens of bays and limbs of comparable size, and a cut-off
    that reaches the ones you want will take many you don't. So each edit
    names a point.

      cut   remove the narrow-necked limb at this point. Opening bridges
            straight across the neck, which is exactly "cut it off and close
            it with a straight line".
      fill  seal the concave inlet at this point. Closing spans the mouth.
      drop  delete the detached island at this point. Never the main body.

    `radius` must exceed half the neck or mouth width to reach the feature;
    it does NOT set how much is removed -- the feature's own extent does.
    """
    from shapely.geometry import Point
    pt = Point(x, y)
    before = g.area
    main = largest_part(g)

    if action == "drop":
        ps = parts(g)
        if len(ps) < 2:
            print(f"    drop at ({x:.0f},{y:.0f}): only one part exists, nothing to drop")
            return g
        biggest = max(ps, key=lambda q: q.area)
        target = _pick_nearest([q for q in ps if q is not biggest], pt)
        keep = [q for q in ps if q is not target]
        out = keep[0] if len(keep) == 1 else MultiPolygon(keep)
        print(f"    drop at ({x:.0f},{y:.0f}): removed a detached part of "
              f"{target.area/1e6:.4f} km2 ({target.area/(mm*mm):.1f} mm2 printed)")
        return out

    if action == "cut":
        opened = main.buffer(-radius, join_style=1).buffer(radius, join_style=1)
        target = _pick_nearest(parts(main.difference(opened)), pt)
        if target is None:
            print(f"    cut at ({x:.0f},{y:.0f}): no limb found at radius {radius:g} m")
            return g
        out = g.difference(target)
        print(f"    cut  at ({x:.0f},{y:.0f}): removed a limb of "
              f"{target.area/1e6:.4f} km2, bbox "
              f"{(target.bounds[2]-target.bounds[0])/mm:.1f} x "
              f"{(target.bounds[3]-target.bounds[1])/mm:.1f} mm printed")
    elif action == "fill":
        closed = main.buffer(radius, join_style=1).buffer(-radius, join_style=1)
        target = _pick_nearest(parts(closed.difference(main)), pt)
        if target is None:
            print(f"    fill at ({x:.0f},{y:.0f}): no inlet found at radius {radius:g} m")
            return g
        out = g.union(target)
        print(f"    fill at ({x:.0f},{y:.0f}): sealed an inlet of "
              f"{target.area/1e6:.4f} km2, bbox "
              f"{(target.bounds[2]-target.bounds[0])/mm:.1f} x "
              f"{(target.bounds[3]-target.bounds[1])/mm:.1f} mm printed")
    else:
        raise SystemExit(f"unknown edit action {action!r}; use cut, fill or drop")

    print(f"           area {before/1e6:.3f} -> {out.area/1e6:.3f} km2")
    return out


def apply_edits(g, edits, mm, default_radius):
    if not edits:
        return g
    print(f"\n  Spot edits ({len(edits)}):")
    for spec in edits:
        bits = spec.split(":")
        if len(bits) < 2:
            raise SystemExit(f"bad --edit {spec!r}; want action:E,N[:radius]")
        action = bits[0].strip().lower()
        xy = bits[1].split(",")
        if len(xy) != 2:
            raise SystemExit(f"bad --edit {spec!r}; want action:E,N[:radius]")
        r = float(bits[2]) if len(bits) > 2 else default_radius
        g = spot_edit(g, action, float(xy[0]), float(xy[1]), r, mm)
    return g


def smooth(g, d, chaikin_iters=2, dp=None):
    """Morphological open+close at radius d, then Chaikin, then a light DP."""
    if d > 0:
        g = g.buffer(d, join_style=1).buffer(-d, join_style=1)    # close: fill notches
        g = g.buffer(-d, join_style=1).buffer(d, join_style=1)    # open:  shave spurs
        if g.is_empty:
            return g
    g = chaikin(g, chaikin_iters)
    if dp:
        g = g.simplify(dp, preserve_topology=True)
    return g


def nvert(g):
    if g.is_empty:
        return 0
    if g.geom_type == "Polygon":
        return len(g.exterior.coords)
    return sum(len(p.exterior.coords) for p in g.geoms)


def thinness(g):
    """Mean width proxy: 2*area/perimeter. Small = a fringe of narrow fingers,
    which is what the western limit is, rather than a fat blob with a wiggly
    edge. Morphological opening at D will amputate anything thinner than 2D."""
    per = sum(p.exterior.length for p in parts(g))
    return 2.0 * g.area / per if per else 0.0


def _boundary_points(geom, step=25.0):
    import numpy as _np
    import shapely as _sh
    out = []
    for p in parts(geom):
        L = p.exterior.length
        out.append(_sh.line_interpolate_point(p.exterior, _np.arange(0, L, step)))
    return _np.concatenate(out)


def directional(orig, new):
    """Two numbers, not one.

    AMPUTATION  = max over the ORIGINAL outline of its distance to the new
                  geometry. How deep the smoother cut material away.
    INTRUSION   = max over the NEW outline of its distance to the original.
                  How far the line bulged out across a filled notch.

    A single symmetric Hausdorff reports only the larger, so a catastrophic
    amputation and a harmless bulge look identical. They are not: amputation
    is irreversible loss of the city's shape, intrusion is claiming ground
    that was never in it.
    """
    import shapely as _sh
    amp = float(_sh.distance(_boundary_points(orig), new).max())
    intr = float(_sh.distance(_boundary_points(new), orig).max())
    return amp, intr


def metrics(orig, new, scale):
    if new.is_empty:
        return None
    mm = scale / 1000.0                       # ground metres per printed mm
    amp, intr = directional(orig, new)
    haus = max(amp, intr)
    sym = orig.symmetric_difference(new).area
    per = sum(p.exterior.length for p in parts(orig))
    mean = sym / per
    lost = orig.difference(new)      # material the smoother REMOVED
    gained = new.difference(orig)     # notches the smoother FILLED IN
    biggest_lost = max([p.area for p in parts(lost)], default=0.0) if not lost.is_empty else 0.0
    return dict(haus=haus, haus_mm=haus / mm, amp=amp, amp_mm=amp / mm,
                intr=intr, intr_mm=intr / mm, mean=mean, mean_mm=mean / mm,
                area_pct=100.0 * new.area / orig.area, nv=nvert(new),
                nparts=len(parts(new)),
                lost_km2=lost.area / 1e6, gained_km2=gained.area / 1e6,
                biggest_lost_km2=biggest_lost / 1e6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst")
    ap.add_argument("--scale", type=float, required=True,
                    help="scale denominator, e.g. 92593 for the pilot")
    ap.add_argument("--d", type=float, help="morphological radius, metres")
    ap.add_argument("--chaikin", type=int, default=2)
    ap.add_argument("--dp", type=float, help="final Douglas-Peucker tolerance, m")
    ap.add_argument("--keep-holes", action="store_true")
    ap.add_argument("--min-part-mm2", type=float, default=4.0,
                    help="drop input parts smaller than this in PRINTED mm2; "
                         "they cannot print and they corrupt the metrics")
    ap.add_argument("--largest-only", action="store_true",
                    help="keep only the biggest part; reports what it discards")
    ap.add_argument("--crs", help="override the output CRS tag, e.g. EPSG:32610. "
                                  "By default the input's crs member is carried through.")
    ap.add_argument("--edit", action="append", default=[], metavar="ACTION:E,N[:R]",
                    help="targeted fix at one point, repeatable. "
                         "cut:E,N removes the narrow-necked limb there; "
                         "fill:E,N seals the concave inlet there; "
                         "drop:E,N deletes the detached island there. "
                         "Coordinates in the working CRS. Optional radius in metres.")
    ap.add_argument("--edit-radius", type=float, default=400.0,
                    help="default reach for cut/fill edits, metres (default 400)")
    ap.add_argument("--buffer-out", metavar="PATH",
                    help="also write an OUTWARD-BUFFERED copy of the result, for "
                         "use as the raster cutline. The mask must reach past the "
                         "true line so the resampling kernel has real data at the "
                         "rim; the mesh boolean trims back to the true line later.")
    ap.add_argument("--buffer-m", type=float, default=50.0,
                    help="buffer distance for --buffer-out, metres (default 50)")
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()

    g, crs_member = load(a.src)
    if a.crs:
        crs_member = {"type": "name", "properties": {"name": a.crs}}
    if crs_member is None:
        print("  [!] Input carries no `crs` member and none was given with --crs.")
        print("      The output will be tagged WGS84 by default and QGIS will")
        print("      render it nowhere. Pass --crs EPSG:32610.")
    else:
        print(f"  crs         {crs_member.get('properties', {}).get('name', crs_member)}")
    mm = a.scale / 1000.0
    if not a.keep_holes:
        g = drop_holes(g)
    part_report(g, "input", mm)
    g = drop_specks(g, mm, a.min_part_mm2)
    if a.largest_only:
        before = g.area
        g = largest_part(g)
        if before - g.area > 0:
            print(f"  --largest-only DROPPED {(before-g.area)/1e6:,.3f} km2 of "
                  f"detached parts. Check that is what you want.\n")

    print(f"\n  source      {a.src}")
    print(f"  scale       1:{a.scale:,.0f}   1 printed mm = {mm:.1f} m of ground")
    per = sum(p.exterior.length for p in parts(g))
    thin = thinness(g)
    print(f"  area        {g.area/1e6:,.1f} km2")
    print(f"  perimeter   {per/1000:,.1f} km")
    print(f"  vertices    {nvert(g):,}")
    print(f"  mean width  {thin:,.0f} m  ({thin/mm:.1f} mm printed)  = 2*area/perimeter")
    print(f"  at scale    the whole outline is {per/mm:,.0f} mm of printed edge\n")
    if thin / mm > 20:
        print("  Mean width is large, so this is a chunky polygon overall -- the\n"
              "  narrow fingers are a LOCAL feature of the western limit, not the\n"
              "  whole shape. The column that measures them is 'lost km2': that is\n"
              "  precisely the material an opening at radius D amputates.\n")
    else:
        print("  Low mean width: much of this polygon is narrower than 2D will\n"
              "  survive. Watch 'lost km2' and 'parts' as hard as Hausdorff.\n")
    print("  lost = material removed.  gain = notches filled in. They are reported\n"
          "  separately on purpose: a near-zero NET can hide large offsetting\n"
          "  changes, and only 'lost' is irreversible.\n")

    if a.sweep or a.d is None:
        print("  Sweep. Read AMPUTATE first -- it is the irreversible column.")
        print("  0.4 mm is one extrusion width; below that, invisible. Watch for a")
        print("  CLIFF: a sudden jump means a narrow neck was severed and a whole")
        print("  limb of the city fell off. Stay on the low side of it.\n")
        dp = a.dp if a.dp else 10.0
        print(f"  Douglas-Peucker cleanup at {dp:g} m applied to every row, so the")
        print(f"  vertex counts are what you would actually export.\n")
        print(f"  {'D(m)':>5} {'D(mm)':>6} {'pts':>4} {'verts':>6} "
              f"{'AMPUTATE m':>11} {'mm':>6} {'INTRUDE m':>10} {'mm':>6} "
              f"{'lost':>7} {'gain':>7}")
        print("  " + "-" * 88)
        for d in (0, 25, 50, 75, 100, 150, 200, 300, 400, 600):
            sm = smooth(g, d, a.chaikin, dp)
            m = metrics(g, sm, a.scale)
            if not m:
                print(f"  {d:7.0f}   collapsed")
                continue
            flag = "  <-- CLIFF" if m["amp_mm"] > 5.0 else ""
            print(f"  {d:5.0f} {d/mm:6.2f} {m['nparts']:4d} {m['nv']:6,} "
                  f"{m['amp']:11,.0f} {m['amp_mm']:6.2f} {m['intr']:10,.0f} {m['intr_mm']:6.2f} "
                  f"{m['lost_km2']:7,.3f} {m['gained_km2']:7,.3f}{flag}")
        print("\n  Then commit:  --d <value> --out <path>\n")
        if a.d is None:
            return

    sm = smooth(g, a.d, a.chaikin, a.dp)
    sm = apply_edits(sm, a.edit, mm, a.edit_radius)
    if a.edit:
        sm = sm.buffer(0)          # heal slivers left by the boolean ops
        print()
    m = metrics(g, sm, a.scale)
    print(f"  D = {a.d} m, chaikin {a.chaikin}, dp {a.dp}")
    print(f"  amputation (worst)   {m['amp']:,.1f} m = {m['amp_mm']:.2f} mm printed")
    print(f"  intrusion  (worst)   {m['intr']:,.1f} m = {m['intr_mm']:.2f} mm printed")
    print(f"  mean deviation       {m['mean']:,.1f} m = {m['mean_mm']:.2f} mm printed")
    print(f"  area                 {m['area_pct']:.2f}% of original")
    print(f"  material lost        {m['lost_km2']:,.3f} km2")
    print(f"  notches filled       {m['gained_km2']:,.3f} km2")
    print(f"  biggest single loss  {m['biggest_lost_km2']:,.3f} km2")
    print(f"  parts                {len(parts(g))} -> {m['nparts']}")
    print(f"  vertices             {nvert(g):,} -> {m['nv']:,}")
    part_report(sm, "output", mm)

    if a.dst:
        out = {"type": "FeatureCollection"}
        if crs_member:
            out["crs"] = crs_member      # before "features" -- some readers
                                         # only scan the head of the document
        out["features"] = [
            {"type": "Feature", "properties":
                {"source": os.path.basename(a.src), "d_m": a.d,
                 "chaikin": a.chaikin, "dp_m": a.dp, "scale_denom": a.scale,
                 "edits": a.edit,
                 "amputation_m": round(m["amp"], 2),
                 "intrusion_m": round(m["intr"], 2),
                 "mean_disp_m": round(m["mean"], 2)},
             "geometry": mapping(sm)}]
        with open(a.dst, "w") as f:
            json.dump(out, f)
        print(f"\n  wrote {a.dst}")

    if a.buffer_out:
        buf = sm.buffer(a.buffer_m, join_style=1)
        bout = {"type": "FeatureCollection"}
        if crs_member:
            bout["crs"] = crs_member
        bout["features"] = [{"type": "Feature",
                             "properties": {"buffer_m": a.buffer_m,
                                            "source": os.path.basename(a.src)},
                             "geometry": mapping(buf)}]
        with open(a.buffer_out, "w") as f:
            json.dump(bout, f)
        print(f"  wrote {a.buffer_out}  (+{a.buffer_m:g} m, "
              f"{buf.area/1e6:.3f} km2, for the raster cutline)")
        print("  Load it over the original in QGIS at print scale and LOOK at it.")
        print("  The metrics rank candidates; they do not pick one.\n")


if __name__ == "__main__":
    main()
