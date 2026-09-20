# 03 — QGIS Workflow

Goal: turn raw lidar into one clean, continuous DEM, then cut it into per-tile
16-bit heightmaps with correctly shared edges.

## Step 1 — Define the project extent

Create the bounding box as a layer so every later step clips to exactly the
same rectangle.

1. Set the project CRS to **EPSG:6559** (NAD83(2011) / Oregon North, metres) or
   **EPSG:32610** (UTM 10N). Not 4326.
2. Create the bbox rectangle: 29,000 m × 25,000 m, centred on the city-limits
   extent centroid (EPSG:32610 E 527,009.0, N 5,043,315.6) — **not** on
   downtown. See `docs/DECISIONS.md` 2026-08-24.
3. Save as `data/derived/bbox.gpkg`. Everything downstream clips to this.

The bbox must be exact. If it drifts, tile boundaries drift, and the scale
math in `topo_params.py` no longer matches reality.

## Step 2 — Acquire and mosaic the DEM

Download the 3DEP 1 m subset for the bbox plus a small margin (200 m is
plenty). If it arrives as multiple tiles:

- **Raster → Miscellaneous → Merge** (`gdal_merge`) into one raster.
- Confirm the output is single-band Float32 and the nodata value is set.

Then **check the vertical units.** In the layer properties, look at the min/max.
If the maximum near the West Hills reads ~1,188 the data is in feet; if it
reads ~362 it is in metres. Convert feet to metres with the raster calculator
(`"dem@1" * 0.3048`) before doing anything else.

## Step 3 — Fill voids and flatten water

Bare-earth DEMs have holes where the classifier removed structures, and water
surfaces return noise.

- Voids: **Processing → GDAL → Raster analysis → Fill nodata**, max distance
  ~10 pixels.
- Water: rasterize the hydrography polygons and use the raster calculator to
  force those cells to a constant. The Willamette through downtown sits near
  3 m; the Columbia near 0.2 m. A rippled river is one of the most obvious
  tells of an unprocessed print.

## Step 4 — Smooth

At final scale, 1 m posts are far finer than the printer can resolve. At
1:30,000, one model millimetre is ~31 m of ground — so roughly 31 DEM pixels
collapse into a single millimetre.

Resample to something closer to the print resolution before meshing. Target
about **4–8 DEM samples per printed millimetre**, then apply a light gaussian.

```
target_ground_res_m = (scale_denominator / 1000) / samples_per_mm
```

At 1:31,250 with 6 samples/mm that is ~5.2 m. Resampling from 1 m to 5 m with
bilinear or cubic averaging removes lidar speckle and drops mesh complexity by
25× with no visible loss. Do not skip this — it is the difference between a
2-minute Blender import and a 40-minute one.

Road masks are rasterised from vector centrelines, not sampled from the DEM,
so they do **not** need a sharper DEM — their crispness comes from the vectors
and the output grid. (Corrected 2026-08-24.)

## Step 5 — Normalise to a 16-bit heightmap

Scale elevation into the full 16-bit integer range so Blender's displacement
has maximum precision.

```
normalised = (dem - ELEV_MIN) / (ELEV_MAX - ELEV_MIN) * 65535
```

Use the **project-wide** min and max (0.19 m and 362 m), not per-tile min/max.
Per-tile normalisation is the classic mistake here: it makes every tile use the
full range and the terrain no longer lines up across seams.

Export as 16-bit unsigned GeoTIFF or PNG.

> 16 bits across a 362 m range is 5.5 mm of real elevation per level. At 8×
> exaggeration that is 0.044 mm of model height per level — well under one layer
> line. 16-bit is sufficient; 8-bit is not (1.4 m per level would produce
> visible banding on the flats).

## Step 6 — Tile

Use `scripts/qgis_export_tiles.py`, or **Raster → Extraction → Clip raster by
extent** per tile.

**The seam rule:** adjacent tiles must share their edge samples exactly. Cut
tiles on exact pixel boundaries derived from the bbox, and give each tile a
**one-pixel overlap** with its neighbours so the edge vertices are generated
from identical elevation values. Independently cropping and re-meshing produces
a visible ridge or gutter at every seam.

Naming: `pdx_<phase>_r<row>c<col>.tif`, row 1 = north, col 1 = west.

## Step 7 — Prepare the road/bike overlays

Only if you are engraving or colouring roads. See
`docs/07-roads-and-color.md` for which treatment applies.

1. Pull vectors with `scripts/fetch_pdx_vectors.py`.
2. Reproject from Web Mercator to the project CRS. **Before buffering.**
3. Filter: `Status = 'ACTIVE'` for the bike network.
4. Buffer each line to its intended printed width, converted to ground metres:
   `ground_width_m = printed_width_mm * scale_denominator / 1000`.
   At 1:31,250, a 0.8 mm printed road line is a 25.0 m ground buffer — roughly
   a real arterial's right-of-way, which is a happy coincidence.
5. Rasterize to a mask aligned to the same grid as the DEM tiles.

Export one mask per colour class you intend to use.

## Outputs of this stage

```
data/derived/portland_dem.tif          full merged, cleaned, metres
data/derived/portland_dem_smooth.tif   resampled to print resolution
data/heightmaps/pdx_<phase>_rNNcNN.tif 16-bit per-tile heightmaps
data/derived/mask_roads.tif            optional
data/derived/mask_bike_<class>.tif     optional, one per colour class
```
