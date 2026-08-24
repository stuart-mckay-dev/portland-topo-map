# 05 — Fusion 360 Workflow

Goal: the parts of the tile that are *manufactured* rather than *measured* —
the base, the tile-to-tile registration, and the wall mounting.

Terrain comes from Blender. Fusion handles everything with a defined dimension.

## Why a separate base body

The Blender tile already has a 10 mm slab. But that slab is a by-product of
extruding terrain downward — it has no features. The base needs:

- Registration so neighbours align without a visible step.
- Mounting provision.
- Enough rigidity that a 200 mm plate does not bow off the wall.

Two strategies:

**A. Model the base in Fusion, print separately, bond.**
Terrain tile prints with a thin (2–3 mm) slab; a separate base plate carries
all the features. More total print time, but the base can print fast and solid
while the terrain gets fine settings, and a failed terrain print does not cost
you the base.

**B. Model base features in Fusion, boolean into the terrain STL.**
One print per tile. Simpler assembly. Harder to iterate, because every change
means re-running the boolean against a million-triangle mesh.

**Recommend B for the pilot** (fewer prints, faster loop) and re-evaluate for
the final, where A's failure isolation matters more at 20 h/tile.

## Registration features

Tiles must align in X and Y and sit coplanar in Z. Options, roughly in order of
preference:

1. **Dovetail or T-slot keys** on the mating edges, with a separate printed
   spline. Self-aligning in Z, allows disassembly, tolerant of small warp.
   Print the key in a contrasting colour so a missing one is obvious.
2. **Alignment pins and sockets** — 3 mm pins, sockets at 3.2 mm. Simple, but
   only registers X/Y; coplanarity depends on the wall.
3. **Rabbet / half-lap edges** — each tile has a step, overlapping its
   neighbour. Very good for hiding seams, but makes the grid directional and
   the last tile hard to insert.

Whatever you choose, model it once as a Fusion component and pattern it, so
tolerance changes propagate. **Test the fit before committing** — print two
small edge coupons, not two full tiles.

Suggested starting clearance for PLA on an X1C: **0.15 mm per mating face**,
0.3 mm total on a pin/socket pair. Tune from the coupon.

## Mounting

Total assembly mass matters. `topo_params.py` reports it — a 6×5 final build at
6" of relief is over 13 kg, which is a real structural load, not a picture hook.

Options:

- **French cleat** running behind each tile row. Strongest, allows the piece to
  be hung in sections, and lets you take rows down individually. Model the
  female cleat as a recess in each tile's base.
- **Continuous backer panel.** Print or cut a plywood/aluminium backer, mount
  the backer to studs, attach tiles with VHB tape or magnets. Best for
  seam control because tile alignment is set by the backer, not by the wall.
  Also the best answer if you might ever move it.
- **Magnets.** Embed 6 mm × 3 mm magnets in the tile base and matching plates
  in the backer. Lets you pull individual tiles for repair. Adds cost across
  20+ tiles.

**Recommend the backer panel** for the final. Tile-to-tile registration
tolerance stacks across a 5-tile row; anchoring to a flat backer stops the
accumulation.

Design a **pocket for the cleat/magnet in Fusion, not in Blender** — it needs
real dimensions and a real fit.

## Edge treatment

Decide whether the installation has a border. A 3–5 mm raised frame around the
outer perimeter reads as intentional and hides the outermost tiles' edge
quality. If you want one, it lives in Fusion and only applies to perimeter
tiles, which means perimeter tiles are not interchangeable with interior ones —
note that in `csv/tiles.csv`.

## Export

STEP for archival, STL/3MF for the slicer. Keep the Fusion parametric model —
you will change clearances at least twice.
