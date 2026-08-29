#!/usr/bin/env python3
"""
blender_heightmap_to_mesh.py -- Convert 16-bit heightmap tiles into printable
STLs, in Blender, headless.

Run:
  blender -b -P scripts/blender_heightmap_to_mesh.py -- \
      --heightmaps data/heightmaps --pattern "pdx_pilot_*.png" \
      --out data/tiles \
      --tile-w 78.46 --tile-h 90.0 \
      --relief-mm 8.0 \
      --subdiv 470 \
      --prism-dir data/prisms/

  # --base-mm is intentionally omitted above: it defaults to BASE_MM in
  # scripts/topo_params.py (4.0 mm as of 2026-08-24). Pass it only to
  # override the project constant for a one-off test.

  # with engraved roads:
  blender -b -P scripts/blender_heightmap_to_mesh.py -- \
      ... --road-mask data/derived/mask_roads.tif --engrave-mm 0.35

  # custom, non-uniform tile footprints (from scripts/custom_tiles.py):
  blender -b -P scripts/blender_heightmap_to_mesh.py -- \
      --heightmaps data/heightmaps_custom --pattern "*.png" \
      --prism-dir data/prisms_custom \
      --sizes-csv data/heightmaps_custom/tile_sizes.csv \
      --tile-w 90 --tile-h 90 --relief-mm 8.0 --out data/tiles_custom
  # --tile-w/--tile-h above are only the fallback for a heightmap missing
  # from the CSV -- every tile listed in it uses its own size.

CRITICAL: --relief-mm is the FULL-RANGE relief for the whole project
(true_relief_mm x exaggeration), NOT this tile's own height. Because the
heightmaps were normalised project-wide, the same value is correct for every
tile and the terrain lines up across seams. Get it from:

    python3 scripts/topo_params.py plan --tile-mm 90 --cols 4 --rows 3 \
        --target-height-mm 40
"""

import os
import sys
import glob
import csv

# topo_params.py is the single source of truth for every dimensional number in
# this project. Import it rather than keeping a second copy of
# the base slab here -- duplicated constants drift, and a tile printed with the
# wrong base is only discoverable after it is on the plate.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from topo_params import BASE_MM as _BASE_MM
    _BASE_SRC = "topo_params.py"
except Exception:
    _BASE_MM = 4.0
    _BASE_SRC = "fallback (could not import topo_params.py)"

try:
    import bpy
    import bmesh
    import mathutils
except ImportError:
    sys.exit("Run this inside Blender:  blender -b -P this_script.py -- <args>")


def argv_after_ddash():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def parse():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--heightmaps", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--tile-w", type=float, required=True, help="mm")
    p.add_argument("--tile-h", type=float, required=True, help="mm")
    p.add_argument("--relief-mm", type=float, required=True,
                   help="FULL project elevation range in mm at chosen exaggeration")
    p.add_argument("--base-mm", type=float, default=_BASE_MM,
                   help=f"base slab in mm; defaults to BASE_MM in "
                        f"topo_params.py (currently {_BASE_MM:g})")
    p.add_argument("--subdiv", type=int, default=400,
                   help="grid subdivisions per side; ~4-6 per printed mm")
    p.add_argument("--road-mask", default=None)
    p.add_argument("--engrave-mm", type=float, default=0.35)
    p.add_argument("--decimate-angle", type=float, default=0.0,
                   help="planar decimate angle in degrees; 0 disables")
    p.add_argument("--pattern", default="*.tif")
    p.add_argument("--preview", metavar="BLENDFILE",
                   help="build ONE live scene and save it here instead of "
                        "exporting STLs. The Displace modifier is left "
                        "UNAPPLIED so Strength can be scrubbed to choose the "
                        "exaggeration, and no base or boolean is added.")
    p.add_argument("--plinth-mm", type=float, default=0.0,
                   help="thickness of a full-rectangle tray under every tile, "
                        "extending past the boundary cut. Keeps each tile a "
                        "printable rectangle, stops thin slivers tipping, and "
                        "gives adjacent tiles a full-length edge to butt "
                        "against. 0 disables.")
    p.add_argument("--prism", default=None,
                   help="OBJ/STL cutter from boundary_prism.py. Imported and "
                        "applied as Boolean>Intersect so the model stops at the "
                        "city limits instead of running out to the rectangle.")
    p.add_argument("--prism-dir", default=None,
                   help="directory of per-tile prisms named "
                        "<tilename>_prism.obj (or .stl), for multi-tile runs")
    p.add_argument("--true-relief-mm", type=float, default=None,
                   help="1x relief for this configuration, so preview mode can "
                        "print the Strength <-> exaggeration conversion. "
                        "3.91 for the pilot 4x3 @ 90mm.")
    p.add_argument("--sizes-csv", default=None,
                   help="CSV with columns name,tile_w_mm,tile_h_mm (name = "
                        "heightmap filename stem, no extension) -- written by "
                        "scripts/custom_tiles.py. Overrides --tile-w/--tile-h "
                        "PER TILE, for a batch of custom tiles that are not "
                        "all the same footprint the way a grid is. A tile in "
                        "--heightmaps but NOT listed here falls back to the "
                        "global --tile-w/--tile-h and prints a warning -- "
                        "silent fallback would size that one tile wrong with "
                        "no error, the same failure mode as every other bug "
                        "in this pipeline.")
    return p.parse_args(argv_after_ddash())


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"
    scn.unit_settings.scale_length = 0.001
    scn.unit_settings.length_unit = "MILLIMETERS"


