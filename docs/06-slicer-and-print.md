# 06 — Bambu Studio and Printing

## Plate strategy

Tile size is set by the map grid, not by the plate — but small pilot tiles
should be **ganged**. A 76 × 90 mm pilot tile fits six-up on a 256 mm plate
(228 × 180 mm), turning a 12-tile pilot into two plates instead of twelve
separate prints.

Final-phase tiles at ~180–200 mm are one per plate. Plan for that: a 20-tile
build is 20 discrete print jobs plus setup, not one weekend.

## Orientation

**Terrain up, flat on the plate. Always.**

- The flat base is the ideal first layer.
- A heightfield cannot produce an overhang — every point has exactly one Z —
  so steep terrain becomes a near-vertical wall, which prints fine.
- **Never enable supports for terrain.** If the slicer wants supports, your
  mesh is broken (inverted normals or non-manifold geometry). Go fix the mesh.

## Settings

Starting point for PLA on an X1C. Tune on the pilot.

| Setting | Value | Why |
|---|---|---|
| Layer height | 0.12–0.16 mm | Terracing on shallow slopes is the dominant artifact; finer layers directly reduce it. 0.2 mm is acceptable only at high exaggeration |
| First layer | 0.2 mm | Adhesion on a large flat footprint |
| Wall loops | 3 | Rigidity for a wall-mounted plate |
| Top layers | 5 | Terrain is the visible surface; skimping shows as pinholes on shallow slopes |
| Bottom layers | 4 | |
| Infill | 10–15 % gyroid | Gyroid resists the bowing that flat plates develop |
| Brim | 5 mm, outer only | Corner lift is the main failure mode at this footprint |
| Draft shield | on, for tiles > 180 mm | |
| Ironing | top surface only, optional | Smooths shallow slopes; adds significant time. Test both |

## The corner-warp problem

Large flat-bottomed prints lift at the corners. This project's tiles are the
textbook case: big footprint, thin base, long print. Mitigations in order of
effectiveness:

1. Clean the plate with dish soap and hot water, not just IPA. Oil is the
   usual culprit.
2. Brim, 5 mm minimum.
3. Enclosure closed, and let the chamber warm up before starting.
4. Reduce cooling on the first 5 layers.
5. If it still lifts, drop the tile size rather than fighting it — this is
   exactly why the project caps at 200 mm rather than 256 mm.

## Layer terracing

The signature artifact of printed topography: on shallow slopes a single layer
step spreads across many millimetres of XY, producing visible contour terraces.

Portland's flats are the worst case. Options, in order:

1. **Increase vertical exaggeration.** Steeper slopes = tighter terraces. This
   is the most effective lever and it costs nothing extra beyond the filament
   already budgeted.
2. **Reduce layer height** to 0.12 mm.
3. **Accept it as a feature.** Terracing on a topographic map reads as contour
   lines. Some of the best-looking printed relief maps lean into this. Look at
   a pilot tile before deciding it is a defect.

## Multi-colour

If using the AMS, read `docs/07-roads-and-color.md` first — the purge cost
difference between Z-banding and XY colour is roughly 150×.

For elevation banding, set band Z heights **once in a saved project profile**
and apply identically to every tile. If band heights drift between tiles the
bands will not line up across seams, which is far more visible than a terrain
mismatch.

Enable "purge into infill" and "purge into object" to reclaim some waste.

## Per-tile print records

Before starting any print, add its row to `csv/tiles.csv`. Record the
slicer's *estimated* time and filament, then the actuals afterwards. After
three or four tiles you will have real throughput numbers — plug them into
`PRINT_RATE_CM3_PER_HR` in `topo_params.py` so every future estimate is
calibrated to your machine rather than to a guess.

## Failure triage

| Symptom | Likely cause |
|---|---|
| Slicer requests supports | Broken mesh — non-manifold or inverted normals |
| Visible ridge at a tile seam | Tiles cropped independently; re-cut with shared edge pixels |
| River surface looks rippled | Water not flattened in QGIS |
| Terrain looks like stair steps | Terracing — see above |
| Roads missing from the print | Groove narrower than one extrusion width |
| Whole map looks 3.3× too tall | Elevation data was in feet, not metres |
| Tiles do not line up in Z | Per-tile normalisation instead of project-wide |
