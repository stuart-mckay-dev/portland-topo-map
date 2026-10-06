# PortlandTopo Runbook

This runbook rebuilds the map end to end, from an empty `data/` directory to printed tiles on the wall. It is written so the project can be rebuilt from scratch: by future-me, on a new machine, or at a different scale.

The runbook lists the steps in order, the commands to run, and the **gate** each step has to pass before the next one starts. The reasoning behind each step is in `docs/`; the most detailed version is [`docs/11-pilot-runsheet.md`](docs/11-pilot-runsheet.md). When this runbook and a doc disagree, check [`docs/DECISIONS.md`](docs/DECISIONS.md), because the most recent dated entry there wins.

> **Golden rules**
> 1. Every dimensional number comes from `scripts/topo_params.py`. Never type a derived number by hand.
> 2. Work in a projected CRS (EPSG:32610, UTM 10N, metres). Never do distance, buffer or slope math in degrees.
> 3. Normalise elevation **project-wide**, never per tile.
> 4. Check the **output** of every geometry stage, not the settings that produced it.
> 5. Every print gets a row in `csv/tiles.csv` *before* it starts.
> 6. `data/` is generated. Never hand-edit it; regenerate it instead.

---

## 0. Reference values (pilot)

These are the values the pilot was built with. For a new scale, regenerate them with `topo_params.py`; don't copy them.

| Quantity | Pilot value | Source |
|---|---|---|
| Project bbox | 29,000 × 25,000 m centred on E 527,009 / N 5,043,316 (EPSG:32610) | `topo_params.py` |
| Grid | 4 cols × 3 rows, boundary-fitted, tile 78.46 × 90.0 mm | `tile_grid_explore.py` |
| Scale | ≈ 1:92,000 | `topo_params.py plan` |
| True (1×) relief | ≈ 3.9 mm for the full elevation range | `topo_params.py plan` |
| Displace strength | 8.0 mm (2.03× exaggeration) | DECISIONS 2026-08-24 |
| Base slab | 4 mm under the lowest point | `BASE_MM` |
| Elevation range | `ELEV_MIN_M` / `ELEV_MAX_M` = project floor / 362.0 m | Step 8h |
| Print resolution | 15.4 m/px (6 samples per printed mm) | Step 9 |
| Boundary smoothing | `--d 50 --chaikin 2 --dp 10` plus 5 spot edits, hard ceiling D < 75 | Step 8d |
| Hard caps | 200 mm max tile edge (warp, not bed size) | DECISIONS 2026-08-20 |

---

## 1. Environment

| Tool | Version | Used for |
|---|---|---|
| Python | 3.9+ | All scripts. `topo_params.py`, `color_cost.py`, `hollow_model.py` and the fetchers are stdlib-only |
| GDAL CLI | bundled with QGIS | `gdalwarp`, `gdal_calc.py`, `ogr2ogr` |
| QGIS | 3.34 LTR+ | Inspecting layers, 3D preview, drawing custom tiles |
| Blender | 4.2+ | Headless meshing (`bpy`) |
| Bambu Studio | current | Slicing for the X1 Carbon + AMS |

```bash
git clone <this repo> PortlandTopo && cd PortlandTopo
python3 -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt         # numpy, rasterio, requests, shapely>=2.1
mkdir -p data/raw data/derived data/heightmaps data/vectors data/prisms data/tiles

# macOS: Blender's binary is not on PATH
alias blender="/Applications/Blender.app/Contents/MacOS/Blender"
blender --version
```

**OpenTopography API key:** register at <https://portal.opentopography.org/>, then put the key in `OpenTopography_API_Key.txt` at the repo root, or use `export OPENTOPO_API_KEY=...`. That file is gitignored. **Never commit it.**

**Gate:** `python3 scripts/topo_params.py compare` runs and prints the candidate configurations.

---

## 2. Plan the build