def _set(obj, attr, value, critical=False):
    """Set a bpy property only if this Blender build still has it.

    The texture API has been trimmed across versions -- 5.2 removed
    ImageTexture.filter_type, for example. None of the optional ones change
    what a Displace modifier does with a heightmap, so a missing attribute is
    not worth crashing a 27-hour pipeline over. The ones that DO matter are
    marked critical and will complain loudly.
    """
    if hasattr(obj, attr):
        setattr(obj, attr, value)
        return True
    msg = f"  [!] this Blender has no {type(obj).__name__}.{attr}"
    if critical:
        print(msg + "  -- CHECK THE RESULT, this one matters")
    return False


def load_tex(name, path, interp="Linear"):
    # ABSOLUTE path, always. A relative path gets stored in the .blend as
    # relative-to-the-blend-file, so a preview.blend written into data/ ends up
    # looking for data/data/heightmaps/... on reopen. The image then comes back
    # missing, Displace samples nothing, and the mesh is flat in the GUI while
    # the headless run that created it measured correct displacement.
    path = os.path.abspath(path)
    img = bpy.data.images.load(path, check_existing=True)

    # bpy.data.images.load() does NOT raise on a format Blender cannot decode.
    # It hands back a 0 x 0 placeholder, Displace then moves nothing, and you
    # get a perfectly flat plane that looks like "not enough exaggeration"
    # rather than "the heightmap never loaded". Fail loudly instead.
    if img.size[0] == 0 or img.size[1] == 0:
        sys.exit(
            f"\n  [X] Blender loaded {os.path.basename(path)} as a 0 x 0 image.\n"
            f"      It cannot decode this file, so displacement would be ZERO\n"
            f"      and the result would be a flat sheet.\n\n"
            f"      Most likely cause: a single-band 16-bit DEFLATE-compressed\n"
            f"      GeoTIFF. Blender's TIFF support does not cover it.\n\n"
            f"      Fix -- re-export the heightmaps as 16-bit PNG:\n"
            f"        python3 scripts/qgis_export_tiles.py ... --png\n"
            f"      or convert what you have:\n"
            f"        gdal_translate -of PNG -ot UInt16 in.tif out.png\n"
            f"      then point --pattern at '*.png'.\n")
    bits_per_ch = img.depth // max(img.channels, 1)
    # COLOUR SPACE. Blender treats an image texture as sRGB by default and
    # applies the sRGB->linear transfer function on read. On a heightmap that
    # is catastrophic and silent: it is a non-linear curve, so it crushes low
    # elevations far more than high ones. Measured on this project, a tile
    # whose heightmap held 0.875 mm of relief displaced by 0.106 mm -- exactly
    # sRGB_to_linear(0.1347) * 6.5. Tiles near full range were barely touched,
    # so the error hid as "some tiles look flat" rather than as a wrong value.
    # Elevation is DATA, not colour.
    try:
        img.colorspace_settings.name = "Non-Color"
        print(f"  [{name}] colour space set to Non-Color")
    except Exception as e:
        print(f"  [!] could not set colour space to Non-Color: {e}")
        print(f"      Elevations will be gamma-crushed. Do not print this.")

    print(f"  [{name}] texture {img.size[0]} x {img.size[1]} px, "
          f"{img.depth}-bit total / {img.channels} ch = {bits_per_ch} bits per "
          f"channel, float={img.is_float}")

    # A 16-bit source is not much use if Blender loaded it into an 8-bit
    # buffer. 8 bits across a 362 m range is 1.4 m per level, which terraces
    # visibly on flat ground -- and Portland is mostly flat ground. Count the
    # distinct levels actually present rather than trusting the header.
    if not img.is_float and bits_per_ch <= 8:
        try:
            import numpy as np
            buf = np.empty(len(img.pixels), dtype=np.float32)
            img.pixels.foreach_get(buf)
            levels = np.unique(np.round(buf[0::img.channels] * 65535.0)
                               .astype(np.uint16)).size
            del buf
            print(f"  [{name}] distinct elevation levels actually present: "
                  f"{levels:,}")
            if levels <= 300:
                print(f"  [!] Blender DOWNCONVERTED this heightmap to 8-bit.")
                print(f"      {levels:,} levels over 361.81 m is "
                      f"{361.81 / max(levels, 1):.2f} m per step -- visible")
                print(f"      terracing on the flats. The PNG on disk is fine;")
                print(f"      Blender's loader is the problem. Set the image's")
                print(f"      colour space to Non-Color and re-check, or feed")
                print(f"      displacement from a float EXR instead.")
        except Exception as e:
            print(f"  [{name}] precision check skipped: {e}")

    tex = bpy.data.textures.new(name, type="IMAGE")
    tex.image = img
    # EXTEND, not REPEAT: REPEAT wraps terrain across the tile seam, which is
    # the one failure mode that ruins a whole grid rather than one tile.
    _set(tex, "extension", "EXTEND", critical=True)
    # Interpolate between texels, or a 16-bit heightmap prints as stair-steps
    # at the texel grid rather than the layer height.
    _set(tex, "use_interpolation", True, critical=True)
    # Cosmetic filtering knobs; absent on newer builds, and irrelevant to
    # displacement. Set them if they exist, shrug if not.
    _set(tex, "filter_type", "BOX")
    return tex


