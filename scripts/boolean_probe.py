#!/usr/bin/env python3
"""
boolean_probe.py -- Bisect a failing Boolean by testing each operand alone.

Run:
  blender -b -P scripts/boolean_probe.py -- --prism data/prism.obj \\
      --heightmap data/heightmaps/pdx_preview_r01c01.png \\
      --tile-w 313 --tile-h 270 --relief-mm 6.5

An empty Boolean result tells you nothing about WHICH operand is at fault.
This runs four tests against a known-good reference cube, so the answer is a
table rather than a hypothesis:

  A  cube  INTERSECT cube    does Boolean work at all in this build?
  B  cube  INTERSECT prism   is the prism a valid operand?
  C  terrain INTERSECT cube  is the solidified terrain a valid operand?
  D  terrain INTERSECT prism the real case

Whichever row is the first to return 0 is the operand to fix.
"""
import sys, os

try:
    import bpy, bmesh, mathutils
except ImportError:
    sys.exit("Run inside Blender: blender -b -P scripts/boolean_probe.py -- ...")


def argv():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def parse():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--prism", required=True)
    p.add_argument("--heightmap", required=True)
    p.add_argument("--tile-w", type=float, default=313.0)
    p.add_argument("--tile-h", type=float, default=270.0)
    p.add_argument("--relief-mm", type=float, default=6.5)
    p.add_argument("--subdiv", type=int, default=200)
    return p.parse_args(argv())


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.unit_settings.system = "METRIC"
    s.unit_settings.scale_length = 0.001
    s.unit_settings.length_unit = "MILLIMETERS"


def mesh_report(obj, label):
    me = obj.data
    bm = bmesh.new(); bm.from_mesh(me)
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    loose = sum(1 for v in bm.verts if not v.link_edges)
    vol = bm.calc_volume(signed=True)
    bm.free()
    print(f"    {label:22s} {len(me.vertices):8,} v  {len(me.polygons):8,} f  "
          f"non-manifold edges {nonman:5d}  loose v {loose:4d}  "
          f"signed volume {vol:+12,.1f}")
    return len(me.vertices), nonman, vol


def add_cube(size, name):
    bpy.ops.mesh.primitive_cube_add(size=size, location=(0, 0, 0))
    o = bpy.context.active_object
    o.name = name
    return o


def import_prism(path):
    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.obj_import(filepath=os.path.abspath(path),
                              forward_axis="Y", up_axis="Z")
    except TypeError:
        bpy.ops.wm.obj_import(filepath=os.path.abspath(path))
    o = list(set(bpy.data.objects) - before)[0]
    o.name = "prism"
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(o.data); bm.free()
    return o


def build_terrain(a):
    longest = max(a.tile_w, a.tile_h)
    xs = max(4, int(round(a.subdiv * a.tile_w / longest)))
    ys = max(4, int(round(a.subdiv * a.tile_h / longest)))
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=xs, y_subdivisions=ys, size=1.0)
    o = bpy.context.active_object
    o.name = "terrain"
    o.scale = (a.tile_w, a.tile_h, 1.0)
    bpy.ops.object.transform_apply(scale=True)

    import numpy as np
    me = o.data
    uvl = me.uv_layers[0] if me.uv_layers else me.uv_layers.new(name="UVMap")
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    minx, miny = co[:, 0].min(), co[:, 1].min()
    w = co[:, 0].max() - minx; h = co[:, 1].max() - miny
    li = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", li)
    uvs = np.empty((len(me.loops), 2), dtype=np.float32)
    uvs[:, 0] = (co[li, 0] - minx) / w
    uvs[:, 1] = (co[li, 1] - miny) / h
    uvl.data.foreach_set("uv", uvs.ravel())

    img = bpy.data.images.load(os.path.abspath(a.heightmap))
    tex = bpy.data.textures.new("hm", type="IMAGE"); tex.image = img
    if hasattr(tex, "extension"): tex.extension = "EXTEND"
    d = o.modifiers.new("terrain", "DISPLACE")
    d.texture = tex; d.texture_coords = "UV"; d.direction = "Z"
    d.mid_level = 0.0; d.strength = a.relief_mm
    d.uv_layer = uvl.name
    bpy.ops.object.modifier_apply(modifier=d.name)

    sol = o.modifiers.new("sol", "SOLIDIFY")
    sol.thickness = 10.0; sol.offset = -1.0
    bpy.ops.object.modifier_apply(modifier=sol.name)
    return o


def do_bool(target, cutter, label):
    b = target.modifiers.new("b", "BOOLEAN")
    b.operation = "INTERSECT"; b.object = cutter
    if hasattr(b, "solver"): b.solver = "EXACT"
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=b.name)
    n = len(target.data.vertices)
    print(f"  {label:34s} -> {n:8,} verts   {'OK' if n else '*** EMPTY ***'}")
    return n


def main():
    a = parse()
    print("\n=== operand health ===")
    reset(); p = import_prism(a.prism); mesh_report(p, "prism")
    reset(); t = build_terrain(a);      mesh_report(t, "terrain (solidified)")
    reset(); c = add_cube(100.0, "cube"); mesh_report(c, "reference cube")

    print("\n=== boolean matrix ===")
    reset(); c1 = add_cube(100.0, "c1"); c2 = add_cube(60.0, "c2")
    do_bool(c1, c2, "A  cube INTERSECT cube")

    reset(); c = add_cube(100.0, "c"); p = import_prism(a.prism)
    do_bool(c, p, "B  cube INTERSECT prism")

    reset(); t = build_terrain(a); c = add_cube(100.0, "c")
    do_bool(t, c, "C  terrain INTERSECT cube")

    reset(); t = build_terrain(a); p = import_prism(a.prism)
    do_bool(t, p, "D  terrain INTERSECT prism")

    print("\n  NOTE: this probe builds the terrain with SOLIDIFY, which is the")
    print("  known-bad construction -- row C is expected to fail. It is kept as")
    print("  a reproduction of the failure, not a test of current behaviour.")
    print("  blender_heightmap_to_mesh.py now extrudes the boundary loop to Z=0")
    print("  and caps it instead, which cannot self-intersect.\n")
    print("  The first row that returns 0 names the operand to fix.")
    print("  A fails -> the build. B fails -> the prism. C fails -> the")
    print("  terrain/solidify. Only D fails -> an interaction, most likely")
    print("  coincident faces or scale.\n")


if __name__ == "__main__":
    main()