```bash
python3 scripts/topo_params.py compare                       # pilot vs final candidates
python3 scripts/topo_params.py grid --max-tile-mm 200        # near-square grids under the cap
python3 scripts/topo_params.py plan --tile-mm 90 --cols 4 --rows 3 --label pilot
python3 scripts/topo_params.py exagg --wall-width-mm 313 --cols 4 --rows 3
```

Write down the **scale denominator**, the **true 1× relief in mm** and the **tile footprint**. Steps 8, 9 and 11 use all three.

Mass and time from `topo_params.py` assume full rectangular tiles. For a boundary-cut map, multiply them by the city's share of the grid, which is about **52.5%** for Portland.

---

## 3. Acquire the DEM

```bash
python3 scripts/fetch_dem.py --check-key                     # confirms the key works
python3 scripts/fetch_dem.py --dry-run                       # prints the query, downloads nothing

# smoke test on a 4 km West Hills box before the full pull
python3 scripts/fetch_dem.py --dataset USGS10m \
    --south 45.487034 --north 45.522966 --west -122.715635 --east -122.664365 \
    --out data/raw/smoke_westhills.tif
python3 scripts/dem_stats.py data/raw/smoke_westhills.tif

# full bbox
python3 scripts/fetch_dem.py --dataset USGS10m --out data/raw/portland_3dep_10m.tif
python3 scripts/dem_stats.py data/raw/portland_3dep_10m.tif
```

- `USGS1m` returns **HTTP 401** on a free account, because that tier is restricted to institutional users. The 10 m product gives ~9 samples per printed mm at pilot scale, which is more than the 0.4 mm nozzle can render.
- If the request is too large, split the bbox into quadrants and run `gdal_merge.py -n -9999 -a_nodata -9999`.
- Log the date, dataset ID and exact query in `docs/SOURCES.md`.

**Gate:**
- **Vertical units are metres.** The West Hills max should land near 330–390 m. A value near 1,100–1,280 means the data is in feet. Convert it with `gdal_calc.py --calc="A*0.3048"` or every later number will be off by 3.28×.
- `% filled` is 100% (the 3DEP 1/3″ product is void-filled).

---

## 4. Reproject (mandatory, and it comes first)

3DEP arrives in **EPSG:4269 (degrees)**, not UTM. Its pixels are 7.2 m wide and 10.3 m tall at this latitude.

```bash
gdalwarp -s_srs EPSG:4269 -t_srs EPSG:32610 -r bilinear -tr 10 10 \
    -of GTiff data/raw/portland_3dep_10m.tif data/derived/dem_32610.tif
python3 scripts/dem_stats.py data/derived/dem_32610.tif
```

Use `bilinear` here. The one deliberate downsample happens in step 9 with `average`, and averaging twice smears ridgelines.

**Gate:** `dem_stats.py` shows no `[!] GEOGRAPHIC CRS` warning, and the pixel size reads `10 × 10` m. Every later step reads `dem_32610.tif`.

---

## 5. Flatten water

Lidar returns from water are noisy, and an unflattened river prints visibly rippled. 3DEP is **partly** pre-flattened, at different levels for each river: the Columbia sits at ≈ 1.90 m and the Willamette at ≈ 2.86–2.98 m.

1. Pull hydrography polygons (PortlandMaps or NHD) and reproject them to EPSG:32610.
2. Rasterize **two separate masks**, one per river, onto the DEM grid.
3. Burn each mask at its own measured level:

```bash
gdal_calc.py -A data/derived/dem_32610.tif -B data/derived/mask_willamette.tif \
    --outfile=data/derived/dem_flat_w.tif --calc="where(B==1, 2.90, A)" --NoDataValue=-9999
gdal_calc.py -A data/derived/dem_flat_w.tif -B data/derived/mask_columbia.tif \
    --outfile=data/derived/dem_flat.tif   --calc="where(B==1, 1.90, A)" --NoDataValue=-9999
```

**Gate:** there is no ~1 m step at Kelley Point, where the two rivers meet. Forcing both rivers to one constant causes exactly that step.

---

## 6. Build the boundary