def import_cutter(path):
    """Import a prism and return the object, whatever the format."""
    before = set(bpy.data.objects)
    low = path.lower()

    # AXES MATTER. Blender's OBJ importer defaults to a Y-up source and rotates
    # -90 about X on the way in. boundary_prism.py already writes Blender's own
    # Z-up millimetres, so that conversion stands the city outline on its edge:
    # the prism's Z extent lands in Y and vice versa, and the boolean then
    # intersects two solids that barely meet and returns an EMPTY mesh.
    # forward=Y / up=Z is the identity.
    axes = {"forward_axis": "Y", "up_axis": "Z"}
    try:
        if low.endswith(".obj"):
            bpy.ops.wm.obj_import(filepath=path, **axes)
        else:
            bpy.ops.wm.stl_import(filepath=path, **axes)
    except TypeError:                            # build without axis args
        if low.endswith(".obj"):
            bpy.ops.wm.obj_import(filepath=path)
        else:
            bpy.ops.wm.stl_import(filepath=path)
    except AttributeError:                       # older operator names
        if low.endswith(".obj"):
            bpy.ops.import_scene.obj(filepath=path, axis_forward="Y", axis_up="Z")
        else:
            bpy.ops.import_mesh.stl(filepath=path)
    new = list(set(bpy.data.objects) - before)
    if not new:
        sys.exit(f"  [X] nothing imported from {path}")
    cutter = new[0]
    cutter.name = "prism_cutter"
    ngons = sum(1 for f in cutter.data.polygons if len(f.vertices) > 4)
    biggest = max((len(f.vertices) for f in cutter.data.polygons), default=0)
    print(f"  cutter imported: {len(cutter.data.polygons):,} faces from "
          f"{os.path.basename(path)}  ({ngons} n-gons, largest {biggest} verts)")

    # Blender's Exact boolean is fragile against a single huge concave n-gon --
    # a 900-vertex cap is exactly that case, and it fails by returning an EMPTY
    # result rather than erroring. Triangulate with Blender's own robust code
    # before the boolean ever sees it.
    if biggest > 4:
        bm = bmesh.new()
        bm.from_mesh(cutter.data)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.to_mesh(cutter.data)
        bm.free()
        print(f"  cutter triangulated -> {len(cutter.data.polygons):,} tris")

    bb = [cutter.matrix_world @ mathutils.Vector(c) for c in cutter.bound_box]
    xs = [v.x for v in bb]; ys = [v.y for v in bb]; zs = [v.z for v in bb]
    print(f"  cutter bounds:   X {min(xs):8.2f} .. {max(xs):8.2f}   "
          f"Y {min(ys):8.2f} .. {max(ys):8.2f}   Z {min(zs):7.2f} .. {max(zs):7.2f}")
    return cutter


