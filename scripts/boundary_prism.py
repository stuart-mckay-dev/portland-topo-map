#!/usr/bin/env python3
"""
boundary_prism.py -- Turn the smoothed city boundary into a watertight STL
prism, in model millimetres, aligned to the heightmap.

Why this exists
---------------
Masking the raster does NOT cut the model. Terrain outside the boundary
normalises to 0, so it prints as a flat apron at base-slab height out to the
rectangle's edge. To make the plastic actually stop at the city limits you
need a mesh boolean, and that needs a solid to intersect against.

Getting a DXF or SVG into Blender at the right scale and position is fiddly
and easy to get subtly wrong. This writes the prism directly, in millimetres,
positioned so it lines up with the displaced grid by construction.

Alignment
---------
The prism must land exactly where the heightmap does. Rather than assume,
it reads the georeferenced extent of the SAME raster the heightmap came from
and maps:

    model_x = (utm_x - raster_left)   / raster_w * tile_w - tile_w/2
    model_y = (utm_y - raster_bottom) / raster_h * tile_h - tile_h/2

matching the grid, which is centred on the origin and UV-mapped 0..1 across
its footprint.

Usage
-----
  python3 scripts/boundary_prism.py \\
      --boundary data/vectors/boundary_smoothed.geojson \\
      --ref-raster data/derived/dem_masked.tif \\
      --tile-w 313 --tile-h 270 \\
      --z-min -5 --z-max 60 \\
      --out data/prism.stl

Then in Blender: File > Import > STL, add a Boolean modifier to the terrain
with Operation = Intersect and Object = the prism, apply, and re-run the
3D-Print Toolbox check. Booleans are the one operation in this pipeline that
can produce non-manifold geometry.

Make z-min lower than the model's lowest point and z-max higher than its
highest, so the prism cuts cleanly through in Z and only constrains XY.
"""
from __future__ import annotations
import argparse, json, struct, sys

try:
    from shapely.geometry import shape, Polygon, MultiPolygon
    from shapely.ops import unary_union, triangulate
except ImportError:
    sys.exit("Needs shapely:  pip install shapely")
try:
    import rasterio
except ImportError:
    sys.exit("Needs rasterio:  pip install rasterio")


def load_polygon(path):
    with open(path) as f:
        gj = json.load(f)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    g = unary_union([shape(ft["geometry"]) for ft in feats if ft.get("geometry")])
    if g.geom_type == "GeometryCollection":
        g = unary_union([p for p in g.geoms
                         if p.geom_type in ("Polygon", "MultiPolygon")])
    return g


def parts(g):
    return [g] if g.geom_type == "Polygon" else list(g.geoms)


def cap_triangles(poly):
    """Triangulate a polygon face so the caps are watertight.

    shapely's plain triangulate() is an UNCONSTRAINED Delaunay over the
    vertices: it spans concave bays and holes, and filtering by
    centroid-inside leaves slivers unaccounted for along a boundary as
    convoluted as this one. Measured on the pilot outline that approach left
    16 non-manifold edges -- enough to make a boolean unpredictable.

    shapely >= 2.1 exposes a genuine constrained Delaunay, which respects the
    boundary and holes exactly. Use it when present; fall back to the filter
    otherwise and say so, because the fallback needs checking.
    """
    import shapely as _sh
    if hasattr(_sh, "constrained_delaunay_triangles"):
        res = _sh.constrained_delaunay_triangles(poly)
        return [list(t.exterior.coords)[:3] for t in res.geoms]

    print("    [!] shapely < 2.1: falling back to filtered unconstrained "
          "Delaunay.\n        Watch the non-manifold count below.")
    return [list(t.exterior.coords)[:3] for t in triangulate(poly)
            if poly.contains(t.centroid)]