### 6a. Fetch and reproject

```bash
curl -o data/vectors/portland_city_limits_4326.geojson \
  "https://gis.oregonmetro.gov/arcgis/rest/services/OpenData/BoundaryDataWebMerc/MapServer/0/query?where=CITYNAME%3D%27Portland%27&outFields=*&outSR=4326&f=geojson"
ogr2ogr -t_srs EPSG:32610 data/vectors/portland_city_limits.geojson \
    data/vectors/portland_city_limits_4326.geojson
```

Use **layer 0 (city limits)**, not layer 6 (the UGB, which covers 3.7× the area). Dissolve, and leave the enclaves out.

> **GeoJSON CRS trap:** RFC 7946 dropped the `crs` member, but GDAL and QGIS still read it. A file without one is assumed to be WGS84. Rewriting a file doesn't fix a layer QGIS has already loaded; remove the layer and add it again.

### 6b. Sweep the smoothing radius

```bash
python3 scripts/smooth_boundary.py --in data/vectors/portland_city_limits.geojson \
    --scale 92593 --sweep
```

Read **AMPUTATION** (material lost, which can't be undone) and **INTRUSION** (notches filled) as two separate columns. Look for the cliff: at pilot scale, amputation jumps from 235 m to 1,571 m between D = 50 and D = 75, because a whole limb of the city detaches. Pick D below the cliff. If the result is still too jagged, raise `--chaikin`, not D. Chaikin cuts corners and can't amputate anything.

### 6c. Commit the outline, with spot edits

```bash
python3 scripts/smooth_boundary.py \
    --in  data/vectors/portland_city_limits.geojson \
    --out data/vectors/boundary_smoothed.geojson \
    --scale 92593 --d 50 --chaikin 2 --dp 10 \
    --edit "cut:535344,5048230"  --edit "drop:518819,5041261" \
    --edit "drop:540031,5036484" --edit "fill:519080,5042530" \
    --edit "fill:525646,5032262" \
    --buffer-out data/vectors/boundary_buffered.geojson --buffer-m 50
```

Spot edits are addressed by **point**, not by threshold. Any area threshold large enough to reach the five features you want also removes a dozen you want to keep. Rebuild the outline for every new scale; never reuse the pilot polygon.

**Gate:** one polygon part (≈ 924 vertices, ≈ 376.4 km² at pilot settings). NW Linnton's straight diagonal survives, and the per-edge character in `docs/11 §8d` looks right.

---

## 7. Choose the tile grid

```bash
python3 scripts/tile_grid_explore.py --boundary data/vectors/boundary_smoothed.geojson --search
python3 scripts/tile_grid_explore.py --boundary data/vectors/boundary_smoothed.geojson \
    --cols 4 --rows 3 --offset-x 0.0 --offset-y 0.0 \
    --png data/grid_4x3.png --grid-out data/vectors/grid_4x3.geojson
```

Fitting the grid to the boundary extent, rather than the raster extent, avoids tiles that only hold a few percent of city. Any slivers that remain get handled in step 11b.

**Gate:** no tile edge exceeds 200 mm. Write down the grid bounds, because `qgis_export_tiles.py --bounds` and `boundary_prism.py --bounds` must receive **identical** values.

---

## 8. Mask, then re-derive the elevation constants

```bash
# working raster: +50 m buffered cutline, so the resampling kernel has data at the rim
gdalwarp -cutline data/vectors/boundary_buffered.geojson -dstnodata -9999 \
    data/derived/dem_flat.tif data/derived/dem_masked.tif

# constants: TRUE cutline, no buffer
gdalwarp -cutline data/vectors/boundary_smoothed.geojson -dstnodata -9999 \
    data/derived/dem_flat.tif data/derived/dem_stats_only.tif
python3 scripts/dem_stats.py data/derived/dem_stats_only.tif
```

Set `ELEV_MIN_M`, `ELEV_MAX_M` and `MEAN_ELEV_FRACTION` from the **masked, unbuffered** statistics. Never take them from the raw rectangle: its 391 m maximum is the Tualatin crest, which lies outside the city. Update the values in **both** `topo_params.py` and `qgis_export_tiles.py`, because the constants are duplicated and must not drift apart.

**Gate:**
- The masked DEM is about 50% filled. That's the city's share of the bbox.
- No cells sit above `ELEV_MAX_M`. The export clips at 1.0, so anything above the ceiling would print as a flat plateau.
- `dem_stats.py` doesn't refuse the paste instruction (it refuses when the raster is more than 90% filled, which means it wasn't masked).