def verify_cutter(cutter, obj_lo, obj_hi):
    """The cutter must bracket the model in Z, or it is not cutting in XY only.

    This is the check that catches an axis-convention mix-up on import, which
    otherwise shows up as an empty boolean with no explanation.
    """
    bb = [cutter.matrix_world @ mathutils.Vector(c) for c in cutter.bound_box]
    zlo, zhi = min(v.z for v in bb), max(v.z for v in bb)
    if zlo > obj_lo or zhi < obj_hi:
        sys.exit(
            f"\n  [X] The cutter does not bracket the model in Z.\n"
            f"      model  Z {obj_lo:8.2f} .. {obj_hi:8.2f}\n"
            f"      cutter Z {zlo:8.2f} .. {zhi:8.2f}\n\n"
            f"      A prism is meant to constrain XY only and pass clean\n"
            f"      through in Z. If the cutter's Z looks like its Y, the\n"
            f"      importer applied a Y-up to Z-up rotation -- see the axis\n"
            f"      arguments in import_cutter().\n"
            f"      Otherwise widen --z-min/--z-max in boundary_prism.py.\n")


def apply_cut(obj, cutter, preview, thickness):
    """Boolean-intersect obj with cutter.

    CRITICAL: Boolean Intersect requires BOTH operands to be closed solids.
    In preview mode the terrain is a single displaced sheet with no thickness
    -- it is deliberately not solidified so Strength stays scrubbable -- and
    intersecting an open surface with a solid does not error. Blender keeps the
    cutter's walls and discards the sheet, giving a box with no lid. So give
    the sheet thickness first.
    """
    if preview:
        # The solidified body must stay INSIDE the cutter's Z range, or the
        # boolean shaves its underside off. The preview's thickness is
        # cosmetic -- it only exists so Intersect has a solid -- so clamp it to
        # fit rather than demanding a taller prism.
        cbb = [cutter.matrix_world @ mathutils.Vector(c) for c in cutter.bound_box]
        czlo = min(v.z for v in cbb)
        _, mlo, mhi = evaluated_stats(obj)
        room = (mlo - czlo) * 0.95
        if room <= 0:
            sys.exit(f"\n  [X] The cutter's floor (Z {czlo:.2f}) is above the "
                     f"model's (Z {mlo:.2f}).\n      Regenerate the prism with a "
                     f"lower --z-min.\n")
        used = min(thickness, room)
        if used < thickness:
            print(f"  solidify clamped {thickness:.1f} -> {used:.1f} mm to stay "
                  f"inside the cutter (floor Z {czlo:.1f})")
        sol = obj.modifiers.new("solidify", "SOLIDIFY")
        sol.thickness = used
        sol.offset = -1.0                     # grow downward, keep the top surface
        print(f"  solidify {used:.1f} mm downward "
              f"(preview sheet has no thickness; Intersect needs a solid)")
        nv, lo, hi = evaluated_stats(obj)
        print(f"  after solidify:  {nv:,} verts, Z {lo:.2f} .. {hi:.2f} mm")

    nv0, zlo0, zhi0 = evaluated_stats(obj)
    verify_cutter(cutter, zlo0, zhi0)

    b = obj.modifiers.new("boundary", "BOOLEAN")
    b.operation = "INTERSECT"
    b.object = cutter
    if hasattr(b, "solver"):
        b.solver = "EXACT"
    ob = [mathutils.Vector(c) for c in obj.bound_box]
    print(f"  terrain bounds:  X {min(v.x for v in ob):8.2f} .. "
          f"{max(v.x for v in ob):8.2f}   Y {min(v.y for v in ob):8.2f} .. "
          f"{max(v.y for v in ob):8.2f}")
    # hide_set() is the eye icon: hidden from view but STILL EVALUATED.
    # hide_viewport (the monitor icon) disables the object in the depsgraph,
    # which can leave the Boolean with no operand and yield an empty mesh.
    cutter.hide_set(True)
    cutter.hide_render = True
    return b