def build(poly_mm, z0, z1):
    tris = []
    for p in parts(poly_mm):
        caps = cap_triangles(p)
        for (a, b, c) in caps:
            tris.append(((a[0], a[1], z1), (b[0], b[1], z1), (c[0], c[1], z1)))
            tris.append(((c[0], c[1], z0), (b[0], b[1], z0), (a[0], a[1], z0)))
        rings = [p.exterior] + list(p.interiors)
        for ring in rings:
            co = list(ring.coords)
            for i in range(len(co) - 1):
                x0, y0 = co[i]; x1_, y1_ = co[i + 1]
                tris.append(((x0, y0, z0), (x1_, y1_, z0), (x1_, y1_, z1)))
                tris.append(((x0, y0, z0), (x1_, y1_, z1), (x0, y0, z1)))
    return tris


def edge_manifold_report(tris):
    """Every edge of a closed surface must be used exactly twice."""
    from collections import Counter
    edges = Counter()
    for t in tris:
        for i in range(3):
            a, b = t[i], t[(i + 1) % 3]
            edges[tuple(sorted((a, b)))] += 1
    bad = {k: v for k, v in edges.items() if v != 2}
    return len(edges), len(bad)


def build_ngon(poly_mm, z0, z1):
    """Build the prism with N-GON caps instead of triangles.

    Triangulating a 900-vertex concave outline in Python needs shapely 2.1's
    constrained Delaunay, which needs Python 3.10+. Blender does not need us to
    do it at all: OBJ carries n-gons, and Blender triangulates them itself with
    a correct C implementation -- then its boolean triangulates internally
    anyway. So the cap is emitted as a single face per ring and the whole
    dependency disappears.

    Returns (verts, faces) with 1-based OBJ indices.
    """
    from shapely.geometry.polygon import orient
    verts, faces = [], []
    for p in parts(poly_mm):
        # FORCE counter-clockwise exterior rings. Shapely does not guarantee
        # winding, and the winding decides the face normals. A prism wound
        # inward renders perfectly (Blender draws backfaces) but booleans as
        # the COMPLEMENT of itself, so Intersect returns an empty mesh with no
        # error. This is the single most important line in the file.
        p = orient(p, sign=1.0)
        if list(p.interiors):
            sys.exit("  [X] This polygon has interior rings (holes). The OBJ\n"
                     "      n-gon path cannot represent them. Dissolve holes in\n"
                     "      smooth_boundary.py, or write an .stl with shapely 2.1.")
        ring = list(p.exterior.coords)
        if ring[0] == ring[-1]:
            ring = ring[:-1]
        n = len(ring)
        base = len(verts)
        for (x, y) in ring:
            verts.append((x, y, z0))
        for (x, y) in ring:
            verts.append((x, y, z1))
        bot = [base + i + 1 for i in range(n)]
        top = [base + n + i + 1 for i in range(n)]
        faces.append(list(reversed(bot)))          # outward normal, downward
        faces.append(top)
        for i in range(n):
            j = (i + 1) % n
            faces.append([bot[i], bot[j], top[j], top[i]])
    return verts, faces