---

## 9. Resample to print resolution

```
target_res_m = (scale_denominator / 1000) / samples_per_mm   →   92,593 / 1000 / 6 ≈ 15.4 m
```

```bash
gdalwarp -tr 15.4 15.4 -r average -of GTiff \
    data/derived/dem_masked.tif data/derived/portland_dem_smooth.tif
```

Recompute this for every scale. The 7×6 final at 1:20,833 needs ≈ 3.5 m, which means the 10 m source becomes the limiting factor there.

---

## 10. Export heightmaps

```bash
python3 scripts/qgis_export_tiles.py --dem data/derived/portland_dem_smooth.tif \
    --out data/heightmaps --cols 4 --rows 3 --phase pilot --png
```

**Gate:**
- The output prints `project range: <ELEV_MIN_M> -> 362.00 m`. Never pass `--auto-range` for real tiles.
- There is no `[!] This DEM may be in FEET` warning.
- The output has 12 files named `pdx_pilot_rNNcNN`, with row 1 = **north** and col 1 = **west**.

Use `--png` for Blender. Blender reads some GeoTIFFs as 0×0 images without raising an error.

---

## 11. Choose the vertical exaggeration

The heightmaps carry no exaggeration. It enters **exactly once**, as the Blender Displace strength:

```
strength_mm = true_relief_mm × exaggeration        (pilot: 3.9 × 2.03 ≈ 8.0 mm)
```

Build a live preview and scrub the strength:

```bash
python3 scripts/qgis_export_tiles.py --dem data/derived/dem_masked.tif \
    --out data/heightmaps --cols 1 --rows 1 --phase preview --png
blender -b -P scripts/blender_heightmap_to_mesh.py -- \
    --heightmaps data/heightmaps --pattern "pdx_preview_*.png" --out /tmp \
    --tile-w 313 --tile-h 270 --relief-mm 15.6 --subdiv 800 \
    --true-relief-mm 3.91 --preview data/preview.blend
```

Open `data/preview.blend`, light it from a low angle, and scrub **Strength**. Price the value you choose:

```bash
python3 scripts/topo_params.py plan --tile-mm 90 --cols 4 --rows 3 --target-height-mm <peak_mm>
```

Record the value and the reasoning in `docs/DECISIONS.md`.

> The pilot's first pick, 1.66×, was made against a model whose flats had been crushed by the sRGB bug. Once that was fixed, the same eye picked 2.03×. **A design decision made against unverified geometry is not a decision.**

### 11b. Custom tiles (optional)

To merge slivers, or to cut tiles along a ridge or a river, draw the tiles as polygons in QGIS: one feature per tile, with a `tile_id` field, in EPSG:32610. Then run:

```bash
python3 scripts/custom_tiles.py check --shapes data/vectors/custom.geojson \
    --boundary data/vectors/boundary_smoothed.geojson --scale-denom 92593
python3 scripts/custom_tiles.py build --shapes data/vectors/custom.geojson \
    --boundary data/vectors/boundary_smoothed.geojson --dem data/derived/portland_dem_smooth.tif \
    --scale-denom 92593 --out-heightmaps data/heightmaps_custom --out-prisms data/prisms_custom
```

In step 13, pass `--sizes-csv data/heightmaps_custom/tile_sizes.csv` so each tile uses its own footprint.

---

## 12. Build the cutting prisms

