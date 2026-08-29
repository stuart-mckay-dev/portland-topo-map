# 04 — Blender Workflow

Goal: turn each 16-bit heightmap into a clean, watertight, correctly scaled STL.

Automate this with `scripts/blender_heightmap_to_mesh.py` rather than doing it
by hand 20 times. The manual steps below describe what the script does.

## Set up units first

Scene Properties → Units → **Millimeters**, Unit Scale 0.001. If you skip this,
everything exports at 1000× and you will not notice until the slicer.

## Per-tile procedure

### 1. Create the grid

Add a **Grid** primitive. Set X and Y subdivisions to match your target mesh
density — not the heightmap pixel count.

A useful target is **4–6 vertices per printed millimetre**. For a 180 mm tile
that is roughly 720–1080 subdivisions per side, i.e. ~0.5–1.2 M triangles per
tile. More than that buys nothing the nozzle can print and makes every
downstream step slow.

Scale the grid to the tile's exact footprint in mm.

### 2. Displace

Add a **Displace** modifier with the heightmap as an image texture.

- Texture interpolation: **Linear**. Extension: **Extend** (not Repeat — Repeat
  wraps terrain across the seam).
- Midlevel: **0**. This makes displacement run from 0 upward rather than
  ±half, so 16-bit value 0 maps to model Z 0.
- Strength: the **full-range relief in mm** for the active configuration, i.e.
  `true_relief_mm × exaggeration`. Get it from:

```
python3 scripts/topo_params.py plan --tile-mm 200 --cols 5 --rows 4 \
    --target-height-mm 50.8
```

Because the heightmap was normalised project-wide (see doc 03), the same
Strength value is correct for **every** tile. That is the whole point of
project-wide normalisation.

### 3. Solidify into a printable body

The displaced grid is a surface, not a solid. Two options:

- **Solidify modifier**, offset +1, thickness = base height. Fast, but produces
  a bottom that mirrors the terrain unless you also flatten it.
- **Preferred:** extrude the boundary edge loop straight down to Z = 0 and cap
  it. Gives a genuinely flat bottom and a clean vertical skirt at the tile
  edges, which is what butts cleanly against the neighbouring tile.

The script uses the second method.

### 4. Verify watertightness

3D-Print Toolbox add-on → Check All. You want zero non-manifold edges, zero
loose geometry, and a consistent normal direction. Fix before exporting; a
non-manifold STL will slice into something subtly wrong rather than failing
loudly.

### 5. Decimate only if needed

If the mesh is over ~1.5 M triangles, apply **Decimate → Planar** with an angle
of 1–2°. Planar decimation collapses the flat floodplain aggressively while
leaving the West Hills intact, which is exactly the right behaviour here.

Avoid Collapse decimation — it degrades ridgelines.

### 6. Export

STL or 3MF, millimetres, **no scene scaling applied on export**. Name to match
the heightmap: `pdx_<phase>_rNNcNN.stl`.

## Engraving roads

If using the engraved treatment (doc 07), the cleanest route is a second
displacement rather than a boolean:

1. Add a second Displace modifier **after** the terrain one.
2. Texture = the road mask (white = road, black = elsewhere).
3. Midlevel 1, Strength = engrave depth in mm (start at 0.35).

With Midlevel 1, white pixels displace by −Strength and black pixels displace
by 0, cutting grooves into the surface without a boolean operation. This is far
faster and far more robust than boolean-subtracting thousands of road solids,
and it cannot produce non-manifold geometry.

The groove follows the terrain, which is what you want — roads sit *in* the
hillside.

> Make the mask slightly blurred (1–2 px gaussian in QGIS) so groove walls get
> a small chamfer. A perfectly hard mask produces vertical groove walls that
> the slicer renders as ragged single-extrusion cliffs.

## Sanity checks before you print 20 of these

- Import two adjacent tiles together and confirm the terrain is continuous
  across the seam with no step.
- Measure the Z height of the tile containing the West Hills peak. It should
  equal `10 mm + relief` from `topo_params.py`. If it does not, the Displace
  Strength or the normalisation is wrong.
- Confirm the bottom is planar at Z = 0.