def signed_volume(verts, faces):
    """Signed volume via the divergence theorem, fan-triangulating each face.

    Positive means outward-facing normals -- a real solid. Negative means the
    surface is inside-out, which is invisible on screen and fatal to a boolean.
    """
    total = 0.0
    for f in faces:
        a = verts[f[0] - 1]
        for i in range(1, len(f) - 1):
            b = verts[f[i] - 1]
            c = verts[f[i + 1] - 1]
            total += (a[0] * (b[1] * c[2] - b[2] * c[1])
                      - a[1] * (b[0] * c[2] - b[2] * c[0])
                      + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return total


def edge_report_faces(faces):
    from collections import Counter
    edges = Counter()
    for f in faces:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            edges[tuple(sorted((a, b)))] += 1
    return len(edges), sum(1 for v in edges.values() if v != 2)


def write_obj(path, verts, faces, name="prism"):
    with open(path, "w") as f:
        f.write(f"# {name} -- millimetres, n-gon caps\n")
        for (x, y, z) in verts:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        f.write(f"o {name}\n")
        for face in faces:
            f.write("f " + " ".join(str(i) for i in face) + "\n")


def write_stl(path, tris, name=b"prism"):
    with open(path, "wb") as f:
        f.write(name.ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for (a, b, c) in tris:
            ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
            vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
            nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
            m = (nx*nx + ny*ny + nz*nz) ** 0.5 or 1.0
            f.write(struct.pack("<12fH", nx/m, ny/m, nz/m,
                                *a, *b, *c, 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boundary", required=True)
    ap.add_argument("--ref-raster", required=True,
                    help="the raster the heightmap was cut from; its extent "
                         "defines the alignment")
    ap.add_argument("--tile-w", type=float, required=True)
    ap.add_argument("--tile-h", type=float, required=True)
    ap.add_argument("--z-min", type=float, default=-5.0)
    ap.add_argument("--z-max", type=float, default=60.0)
    ap.add_argument("--bounds", nargs=4, type=float, metavar=("XMIN","YMIN","XMAX","YMAX"),
                    help="grid THIS ground extent instead of the raster's. "
                         "Must match qgis_export_tiles.py --bounds exactly, or "
                         "the prisms will not line up with the heightmaps.")
    ap.add_argument("--cols", type=int, default=1,
                    help="tile grid columns; >1 writes one prism per tile, "
                         "each in ITS OWN local coordinates")
    ap.add_argument("--rows", type=int, default=1)
    ap.add_argument("--force", action="store_true",
                    help="write the STL even if it is not watertight")
    ap.add_argument("--phase", default="pilot",
                    help="naming for multi-tile output: pdx_<phase>_rNNcNN")
    ap.add_argument("--out", required=True,
                    help="output file; .obj writes n-gon caps and needs no "
                         "Python-side triangulation (recommended), .stl needs "
                         "shapely 2.1. With --cols/--rows >1 this is a "
                         "DIRECTORY and the extension is set by --format.")
    ap.add_argument("--format", default="obj", choices=["obj", "stl"],
                    help="output format for multi-tile runs (default obj)")
    a = ap.parse_args()

    poly = load_polygon(a.boundary)
    with rasterio.open(a.ref_raster) as src:
        left, bottom, right, top = src.bounds
        if a.bounds:
            left, bottom, right, top = a.bounds
            print(f"  grid extent OVERRIDDEN to {right-left:,.0f} x "
                  f"{top-bottom:,.0f} m")
        rw, rh = right - left, top - bottom
        print(f"  reference raster  {a.ref_raster}")
        print(f"    extent {rw:,.0f} x {rh:,.0f} m   CRS {src.crs}")

    # With a tile grid, each tile covers 1/cols of the raster width and
    # 1/rows of its height, and the model footprint given is ONE tile.
    grw, grh = rw / a.cols, rh / a.rows
    sx, sy = a.tile_w / grw, a.tile_h / grh
    print(f"  model footprint   {a.tile_w} x {a.tile_h} mm")
    print(f"    scale  1 m of ground = {sx:.6f} mm in X, {sy:.6f} mm in Y")
    if abs(sx - sy) / max(sx, sy) > 0.01:
        print(f"    [!] X and Y scales differ by "
              f"{100*abs(sx-sy)/max(sx,sy):.2f}% -- the model is stretched. "
              f"Check tile-w/tile-h against the raster aspect.")

    from shapely.ops import transform as shp_transform
    from shapely.geometry import box as shp_box
    import os

    if a.cols == 1 and a.rows == 1:
        jobs = [(None, left, bottom, a.out)]
    else:
        os.makedirs(a.out, exist_ok=True)
        jobs = []
        for r in range(a.rows):
            for c in range(a.cols):
                # row 1 is the NORTH edge, matching qgis_export_tiles.py
                tl = left + c * grw
                tb = top - (r + 1) * grh
                name = f"pdx_{a.phase}_r{r+1:02d}c{c+1:02d}_prism.{a.format}"
                jobs.append(((r, c, tl, tb), tl, tb, os.path.join(a.out, name)))
        print(f"  tiling            {a.cols} x {a.rows} = {len(jobs)} prisms")
        print(f"    ground per tile {grw:,.0f} x {grh:,.0f} m\n")

    empty = 0
    for job, ox, oy, outpath in jobs:
        clipped = poly
        if job is not None:
            r, c, tl, tb = job
            clipped = poly.intersection(shp_box(tl, tb, tl + grw, tb + grh))
            if clipped.is_empty or clipped.area <= 0:
                print(f"  {os.path.basename(outpath):34s} EMPTY -- no city in "
                      f"this tile, nothing to cut")
                empty += 1
                continue

        def to_mm(x, y, z=None, _ox=ox, _oy=oy):
            return ((x - _ox) * sx - a.tile_w / 2.0,
                    (y - _oy) * sy - a.tile_h / 2.0)

        poly_mm = shp_transform(to_mm, clipped)
        use_obj = outpath.lower().endswith(".obj")
        if use_obj:
            verts, faces = build_ngon(poly_mm, a.z_min, a.z_max)
            nedges, nbad = edge_report_faces(faces)
            ncount = len(faces)
            vol = signed_volume(verts, faces)
            expected = clipped.area * (a.z_max - a.z_min) * sx * sy
            print(f"    signed volume {vol:+,.1f} mm3 "
                  f"(expected about {expected:+,.1f})")
            if vol <= 0:
                sys.exit("\n  [X] NEGATIVE signed volume: this prism is "
                         "inside-out.\n      It will render fine and boolean to "
                         "nothing. Ring winding is wrong.\n")
        else:
            tris = build(poly_mm, a.z_min, a.z_max)
            nedges, nbad = edge_manifold_report(tris)
            ncount = len(tris)
        x0, y0, x1, y1 = poly_mm.bounds
        tag = "watertight" if nbad == 0 else f"[!] {nbad} NON-MANIFOLD"
        if job is None:
            print(f"  prism XY bounds   {x0:.2f} .. {x1:.2f} mm  x  "
                  f"{y0:.2f} .. {y1:.2f} mm")
            print(f"  prism Z           {a.z_min} .. {a.z_max} mm")
            print(f"  {'faces' if use_obj else 'triangles':17s} {ncount:,}")
            print(f"  edges             {nedges:,}, non-manifold {nbad}")
            print(f"    {tag}")
        else:
            print(f"  {os.path.basename(outpath):34s} {ncount:6,} faces "
                  f"{100*clipped.area/(grw*grh):5.1f}% of tile  {tag}")
        if nbad and not a.force:
            sys.exit(
                f"\n  [X] REFUSING to write a non-manifold prism.\n"
                f"      {nbad} edges are not shared by exactly two faces.\n"
                f"      A leaky cutter makes Blender's boolean emit GARBAGE\n"
                f"      rather than fail, so this would not announce itself.\n\n"
                f"      Almost always the cause is shapely < 2.1 -- see the\n"
                f"      fallback warning above. Two fixes, easiest first:\n\n"
                f"        1. Write an OBJ instead of an STL. Just change the\n"
                f"           --out extension to .obj. Blender reads n-gons and\n"
                f"           triangulates them itself, so no Python-side\n"
                f"           triangulation happens and shapely 2.1 is not\n"
                f"           needed at all.\n"
                f"        2. pip install --upgrade 'shapely>=2.1'\n"
                f"           (needs Python 3.10+; the stock macOS/Xcode\n"
                f"           Python is 3.9, so this means a new venv.)\n\n"
                f"      Override with --force only if you know why.\n")
        if use_obj:
            write_obj(outpath, verts, faces)
        else:
            write_stl(outpath, tris)

    if empty:
        print(f"\n  {empty} tile(s) contain no city at all. Those tiles have "
              f"nothing to print --\n  check them against the grid before "
              f"slicing (run-sheet 8f).")
    print(f"\n  wrote {a.out}")
    kind = "Wavefront (.obj)" if str(a.out).lower().endswith(".obj") or a.format == "obj" else "STL"
    print(f"  Blender: File > Import > {kind}, then a Boolean modifier on the")
    print("  terrain, Operation Intersect, Object = the prism. Apply, then")
    print("  re-run 3D-Print Toolbox > Check All on every tile.\n")


if __name__ == "__main__":
    main()