Masking the raster is not enough to cut the model: terrain outside the boundary normalises to zero and prints as a flat apron. A mesh boolean against an extruded boundary prism produces the real edge.

```bash
python3 scripts/boundary_prism.py \
    --boundary data/vectors/boundary_smoothed.geojson \
    --ref-raster data/derived/portland_dem_smooth.tif \
    --tile-w 78.46 --tile-h 90.0 --cols 4 --rows 3 --phase pilot \
    --z-min -5 --z-max 60 --format obj --out data/prisms/
```

**Gate, for every prism:**
- `non-manifold 0`
- **Signed volume > 0.** A negative volume means the prism is inside out. It renders perfectly but booleans as its own complement, so the result comes back empty.
- The X and Y scales agree within ~1%. A mismatch means the tile size disagrees with the raster aspect.
- `--z-min` is below the model floor and `--z-max` is above the peak.

---

## 13. Mesh the tiles (headless Blender)

```bash
blender -b -P scripts/blender_heightmap_to_mesh.py -- \
    --heightmaps data/heightmaps --pattern "pdx_pilot_*.png" \
    --out data/tiles --tile-w 78.46 --tile-h 90.0 \
    --relief-mm 8.0 --subdiv 470 --prism-dir data/prisms/
```

`--relief-mm` is the **full project relief** (true relief × exaggeration), not the tile's own height. The same value goes to every tile, and that's why the seams line up. Leave `--base-mm` unset unless you're testing; it defaults to `BASE_MM` from `topo_params.py`.

The script refuses to export a tile that fails any health check. Each stage reports its vertex count, face count, non-manifold edges and signed volume, and the script checks:

| Check | Catches |
|---|---|
| image size ≠ 0×0 | an undecodable texture |
| evaluated Z span ≈ `--relief-mm` × peak | a missing UV layer, or sRGB decoding (heightmaps must be **Non-Color**) |
| packed image | a relative path that breaks when the `.blend` is reopened |
| signed volume > 0, non-manifold = 0 | an inverted prism, or a broken boolean |

The skirt is an **extrusion of the boundary loop to Z = 0**, never a Solidify. Solidify folds the masked cliff edge through itself, and the Exact boolean then returns an empty mesh without raising an error.

**If a boolean returns empty**, don't keep inspecting the suspect input. Bisect it:

```bash
blender -b -P scripts/boolean_probe.py -- --prism data/prisms/pdx_pilot_r02c02_prism.obj \
    --heightmap data/heightmaps/pdx_pilot_r02c02.png --tile-w 78.46 --tile-h 90 --relief-mm 8.0
```

The first row of its table that returns 0 identifies the operand at fault.

**Gate:**
- Every exported tile passes. Run 3D-Print Toolbox → Check All on **every** tile, not a sample.
- The tile volumes sum to the expected bulk (pilot: ≈ 502 cm³ across 10 tiles).

---

## 14. Per-tile planning

```bash
python3 scripts/tile_heights.py --heightmaps data/heightmaps --relief-mm 8.0 --base-mm 4 --stats
python3 scripts/tile_heights.py --heightmaps data/heightmaps --relief-mm 8.0 --base-mm 4 --csv
python3 scripts/hollow_model.py                 # only matters at high relief
python3 scripts/color_cost.py --sweep           # before proposing any XY colour
```

- Seed `csv/tiles.csv` from the output. Mark tiles with almost no material `omitted`, or merge them using step 11b.
- Hollowing pays off above ~60 mm mean tile height. Below that height, use `RIB_BOX`; above it, use `RIB_SHELL`. **Never put support above a `RIB_BOX` ceiling**, because the support gets sealed in on all six sides.

---

## 15. Base, registration, mounting (Fusion 360)

Covered in `docs/05` and `docs/08`. These parts are still open for the final build: the registration method, and recessed mounts that have to coexist with hollowing and the 4 mm base slab. Perimeter tiles aren't rectangular, so each perimeter tile needs its own key and mount treatment.

---

## 16. Slice and print (Bambu Studio, X1 Carbon)