def mesh_health(obj, label):
    """Vertex/face counts, non-manifold edges and signed volume in one line.

    Every silent failure in this pipeline was invisible in a settings panel and
    obvious in these four numbers.
    """
    me = obj.data
    bm = bmesh.new(); bm.from_mesh(me)
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    vol = bm.calc_volume(signed=True)
    bm.free()
    print(f"    {label:26s} {len(me.vertices):8,} v  {len(me.polygons):8,} f  "
          f"non-manifold {nonman:5d}  volume {vol:+12,.1f} mm3")
    return len(me.vertices), nonman, vol


def add_plinth(obj, tile_w, tile_h, height):
    """Union a full-rectangle tray under the tile.

    After the boundary boolean a tile can be a thin sliver of city with a tiny
    footprint -- unstable on the bed, fragile to handle, and with no straight
    edge to register against its neighbour. A shallow tray restores the
    rectangle without hiding the silhouette: the city still stands proud of it
    by base_mm + relief.
    """
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    pl = bpy.context.active_object
    pl.name = "plinth"
    pl.scale = (tile_w, tile_h, height)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    pl.location.z = height / 2.0
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

    b = obj.modifiers.new("plinth", "BOOLEAN")
    b.operation = "UNION"
    b.object = pl
    if hasattr(b, "solver"):
        b.solver = "EXACT"
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=b.name)
    bpy.data.objects.remove(pl, do_unlink=True)


def build_uvs(obj):
    """Write UVs explicitly instead of trusting the primitive to make them.

    Displace with Coordinates=UV samples nothing when the mesh has no UV
    layer -- it does not error, it just moves every vertex by zero and hands
    you a flat sheet. Generating them here also guarantees the mapping is
    exactly footprint -> 0..1, which is what makes the same heightmap line up
    across tile seams.
    """
    import numpy as np
    me = obj.data
    uvl = me.uv_layers[0] if me.uv_layers else me.uv_layers.new(name="UVMap")

    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    minx, miny = float(co[:, 0].min()), float(co[:, 1].min())
    w = float(co[:, 0].max()) - minx
    h = float(co[:, 1].max()) - miny
    if w <= 0 or h <= 0:
        sys.exit("  [X] degenerate grid: zero width or height")

    li = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", li)
    uvs = np.empty((len(me.loops), 2), dtype=np.float32)
    uvs[:, 0] = (co[li, 0] - minx) / w
    uvs[:, 1] = (co[li, 1] - miny) / h
    uvl.data.foreach_set("uv", uvs.ravel())
    print(f"  [{obj.name}] UVs written: {len(me.loops):,} loops -> '{uvl.name}'")
    return uvl.name


def evaluated_stats(obj):
    """Vertex count and Z range WITH modifiers applied. Zero verts means the
    modifier stack destroyed the mesh -- which looks identical to a hidden
    object in the viewport."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    n = len(me.vertices)
    if n == 0:
        ev.to_mesh_clear()
        return 0, 0.0, 0.0
    import numpy as np
    co = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    z = co.reshape(-1, 3)[:, 2]
    lo, hi = float(z.min()), float(z.max())
    ev.to_mesh_clear()
    return n, lo, hi


def evaluated_z_range(obj):
    """What the mesh actually looks like WITH modifiers applied."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    import numpy as np
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    z = co.reshape(-1, 3)[:, 2]
    lo, hi = float(z.min()), float(z.max())
    ev.to_mesh_clear()
    return lo, hi


