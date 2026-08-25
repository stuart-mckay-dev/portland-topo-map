# 00 — Project Specification

## Goal

A wall-mounted scale topographic relief of the City of Portland, Oregon,
printed as a grid of interlocking tiles on a Bambu Lab X1 Carbon, assembled
into one continuous terrain surface.

## Success criteria

The piece succeeds if, standing at normal viewing distance (1.5–2.5 m):

1. The West Hills / Tualatin Mountains read as a clear ridge against the
   Willamette floodplain.
2. Individual landmark features are identifiable without labels — Mt Tabor,
   Rocky Butte, Powell Butte, Kelly Butte, the Willamette and Columbia
   channels, Ross Island, Forest Park's ravine structure.
3. Street structure is legible at closer range (under ~1 m) without dominating
   the terrain read at distance.
4. Tile seams are visible only on deliberate inspection.
5. The piece does not project so far from the wall that it feels obtrusive in
   the room.

## Source geometry

| Property | Value |
|---|---|
| Bounding box, E–W | 29,000 m (18.02 mi) |
| Bounding box, N–S | 25,000 m (15.53 mi) |
| Aspect ratio | 1.1600 : 1 (wider than tall) |
| Lowest elevation | 0.19 m / 0.62 ft — Columbia River |
| Highest elevation | 362 m / 1,188 ft — West Hills |
| Elevation range | 361.81 m |

## Fixed design decisions

- The lowest elevation sits **10 mm** above the build plate. Everything scales
  from that datum. The 10 mm slab is structure and mounting substrate.
- Tiles are printed **terrain-side up**, flat on the plate. No supports.
- The longest tile edge stays at or under **200 mm** unless a specific tile is
  promoted to the 230 mm stretch limit for a documented reason.
- Tiles are rectangular and **all the same size** within a phase. Grid
  proportions are chosen so tiles come out near-square.

## Undecided

See `docs/OPEN-QUESTIONS.md`. The two big ones:

- **Final wall dimensions.** Owner is measuring candidate locations. Everything
  downstream (scale, tile count, exaggeration, cost) is parameterised on this.
- **Vertical exaggeration.** To be chosen empirically from pilot prints. Owner
  has stated a tolerance ceiling of ~8" (203 mm) of projection off the wall,
  which is a limit, not a target.

## Toolchain

| Stage | Tool | Output |
|---|---|---|
| Data acquisition | OpenTopography / DOGAMI / PortlandMaps | GeoTIFF DEM, vector layers |
| DEM prep, reprojection, tiling | QGIS | Per-tile 16-bit heightmap PNG/TIFF |
| Mesh generation, cleanup, decimation | Blender | Watertight per-tile STL |
| Base geometry, alignment features | Fusion 360 | Base + registration STL |
| Slicing | Bambu Studio | 3MF / gcode |
| Printing | Bambu Lab X1 Carbon + AMS | Tiles |

## Budget reality

Print time and filament scale with vertical exaggeration and with tile count.
Both grow fast. `scripts/topo_params.py` reports estimated kilograms and hours
for any configuration — consult it *before* committing to a size, not after.

At the owner's stated 20 h/tile, a 20-tile final build is roughly 400 hours of
machine time. This is the single strongest argument for running the pilot first.