Measured on pilot plates (DECISIONS 2026-08-25):

- **`0.12 mm Fine` on the 0.4 nozzle** is the best-value profile: +28 min per plate over 0.20 Standard, with a contour interval of 5.4 m instead of 9.1 m, and the lowest filament use of any profile tested.
- The 0.2 nozzle is dominated on this geometry. It only buys XY resolution and adds ~1.5× time at the same layer height.
- Solid infill under the sloped top shell is 34–44% of tile mass. The top-shell layer count is the biggest untouched material lever.
- Gang 6 + 4 tiles across two plates rather than 2 × 6, which saves ~40 min of prepare time.
- AMS is reserved for **Z bands**. Roads are **engraved** (`--road-mask`, `--engrave-mm 0.35`) and paint-filled.

Before each print, add its row to `csv/tiles.csv` with the estimated hours and grams. After it finishes, fill in the actual values, and log each spool in `csv/filament_log.csv`. Run the coupons in `csv/test_prints.csv` (`HOLLOW-4` and `HOLLOW-6` first) before committing to a final-wall strategy.

---

## 17. Scaling up to the final wall

1. Settle the wall size, then update the constants in `topo_params.py` and run `plan`.
2. Rebuild the boundary at the **final** scale (step 6). The pilot polygon is under-detailed for a larger print.
3. Recompute the resample target (step 9). At 1:20,833, a 10 m DEM gives only ~2 samples per mm, so get a finer source: USGS National Map 1 m (public, no gate) or DOGAMI.
4. Re-derive the true relief, choose the exaggeration again, and re-run steps 10–16.
5. Add a dated entry to `docs/DECISIONS.md`, and flag any tile already printed at the old parameters.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Tile prints as a flat sheet | texture is 0×0, UV layer missing, or path is relative | Use PNG heightmaps, check the per-stage report, and pack the images |
| Flats look too flat, hills look fine | heightmap decoded as sRGB | Set `colorspace_settings.name = "Non-Color"` |
| Boolean returns empty | inverted prism, or self-intersecting terrain | Check the prism's signed volume, never Solidify, and run `boolean_probe.py` |
| Flat plateau on the highest hill | `ELEV_MAX_M` below the real max | Re-derive it from the masked DEM (step 8) |
| Ridge or gutter at tile joints | per-tile normalisation, or no shared edge | Never use `--auto-range`, and keep `--overlap-px 1` |
| Map ~3.3× too tall | DEM in feet | Convert to metres before scaling |
| `gdalwarp -tr 15.4` produces nonsense | raster still in degrees | Reproject first (step 4) |
| Boundary layer renders in the wrong place | GeoJSON missing its `crs` member, or a stale QGIS layer | Write the `crs` member, then remove and re-add the layer |
| HTTP 401 from OpenTopography | 1 m tier is gated | Use `USGS10m` |

---

## Document map

| Doc | Covers |
|---|---|
| `00-project-spec.md` | Goals, constraints, phase model |
| `01-scale-and-geometry.md` | Scale, grid and exaggeration tables (generated) |
| `02-data-sources.md` | DEM and vector sources, endpoints, field domains |
| `03-qgis-workflow.md` | Raster preparation in QGIS |
| `04-blender-workflow.md` | Displace, skirt, boolean |
| `05-fusion360-workflow.md` | Base, ribs, registration |
| `06-slicer-and-print.md` | Bambu Studio settings |
| `07-roads-and-color.md` | Engraving, paint fill, AMS banding, colour-cost model |
| `08-assembly-and-mounting.md` | Wall assembly |
| `09-pilot-run.md` | Pilot scope and test ladder |
| `10-hollow-base-strategies.md` | Hollow-base model and per-tile strategy |
| `11-pilot-runsheet.md` | Step-by-step pilot data preparation, with every measured value |
| `DECISIONS.md` | Dated decision log, newest first |
| `OPEN-QUESTIONS.md` | What's still undecided |
| `SOURCES.md` | Dataset provenance and attribution |