def build_tile(hm_path, args):
    name = os.path.splitext(os.path.basename(hm_path))[0]
    print(f"  [{name}] building...")

    # Keep the quads square: subdivide each axis in proportion to its length,
    # rather than giving a 313 x 270 mm sheet the same count both ways.
    longest = max(args.tile_w, args.tile_h)
    xs = max(4, int(round(args.subdiv * args.tile_w / longest)))
    ys = max(4, int(round(args.subdiv * args.tile_h / longest)))
    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=xs,
        y_subdivisions=ys,
        size=1.0,
        location=(0, 0, 0),
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (args.tile_w, args.tile_h, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    build_uvs(obj)

    # --- terrain displacement -------------------------------------------
    d = obj.modifiers.new("terrain", "DISPLACE")
    d.texture = load_tex(f"{name}_hm", hm_path)
    d.texture_coords = "UV"
    d.direction = "Z"
    d.mid_level = 0.0                 # 0 -> displacement runs upward from 0
    d.strength = args.relief_mm
    d.uv_layer = obj.data.uv_layers[0].name

    # Verify the displacement actually moved something. Two separate silent
    # failures have produced a flat sheet here: an undecodable image, and a
    # missing UV layer. Neither raised. Measure the result instead of trusting
    # that the modifier was configured correctly.
    lo, hi = evaluated_z_range(obj)
    print(f"  [{name}] evaluated Z range {lo:.3f} -> {hi:.3f} mm "
          f"(span {hi - lo:.3f} mm)")

    # Cross-check the displaced height against what the heightmap actually
    # contains. This is the check that catches colour management, wrong
    # normalisation, and any future misreading of the texture -- none of which
    # announce themselves.
    try:
        import numpy as _np
        _img = d.texture.image
        _buf = _np.empty(len(_img.pixels), dtype=_np.float32)
        _img.pixels.foreach_get(_buf)
        _peak = float(_buf[0::_img.channels].max())
        del _buf
        _expect = _peak * args.relief_mm
        _err = abs((hi - lo) - _expect)
        print(f"  [{name}] heightmap peak {_peak:.5f} -> expected relief "
              f"{_expect:.3f} mm")
        if _expect > 0.01 and _err / _expect > 0.05:
            sys.exit(
                f"\n  [X] Displaced relief disagrees with the heightmap.\n"
                f"      expected {_expect:.3f} mm from the image, got "
                f"{hi - lo:.3f} mm\n"
                f"      ({100*_err/_expect:.1f}% off)\n\n"
                f"      The usual cause is COLOUR SPACE: an image read as sRGB\n"
                f"      gets a non-linear curve applied, which crushes low\n"
                f"      elevations far more than high ones. The texture must be\n"
                f"      Non-Color. Check the line above this one.\n")
    except SystemExit:
        raise
    except Exception as _e:
        print(f"  [{name}] relief cross-check skipped: {_e}")
    if hi - lo < 0.001 * args.relief_mm:
        sys.exit(
            f"\n  [X] Displacement did NOTHING -- the mesh is flat.\n"
            f"      Strength is {args.relief_mm} mm but the evaluated Z span is\n"
            f"      {hi - lo:.6f} mm. The modifier is configured but sampling\n"
            f"      nothing. Check the UV layer and the texture image.\n")

    if args.preview and not args.prism:
        # No cut requested: leave Displace live so Strength stays scrubbable.
        print(f"  [{name}] Displace left LIVE at strength {args.relief_mm} mm")
        return obj

    # From here the mesh becomes a real closed solid. That is REQUIRED before
    # any Boolean: Solidify cannot do it here, because the masked heightmap has
    # a near-vertical cliff at the city boundary and offsetting along the
    # normals across a vertical wall makes the surface pass through itself.
    # Blender's Exact solver rejects self-intersecting input by returning an
    # empty mesh -- with zero non-manifold edges and a correct signed volume,
    # so nothing else flags it. Extruding the boundary loop straight down to
    # Z=0 and capping cannot self-intersect.
    if args.preview:
        bpy.ops.object.modifier_apply(modifier=d.name)
    bpy.ops.object.modifier_apply(modifier=d.name)

    # --- optional road engraving ----------------------------------------
    if args.road_mask and os.path.exists(args.road_mask):
        e = obj.modifiers.new("engrave", "DISPLACE")
        e.texture = load_tex(f"{name}_roads", args.road_mask)
        e.texture_coords = "UV"
        e.direction = "Z"
        e.mid_level = 1.0             # white -> -strength, black -> 0
        e.strength = args.engrave_mm
        bpy.ops.object.modifier_apply(modifier=e.name)

    # --- lift onto the base slab ----------------------------------------
    obj.location.z = args.base_mm
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

    # --- close the solid: extrude the boundary down to Z=0 and cap -------
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)

    boundary = [e for e in bm.edges if e.is_boundary]
    ret = bmesh.ops.extrude_edge_only(bm, edges=boundary)
    new_verts = [v for v in ret["geom"] if isinstance(v, bmesh.types.BMVert)]
    for v in new_verts:
        v.co.z = 0.0

    bottom_edges = [e for e in bm.edges
                    if e.verts[0].co.z == 0.0 and e.verts[1].co.z == 0.0]
    bmesh.ops.holes_fill(bm, edges=bottom_edges)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()

    # Tiles are already closed solids by this point, so no solidify needed.
    cutter_path = None
    if args.prism_dir:
        for ext in (".obj", ".stl"):
            cand = os.path.join(args.prism_dir, name + "_prism" + ext)
            if os.path.exists(cand):
                cutter_path = cand
                break
        if cutter_path is None:
            print(f"  [{name}] [!] no prism found in {args.prism_dir} -- "
                  f"tile NOT cut to the boundary")
    elif args.prism:
        cutter_path = os.path.abspath(args.prism)

    if cutter_path:
        cutter = import_cutter(cutter_path)
        m = apply_cut(obj, cutter, preview=False, thickness=0)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=m.name)
        if len(obj.data.vertices) == 0:
            sys.exit(f"\n  [X] [{name}] the boolean produced an EMPTY mesh. "
                     f"Check that\n      the prism for this tile overlaps it in "
                     f"both XY and Z.\n")
        mesh_health(obj, "after boundary cut")
        lo2, hi2 = evaluated_z_range(obj)
        print(f"  [{name}] after boolean: Z {lo2:.2f} -> {hi2:.2f} mm, "
              f"{len(obj.data.polygons):,} faces")
        bpy.data.objects.remove(cutter, do_unlink=True)

    if args.plinth_mm > 0:
        add_plinth(obj, args.tile_w, args.tile_h, args.plinth_mm)
        nv, nonman, vol = mesh_health(obj, f"after {args.plinth_mm}mm plinth")
        if nv == 0:
            sys.exit(f"\n  [X] [{name}] the plinth union emptied the mesh.\n")
        if nonman:
            print(f"    [!] {nonman} non-manifold edges after the plinth union. "
                  f"The\n        tile's bottom faces are coplanar with the "
                  f"tray's, which the\n        solver can mishandle. Check this "
                  f"tile before printing.")

    if args.decimate_angle > 0:
        dec = obj.modifiers.new("dec", "DECIMATE")
        dec.decimate_type = "DISSOLVE"      # planar
        dec.angle_limit = args.decimate_angle * 3.14159265 / 180.0
        bpy.ops.object.modifier_apply(modifier=dec.name)

    # --- report ----------------------------------------------------------
    zs = [v.co.z for v in obj.data.vertices]
    print(f"  [{name}] tris~{len(obj.data.polygons):,}  "
          f"Z {min(zs):.2f} -> {max(zs):.2f} mm")

    if args.preview:
        print(f"  [{name}] built as a closed solid and cut; Displace is APPLIED, "
              f"so\n           change exaggeration by re-running with a new "
              f"--relief-mm.")
        return max(zs)

    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, name + ".stl")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.wm.stl_export(filepath=out, export_selected_objects=True,
                              global_scale=1.0)
    except AttributeError:                     # Blender < 4.2
        bpy.ops.export_mesh.stl(filepath=out, use_selection=True,
                                global_scale=1.0)
    print(f"  [{name}] -> {out}")
    return max(zs)


def preview(args, files):
    """A scene for choosing the exaggeration.

    Without --prism the Displace modifier is left live and Strength scrubs in
    the UI. With --prism the mesh must be a closed solid for the Boolean to
    work, so Displace is applied and exaggeration changes by re-running.
    """
    if len(files) > 1:
        print(f"  preview mode uses one heightmap; taking {os.path.basename(files[0])}")
    reset_scene()
    build_tile(files[0], args)

    # Pack the heightmap INTO the .blend so the file is self-contained and
    # cannot lose its texture to a path change, a move, or a different CWD.
    try:
        bpy.ops.file.pack_all()
        packed = [i.name for i in bpy.data.images if i.packed_file]
        print(f"  packed into the .blend: {', '.join(packed) or 'nothing'}")
    except Exception as e:
        print(f"  [!] could not pack images: {e}")

    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.preview))

    tr = args.true_relief_mm
    print(f"\n  Saved {args.preview}")
    if args.prism:
        print("  Built as a closed solid (extrude to Z=0 and cap) and cut to the")
        print("  boundary. Displace is APPLIED, so Strength no longer scrubs --")
        print("  re-run with a different --relief-mm to change exaggeration.")
    else:
        print("  Open it, select the object, and scrub the Displace modifier's")
        print("  Strength field. Nothing else in the scene depends on it.")
    if tr:
        print(f"\n  Strength (mm) / {tr} = exaggeration")
        print(f"  {'exagg':>7}  {'strength mm':>12}")
        for e in (1, 2, 3, 4, 6, 8, 10, 12):
            print(f"  {e:6.1f}x  {e * tr:12.1f}")
        print(f"\n  Current strength {args.relief_mm:.1f} mm "
              f"= {args.relief_mm / tr:.2f}x exaggeration")
    else:
        print("  Pass --true-relief-mm to get the exaggeration conversion "
              "printed here.")
    if args.prism:
        print("\n  NOTE: Solidify is NOT used. Offsetting a masked heightmap along")
        print("  its normals self-intersects at the near-vertical boundary cliff,")
        print("  and Blender's Exact boolean rejects that by returning an empty")
        print("  mesh -- with zero non-manifold edges and a correct volume.\n")
    else:
        print("\n  Terrain outside the city boundary normalises to 0, so it sits")
        print("  as a flat apron out to the rectangle's edge. That is correct --")
        print("  the boundary boolean trims it. Pass --prism data/prism.obj to")
        print("  see the real silhouette while judging.\n")


def load_sizes_csv(path):
    """name -> (tile_w_mm, tile_h_mm), name being the heightmap stem."""
    sizes = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            sizes[row["name"]] = (float(row["tile_w_mm"]), float(row["tile_h_mm"]))
    return sizes


def main():
    args = parse()
    files = sorted(glob.glob(os.path.join(args.heightmaps, args.pattern)))
    if not files:
        sys.exit(f"No heightmaps matching {args.pattern} in {args.heightmaps}")

    if args.preview:
        preview(args, files)
        return

    print(f"\n{len(files)} tiles | footprint {args.tile_w} x {args.tile_h} mm")
    src = _BASE_SRC if args.base_mm == _BASE_MM else "overridden on the command line"
    print(f"full-range relief {args.relief_mm} mm | base {args.base_mm} mm "
          f"[{src}]")
    print(f"expected tallest tile = {args.base_mm + args.relief_mm:.2f} mm")
    if args.road_mask:
        print(f"engraving roads {args.engrave_mm} mm deep")
    print()

    sizes = load_sizes_csv(args.sizes_csv) if args.sizes_csv else None
    default_tile_w, default_tile_h = args.tile_w, args.tile_h
    if sizes:
        print(f"--sizes-csv: {len(sizes)} tile(s) with their own footprint; "
              f"fallback for anything else is {default_tile_w} x "
              f"{default_tile_h} mm\n")

    heights = []
    for f in files:
        reset_scene()
        if sizes is not None:
            stem = os.path.splitext(os.path.basename(f))[0]
            if stem in sizes:
                args.tile_w, args.tile_h = sizes[stem]
            else:
                args.tile_w, args.tile_h = default_tile_w, default_tile_h
                print(f"  [{stem}] [!] not in --sizes-csv -- using the "
                      f"fallback footprint {default_tile_w} x "
                      f"{default_tile_h} mm. If this tile came from "
                      f"custom_tiles.py, that is almost certainly wrong.")
        heights.append(build_tile(f, args))

    print(f"\nDone. Tallest tile {max(heights):.1f} mm, "
          f"shortest {min(heights):.1f} mm.")
    print("Expected tallest = base + relief = "
          f"{args.base_mm + args.relief_mm:.1f} mm. If the tallest tile is "
          "well under that, no tile contains the project high point -- check "
          "your normalisation.\n")


if __name__ == "__main__":
    main()
