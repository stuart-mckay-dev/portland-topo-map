# 11 — Pilot Run-Sheet: Data → Prepared Heightmaps

A single self-contained sheet for the front half of the pilot: acquire the DEM,
set QGIS up, clean it, cut it to a boundary, and export prepared per-tile
heightmaps. It ends where `docs/04-blender-workflow.md` begins.

Scope: **steps 1–11 below produce everything Blender needs except the Z-scale
value.** Z-scale is chosen visually (see step 12) and is deliberately the last
thing decided.

Working config for this sheet — pilot, 4×3 grid, 90 mm tiles:

```
$ python3 scripts/topo_params.py plan --tile-mm 90 --cols 4 --rows 3 --label "PILOT 4x3 @ 90mm"

  Grid                4 cols x 3 rows = 12 tiles
  Finished wall       313 x 270 mm   (12.3" x 10.6")
  Tile footprint      78.3 x 90.0 mm   (aspect 0.870)
  Ground per tile     7.25 x 8.33 km
  Horizontal scale    1 : 92,593
  1 mm of model       = 92.6 m of ground
  True (1x) relief    3.91 mm for the full 362 m range
  Base slab           4.0 mm under the lowest point
```

---

## 0 — Read this before you start

### 0a. The boundary cut is a change to a recorded decision

`docs/02-data-sources.md` currently says the project uses the rectangular bbox
**and not** the boundary polygon: *"the map will include unincorporated pockets
and slices of neighbouring cities. This is intentional — terrain does not stop
at a jurisdiction line."*

Cutting to a boundary reverses that. It is a legitimate choice — a
silhouette map reads as *Portland* in a way a rectangle does not — but it has
four consequences, and all four are cheaper to face now than after slicing:

1. **Edge tiles stop being rectangles.** Registration keys, the 4 mm base
   slab edge and the mounting scheme in `docs/08` all assume a rectangular
   tile with a vertical skirt. Perimeter tiles will need per-tile treatment.
2. **Some tiles come out nearly empty.** At a 4×3 pilot grid the corner tiles
   may contain very little material. Check the grid against the boundary
   (step 8f) before slicing anything.
3. **The boundary has holes and islands.** Portland's city limits enclose
   at least one full enclave (Maywood Park) plus unincorporated pockets. A
   literal boolean cut puts real holes in the middle of the map.
   **DECIDED 2026-08-24: dissolve them out.**
4. **The outline must be simplified or it prints as noise.** See 0c.

Record whatever you choose in `docs/DECISIONS.md` with a date.

### 0b. "Metro boundary" is ambiguous, and the two readings are very different

| Candidate | Layer | True ground extent | Area | vs. project bbox |
|---|---|---|---|---|
| **Portland city limits** | Metro `BoundaryDataWebMerc` layer **0**, `CITYNAME='Portland'` | 28.58 × 24.60 km | 697 km² | ≈ same (+2% wide) |
| **Metro UGB** | Metro `BoundaryDataWebMerc` layer **6** | 61.4 × 41.4 km | 2,538 km² | **3.7× the area** |
| **Metro district** | Metro `BoundaryDataWebMerc` layer **3** | larger still | — | — |
| *(project bbox, resized 2026-08-24)* | `docs/00-project-spec.md` | 29.00 × 25.00 km | 725 km² | — |

The **city limits** essentially *are* the existing bbox — the project bbox was
clearly derived from them. Choosing this changes nothing upstream. Note the
city is 566 m wider than the bbox, so the current rectangle clips a thin sliver
of the real city limits; widen the bbox by ~600 m if you want the whole thing.

The **UGB** is a different project. It is 2.2× wider, so at any given wall
width the scale denominator more than doubles and detail halves. It also
reaches into terrain the current constants do not cover — `ELEV_MAX_M = 362.0`
in `topo_params.py` and `qgis_export_tiles.py` is the West Hills high point and
would be **wrong**, silently compressing the whole map. If you go this way,
every constant in `topo_params.py` must be re-derived first.

> **DECIDED 2026-08-24 — city limits.** Metro layer 0, `CITYNAME='Portland'`.
> Not the UGB. See `docs/DECISIONS.md`.

### 0b-bis. The current bbox clips the city on two sides — fix before downloading

Exact city-limits extent in EPSG:32610 is **28,578.6 x 24,602.4 m**, and it does
not sit where the bbox sits. `fetch_dem.py` centres on downtown, which puts the
city 2,244 m outside the bbox on the **east** and 3,036 m outside on the
**north**:

```
current bbox   X 511,183.8 .. 539,053.8    Y 5,027,890.6 .. 5,052,580.6
city limits    X 512,719.7 .. 541,298.3    Y 5,031,014.4 .. 5,055,616.9
```

Against a rectangular map this was only a framing choice. Against a boundary
cut the silhouette gets sliced flat along its north and east edges — exactly
where the shape is most recognisable.

**Fix:** recentre on the city-limits centroid (X 527,009.0, Y 5,043,315.6) and
size the bbox to **29,000 x 25,000 m**. In WGS84 that centre is approximately
**45.5401 N, -122.4358 W** — verify in QGIS rather than trusting this line.

This changes `BBOX_W_M` / `BBOX_H_M` in `topo_params.py`, so every derived table
in `docs/01` and `docs/09` must be regenerated. Pilot impact is small
(1:92,593 -> 1:92,593, wall 305 x 270 -> 313 x 270 mm). Final impact is a happy
one: aspect goes 1.1288 -> 1.1600 and the squarest grid becomes **7x6**, which
is already the grid `docs/01` recommends for buying relief with wall area
instead of exaggeration.

See the OPEN entry in `docs/DECISIONS.md`.

### 0c. Masking and the boolean cut are two different operations

They happen in two different programs and it matters that you do not confuse
them:

- **Masking** is a *raster* operation, in QGIS. It sets everything outside the
  boundary to nodata. It does **not** create a cut edge — nodata normalises to
  0, which in Blender displaces to the top of the base slab, giving a flat
  apron around the terrain, not a wall.
- **The boolean cut** is a *mesh* operation, in Blender or Fusion 360, using a
  prism extruded from the boundary polygon. This is what actually produces the
  vertical silhouette edge.

You want both: mask so the terrain outside the line does not distort the
normalisation, then boolean so the plastic actually stops at the line.

`docs/04` says "displace, no booleans" — that guidance is specifically about
*road engraving*, where thousands of road solids would be catastrophic. One
boundary prism per tile is cheap and robust. It is not the case the doc warns
about.

### 0d. Simplify the outline to the scale you are printing

At the pilot's 1:92,593, one printed millimetre is 92.6 m of ground:

| | pilot 1:92,593 | final 5×4 1:31,250 |
|---|---|---|
| 0.4 mm printed | 37.0 m | 12.5 m |
| 0.5 mm printed | 46.3 m | 15.6 m |
| 1.0 mm printed | 92.6 m | 31.3 m |

Portland's city limits jog by far less than 36 m in places — parcel-level
staircases along annexation lines. Cut to the raw polygon and those become
sub-extrusion-width noise that the slicer renders as ragged garbage.

Plain Douglas-Peucker is the wrong tool here — it thins a staircase rather
than straightening it. **§8d has the method**: morphological open+close, then
Chaikin corner-cutting, with the deviation measured in printed millimetres.
Do not reuse the pilot's smoothed polygon at final scale.

---

## 1 — Software setup

- [ ] **QGIS** 3.34 LTR or newer. Everything below uses bundled GDAL — no
      plugins required. (SAGA only if you want the optional gaussian in step 9.)
- [ ] **Python** for the project scripts. `topo_params.py` is stdlib-only, but
      `qgis_export_tiles.py`, `dem_stats.py` and `tile_heights.py` need
      `numpy` + `rasterio`:

```bash
cd ~/Documents/PortlandTopo
python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt
```

  QGIS ships its own Python with rasterio-equivalents available; if you would
  rather not manage a venv, run those scripts from the QGIS Python console
  instead.

- [ ] **Blender** 4.2+ with the 3D-Print Toolbox add-on enabled (needed at
      step 11b onward). On macOS the binary is **inside the .app bundle and not
      on `PATH`** — `blender` alone gives `command not found`:

```bash
ls -d /Applications/Blender*.app ~/Applications/Blender*.app 2>/dev/null
echo 'alias blender="/Applications/Blender.app/Contents/MacOS/Blender"' >> ~/.zshrc
source ~/.zshrc && blender --version
```
- [ ] Confirm `data/` does not exist yet — it is gitignored and regenerated:

```bash
ls ~/Documents/PortlandTopo/data 2>/dev/null || echo "clean start"
mkdir -p data/raw data/derived data/heightmaps data/vectors
```

---

## 2 — Acquire the DEM

Source: **USGS 3DEP via OpenTopography**, `opentopoID OTNED.012021.4269.3`,
1 m bare-earth, NAVD88 metres, delivered in UTM 10N (EPSG:32610).

> **Do §0b-bis first.** Downloading against the un-recentred bbox means
> downloading the wrong rectangle.

- [ ] Key: nothing to do. `fetch_dem.py` reads
      `OpenTopography_API_Key.txt` from the repo root automatically. To
      override, `export OPENTOPO_API_KEY=...` or pass `--api-key`.

- [ ] **Dry-run first.** This prints the bbox and the download size without
      transferring anything:

```bash
python3 scripts/fetch_dem.py --dry-run
```

  Expect roughly 709 km², ~709 Mpx, ~2.8 GB uncompressed float32.

### 2a — Smoke-test the key on a 4 km box FIRST

Do not make the full download the thing that discovers your key is wrong. This
box spans Council Crest down to the Willamette — high ground and river in one
crop, so it validates the key, the endpoint and the vertical units in about
under a megabyte and a few seconds.

```bash
python3 scripts/fetch_dem.py --dataset USGS10m \
    --south 45.487034 --north 45.522966 \
    --west -122.715635 --east -122.664365 \
    --out data/raw/smoke_westhills.tif

python3 scripts/dem_stats.py data/raw/smoke_westhills.tif
```

- [ ] **Max reads roughly 320–330 m** (Council Crest is ~327 m) and **min reads
      near 0–3 m** (the Willamette). That is metres. Proceed.
- [ ] **Max reads roughly 1,050–1,090** → international feet. See step 3.
- [ ] Anything else — an HTML error page, a 401, a zero-byte file — is a key or
      endpoint problem, and you have found it cheaply.

#### If you get HTTP 401

The endpoint and parameter names are correct as written (`API/usgsdem`,
`datasetName`, `API_Key` with that exact capitalisation — verified against
OpenTopography's own 3DEP announcement). A 401 therefore means the key value
was rejected, and there are two different reasons for that. This tells them
apart:

```bash
python3 scripts/fetch_dem.py --check-key
```

It fires two tiny probes with the same key — one at the **global** collection
(`API/globaldem`, SRTMGL3) and one at the **3DEP** collection
(`API/usgsdem`, USGS30m) — and prints the server's own error text.

| Result | Meaning | Fix |
|---|---|---|
| both 401/403 | Key is wrong, inactive, or was regenerated | Fresh key from [myOpenTopo](https://portal.opentopography.org/myopentopo) |
| global 200, 3DEP 401/403 | Key is fine; the account lacks 3DEP entitlement | Request USGS 3DEP access on the same page |
| both 200 | Key is fine; the failure was elsewhere | Re-check the bbox flags for a typo |

The key is read automatically from `OpenTopography_API_Key.txt` at the repo
root; a label line above the token is fine. `$OPENTOPO_API_KEY` and
`--api-key` still override it. That file is now gitignored — check it stayed
that way before your first commit.

- [ ] Download the pilot DEM at 10 m:

```bash
python3 scripts/fetch_dem.py --dataset USGS10m \
    --out data/raw/portland_3dep_10m.tif
```

  ~747 km² at 10 m is ~7.5 Mpx, roughly 30 MB. Seconds, not an afternoon.

### If the request is rejected for size

Unlikely at 10 m (~30 MB), but OpenTopography does cap single-request area.
Split into quadrants and merge. Get the four sub-bboxes from the dry-run
output's S/N/W/E and halve them:

```bash
python3 scripts/fetch_dem.py --south <S> --north <MIDLAT> --west <W> --east <MIDLON> \
    --out data/raw/q_sw.tif
# ...repeat for se, nw, ne...
gdal_merge.py -o data/raw/portland_3dep_10m.tif -n -9999 -a_nodata -9999 \
    data/raw/q_*.tif
```

### DECIDED 2026-08-24 — the pilot runs on 10 m

`USGS1m` returns **HTTP 401** for a free account. Not a bad key —
OpenTopography restricts the 1 m tier to *.edu* institutions, educators and
OpenTopography+ members. `USGS10m` and `USGS30m` work with the same key.

This costs the pilot nothing. See the sampling table in `docs/02`: at
1:92,593 a 10 m DEM gives **9.3 samples per printed mm** against a 4–8 target,
and the finest feature a 0.4 mm extrusion can render is 37 m of ground. 1 m
would have been ~93× finer than anything printable.

### If you ever need better than 10 m

Only the **7×6** final configuration genuinely does — 2.1 samples/mm against an
8.3 m printable floor. Two free routes, neither behind OpenTopography's gate:

- **USGS The National Map** — 3DEP is public domain and USGS distributes the
  1 m tiles itself. <https://apps.nationalmap.gov/downloader/>
- **DOGAMI / Oregon Lidar Consortium** — ships by 7.5-minute quadrangle, often
  crisper in the West Hills. **Check the units** — some Oregon deliverables are
  in international feet.

Neither is needed for the pilot.

---

## 3 — Verify the vertical units. Do not skip this.

The single most expensive mistake available in this project. A feet/metres
mix-up is a silent 3.2808× exaggeration error that looks entirely plausible
until it is printed.

```bash
python3 scripts/dem_stats.py data/raw/portland_3dep_10m.tif
```

- [ ] **Max reads ~362** → metres. Correct, continue.
- [ ] **Max reads ~1188** → international feet. Convert before anything else:

```bash
gdal_calc.py -A data/raw/portland_3dep_10m.tif --outfile=data/raw/portland_m.tif \
    --calc="A*0.3048" --NoDataValue=-9999
```

- [ ] Also note the **mean elevation fraction** `dem_stats.py` reports. It
      set `MEAN_ELEV_FRACTION` in `topo_params.py`. **Done 2026-08-24:
      0.1958.**

---

## 4 — QGIS project setup

- [ ] New project. **Project → Properties → CRS → EPSG:32610** (WGS84 / UTM
      zone 10N, metres).

  > **Corrected 2026-08-24.** An earlier revision of this sheet preferred
  > 32610 on the grounds that OpenTopography delivers it natively and the
  > raster would never be warped. That was wrong — 3DEP comes back as
  > **EPSG:4269, geographic, in degrees**. A reprojection is mandatory either
  > way, so the choice is now on merits alone.
  >
  > 32610 stays the pick, for a duller reason: the recorded bbox centroid and
  > the city-limits extent in `docs/DECISIONS.md` are already expressed in it.
  > EPSG:6559 (NAD83(2011) / Oregon North) is equally defensible and avoids a
  > NAD83→WGS84 datum shift — but that shift is ~1–2 m, which is 0.05 mm at
  > the final's 1:31,250 and invisible. Not worth restating the coordinates.
  >
  > Never EPSG:4326 for anything dimensional.

- [ ] **Project → Properties → General → Save paths: Relative.**
- [ ] Save as `PortlandTopo.qgz` at the project root.
- [ ] Turn **off** "Render layers in parallel" if QGIS gets sluggish with the
      1 m raster loaded.

### 4a — Load the layers and look at them

**GeoJSON CRS trap.** The GeoJSON spec defaults to WGS84 lat/lon, and RFC 7946
removed the `crs` member outright — but GDAL and QGIS still honour the legacy
one. Measured 2026-08-24:

- The **ArcGIS** download *does* carry it:
  `"crs":{"type":"name","properties":{"name":"EPSG:32610"}}`. It loads fine.
- `smooth_boundary.py` originally wrote **none**, so QGIS read projected metres
  as degrees, tried to plot longitude 512,000, and the layer rendered nowhere —
  present in the layer list, invisible on the map. **Fixed:** the script now
  writes a FeatureCollection and carries the input's `crs` member through, with
  `--crs EPSG:32610` to override.

- [ ] After adding each vector, check the CRS in the layer list. If it is not
      EPSG:32610: right-click → **Set CRS → Set Layer CRS…** → EPSG:32610.
      Do **not** use "Reproject" — the coordinates are already correct, only
      the label is wrong.
- [ ] Symptom: the layer is listed and ticked but nothing draws, and
      *Zoom to Layer* sends you somewhere absurd.
- [ ] **Rewriting the file does not fix an open layer.** QGIS stamps the CRS
      when it first loads the source and keeps it in the project. After
      regenerating a GeoJSON, right-click the layer → **Remove Layer**, then
      add it again. Re-running the script alone changes nothing on screen.

**Load order — bottom to top:**

1. **Layer → Add Layer → Add Raster Layer…** (`Ctrl+Shift+R`) →
   `data/derived/dem_32610.tif`
2. **Layer → Add Layer → Add Vector Layer…** (`Ctrl+Shift+V`) →
   `data/vectors/portland_city_limits.geojson`
3. Same again → `data/vectors/boundary_smoothed.geojson`

**Make the DEM readable.** Double-click it → **Symbology**:

- [ ] Render type → **Hillshade**. Azimuth 315, altitude 45. This is the
      fastest way to see whether the terrain looks like Portland.
- [ ] Or Render type → **Singleband pseudocolor**, Min 0 / Max 391, ramp
      *Viridis* or *Terrain*, to read elevation numerically.
- [ ] Best of both: duplicate the DEM layer, hillshade on top of pseudocolor,
      and set the top layer's **Layer Rendering → Opacity** to ~50%.

**Make the two boundaries comparable.** Double-click each → **Symbology** →
Simple Fill:

| Layer | Fill style | Stroke | Width |
|---|---|---|---|
| `portland_city_limits` (original) | **No Brush** | red | 0.26 mm |
| `boundary_smoothed` | **No Brush** | blue | 0.6 mm |

If the layer swatch in the legend is a **solid** colour, the fill is still on —
set *Fill style* to **No Brush** or the smoothed polygon will cover the DEM.

Outlines only, so you can see one through the other. Put the smoothed layer
**above** the original.

**Set the scale — this is the part that matters.**

- [ ] In the status bar at the bottom, type **92593** into the *Scale* box and
      press Enter. Judge nothing until you have.
- [ ] Sanity-check it: the whole city should span roughly **12.3 inches** on
      screen. If it does not, QGIS is using a monitor DPI that does not match
      your display — **Settings → Options → Map Tools → Rendering** — and every
      "can I see this?" judgement will be wrong until it does.

**Where to look**, in order:

- [ ] **West / south-west** (Cedar Mill, West Slope, Raleigh Hills) — the
      narrow-finger fringe. This is where D does damage.
- [ ] **North-east near the Columbia**, around **45.5767–45.5976 N,
      −122.547 W** — the 25 mm limb that falls off at D ≥ 75. Confirm it is
      still attached.
- [ ] **The two detached islands** the D=50 run created: 165 × 464 m
      (1.8 × 5.0 mm printed) and 111 × 109 m (1.2 × 1.2 mm). Decide whether
      they belong in the map. Drop them with `--min-part-mm2 30` if not.
- [ ] **South** toward Metzger — the comb of teeth. Did they straighten?
- [ ] **NW Linnton diagonal** — should still be straight. If it developed a
      wobble, Chaikin is over-applied.

- [ ] Save the project as `PortlandTopo.qgz` at the project root.

### 4b — Choose the vertical exaggeration in the 3D view

This is the render you wanted, and QGIS gives you the number directly: the 3D
view's **vertical scale is exactly the project's exaggeration multiplier.**
Both are "multiply Z by N against unchanged horizontal distance". Whatever
looks right on that slider is the value the rest of the pipeline needs.

- [ ] **View → 3D Map Views → New 3D Map View**
- [ ] Set the terrain:
      - **QGIS 3.28 and newer:** *Project → Properties → Terrain* → Terrain
        type **DEM**, Raster layer `dem_32610.tif`, **Vertical scale** = N.
      - **Older:** the wrench/Configure button inside the 3D view → *Terrain*.
- [ ] Try **2, 3, 4, 6, 8**. Note where it stops reading as terrain and starts
      reading as sculpture.
- [ ] Light it from a low angle. Flat-lit terrain always looks flatter than it
      prints, and Portland's eastside is mostly flats.

Two honest caveats before you commit to a number from this:

1. **A screen render has infinite Z resolution; the printer has 0.2 mm layers.**
   Terracing is worst on shallow slopes, and exaggeration is what fixes it —
   which is a reason to land *higher* than the render suggests. `docs/09`
   specifies printed coupons for exactly this reason.
2. **Exaggeration is a budget.** Quote the cost alongside the look —
   `python3 scripts/topo_params.py plan --tile-mm 90 --cols 4 --rows 3` prints
   grams and hours per exaggeration step.

- [ ] Hand the chosen N over, or convert it yourself:
      `python3 scripts/topo_params.py plan --tile-mm 90 --cols 4 --rows 3 --target-height-mm <N>`
- [ ] Record it in `docs/DECISIONS.md` with the date and the reasoning.

### Create the bbox layer

Everything downstream clips to exactly this rectangle. If it drifts, tile
boundaries drift and `topo_params.py` no longer describes reality.

- [ ] Layer → Create Layer → New Temporary Scratch Layer, Polygon, EPSG:32610.
- [ ] Draw or, better, compute it — take the DEM's centre and build a
      29,000 × 25,000 m rectangle around it so it is exact rather than
      hand-drawn. Centre it on EPSG:32610 **E 527,009.0, N 5,043,315.6** — the
      city-limits extent centroid, not downtown.
- [ ] Export → Save Features As → GeoPackage → `data/derived/bbox.gpkg`.

---

## 5 — Import and mosaic

- [ ] Layer → Add Layer → Add Raster Layer → `data/raw/portland_3dep_10m.tif`.
- [ ] If it arrived as multiple files: **Raster → Miscellaneous → Merge**.
      Confirm output is single-band **Float32** with nodata set.
### 5b — Reproject. Before anything measured in metres.

**This step is not optional and it must come first.** The download is in
degrees. `gdalwarp -tr 15.4 15.4` on a degrees raster asks for 15.4-degree
pixels, and a buffer in degrees is meaningless. Everything downstream —
resample, water mask, boundary buffer, tiling — assumes metres.

```bash
gdalwarp -s_srs EPSG:4269 -t_srs EPSG:32610 -r bilinear -tr 10 10 \
    -of GTiff data/raw/portland_3dep_10m.tif \
    data/derived/dem_32610.tif
```

- [ ] Confirm the output CRS and that pixel size now reads in **metres**:

```bash
python3 scripts/dem_stats.py data/derived/dem_32610.tif
```

  `dem_stats.py` prints a `[!] GEOGRAPHIC CRS` warning if you skipped this.

- [ ] `-tr 10 10` makes the pixels **square**. The download is 1/3 arc-second,
      which at Portland's latitude is 0.000093° in both axes but **7.2 m in x
      and 10.3 m in y** — degrees of longitude are shorter than degrees of
      latitude here. Square metres from this point on.
- [ ] Use `-r bilinear` here, not `average`. This reprojection is a
      resampling of convenience; the deliberate downsample to print resolution
      happens once, in step 9, with `-r average`. Averaging twice smears
      ridgelines.
- [ ] Every later step reads `dem_32610.tif`, not the raw download.

---

## 6 — Fill voids — **a no-op on the 10 m product; verify and skip**

Bare-earth classification leaves holes where structures were removed — but the
3DEP 1/3 arc-second product is delivered void-filled. Measured 2026-08-24 on
this download: **10,035,872 valid cells out of a 4,073 x 2,464 grid — zero
nodata.** (`dem_stats.py` prints a "% filled" figure; the raw download reads
100.0%.)

- [ ] Confirm 100% filled, then skip to step 7. Do not run Fill nodata on a
      raster that has nothing to fill — it costs time and resamples for free.
- [ ] The reprojected `dem_32610.tif` shows ~63,500 nodata cells (0.8%), but
      those are the corner wedges left by rotating the grid into UTM. They sit
      outside the city boundary and the mask removes them.

If you later switch to a 1 m source, re-check — 1 m tiles are **not**
guaranteed void-free.

- [ ] Input: `data/derived/dem_32610.tif`
- [ ] **Processing → GDAL → Raster analysis → Fill nodata**
- [ ] Max search distance: **10** pixels
- [ ] Smoothing iterations: 0
- [ ] Output → `data/derived/dem_filled.tif`

---

## 7 — Flatten water

Lidar returns off water are noisy and print as a visibly rippled river — one of
the most obvious tells of an unprocessed relief map.

- [ ] Pull hydrography polygons (PortlandMaps or NHD; see `docs/02`) into
      `data/vectors/`.
- [ ] Reproject to EPSG:32610.
- [ ] **Raster → Conversion → Rasterize** the water polygons onto the same grid
      as `dem_filled.tif` (set "Output extent" and pixel size from the DEM), a
      burn value of 1, everything else 0 → `data/derived/mask_water.tif`.
- [ ] **Raster calculator** to force those cells flat. Use the **measured**
      values, not the docs' round numbers. Value-frequency analysis of this
      DEM found water already partly flattened, in patches, at inconsistent
      levels: **Columbia ≈ 1.90 m** (~24 km² at 1.90/1.91) and **Willamette
      ≈ 2.86–2.98 m**. Note that is 1.90, not the 0.19 in `topo_params.py` —
      see `docs/DECISIONS.md`.

      Do them as **two separate masks**. Forcing both rivers to one constant
      puts a visible ~1 m step where they meet at Kelley Point.

      9.46% of the DEM sits below 5 m and that low ground carries 387 distinct
      values, so the pre-flattening is partial. Step 7 is still required.

```bash
gdal_calc.py -A data/derived/dem_filled.tif -B data/derived/mask_water.tif \
    --outfile=data/derived/dem_flat.tif \
    --calc="where(B==1, 2.90, A)" --NoDataValue=-9999
# and again for the Columbia mask at 1.90
```

- [ ] `ELEV_MIN_M` is set at **step 8h**, from the masked DEM — not here.
      When you set it, change it in **both** `topo_params.py` and
      `qgis_export_tiles.py`; they are duplicated and must not drift.

---

## 8 — Boundary mask

> **Order matters.** Mask **after** cleaning but **before** normalisation, and
> **before** the resample in step 9 only if you buffer first — see 8e. A
> gaussian or averaging kernel that straddles a nodata edge pulls the terrain
> down near the boundary, producing a false rim exactly where the eye will look.

### 8a — Fetch the boundary

Metro's `BoundaryDataWebMerc` service, layer **0** (`City Limits`, field
`CITYNAME`). Native SR is Web Mercator (EPSG:3857).

```bash
curl -o data/vectors/portland_city_limits.geojson \
  "https://gis.oregonmetro.gov/arcgis/rest/services/OpenData/BoundaryDataWebMerc/MapServer/0/query?where=CITYNAME%3D%27Portland%27&outFields=*&outSR=4326&f=geojson"
```

  Alternative source: PortlandMaps `COP_OpenData_Boundary` layer **10**
  (`City Boundaries`). For the UGB instead, use Metro layer **6** — but read
  §0b first.

### 8b — Reproject to the working CRS. Before anything geometric.

- [ ] **Vector → Data Management Tools → Reproject Layer** → EPSG:32610.
- [ ] Save as `data/vectors/boundary_32610.gpkg`.

  Buffering or simplifying in Web Mercator at Portland's latitude
  overestimates distances by ~43% (1/cos 45.5°). Reproject first, always.

### 8c — Dissolve, and decide about the holes

- [ ] **Vector → Geoprocessing Tools → Dissolve** (no field) → one feature.
- [ ] Inspect for interior rings. Zoom to the NE — Maywood Park is a complete
      enclave. There are also unincorporated pockets.
- [ ] **Processing → Vector geometry → Delete holes.** Decided 2026-08-24:
      dissolve them all out. Set the minimum-area threshold to 0 so nothing
      survives, then confirm visually that the polygon has no interior rings
      left — the layer should report a single ring in its geometry.

### 8d — Regularise the outline to print scale

**Do not use Simplify on its own.** Douglas-Peucker (QGIS "Simplify") only
*deletes* vertices. Portland's western, southern and south-eastern limits
staircase along PLSS section lines and annexation seams — a directional
zig-zag. Delete vertices from a staircase and you get a staircase with fewer,
bigger steps. You never get the smooth directional line the eye reads as
"the edge of the city".

Three operations in order do get you there:

1. **Morphological open + close** at radius `D`.
   `close = buffer(+D).buffer(-D)` fills notches narrower than `2D`;
   `open = buffer(-D).buffer(+D)` shaves spurs narrower than `2D`.
   This removes features by **size**, which is the principled way to say
   "anything below print resolution goes". Doing both directions is what keeps
   it from systematically inflating or shrinking the polygon.
2. **Chaikin corner-cutting.** Each iteration replaces every vertex with two
   points at ¼ and ¾ along its adjacent segments; the limit curve is a
   quadratic B-spline. Run against a staircase it converges on the staircase's
   **mean path** — the "line of best fit through the zig-zag", arrived at
   geometrically instead of by regression.
3. **Douglas-Peucker last, and light**, purely to drop the redundant vertices
   that 1 and 2 introduce.

#### On R² and lines of best fit

R² measures how well a line explains points where *y is a function of x*. A
closed boundary is not a function — it doubles back on itself, and Portland's
western limit runs nearly north–south, where a y-on-x fit is degenerate. The
honest analogues, both reported by the script below:

| Metric | Meaning | Analogous to |
|---|---|---|
| **Hausdorff distance** | worst-case displacement anywhere on the outline | max residual |
| **Mean displacement** | symmetric-difference area ÷ original perimeter | RMSE |
| **Area retained** | guards against the smoother quietly eating the city | — |

Both distances are reported in **printed millimetres at your scale**, which is
the number that decides whether a deviation is visible at all. One extrusion
width is 0.4 mm; below that it cannot be printed, let alone seen.

#### Run the sweep

```bash
pip install shapely
python3 scripts/smooth_boundary.py \
    --in  data/vectors/boundary_32610.geojson \
    --scale 92593 --sweep
```

- [ ] Read **AMPUTATE** first — it is the irreversible column. Watch for the
      `<-- CLIFF` flag.

**Measured result, 2026-08-24 — use `D = 50`, and never `D >= 75`:**

```
 D(m)  D(mm)  pts  verts  AMPUTATE m     mm  INTRUDE m     mm    lost    gain
    0   0.00    1  1,099          42   0.45         38   0.41   0.181   0.221
   25   0.27    4  1,014         195   2.10         22   0.24   0.271   0.305
   50   0.54    3    954         235   2.53         48   0.52   0.380   0.671
   75   0.81    2    871       1,571  16.96         57   0.61   0.784   1.006  <-- CLIFF
  100   1.08    1    798       1,571  16.96         90   0.98   0.830   1.591
```

Amputation jumps **6.7× for a 1.5× change in D** between 50 and 75. A narrow
neck is severed and a **0.2793 km² limb — 659 × 2,316 m, or 7.1 × 25.0 mm
printed** — falls off, at 45.5767–45.5976 N, −122.547 W in the north-east near
the Columbia. That is a 25 mm limb on a 313 mm map.

- [ ] If `D = 50` does not straighten the zig-zag enough, **raise `--chaikin`,
      not `D`**. Chaikin is corner-cutting, not a size filter — it cannot
      amputate a limb. `D` is the only knob that deletes material.
- [ ] Commit and write the file:

```bash
python3 scripts/smooth_boundary.py \
    --in  data/vectors/boundary_32610.geojson \
    --out data/vectors/boundary_smoothed.geojson \
    --scale 92593 --d 50 --chaikin 2 --dp 10
```

- [ ] Load it over the original in QGIS at 1:92,593 and **look at it**. The
      metrics rank candidates; they do not pick one. Watch specifically:
      the western fringe around Cedar Mill and West Slope (the hard case), the
      southern teeth toward Metzger, the south-eastern spurs near Pleasant
      Valley, and the Linnton diagonal — which should come through straight.

#### 8d-bis — Spot edits: fixing five places without moving a global knob

After the D sweep there will be a handful of specific places that are still
wrong. **Do not raise D to fix them.** Portland's outline carries dozens of
bays and limbs of comparable size; a radius large enough to reach the one you
want takes many you were happy with. The D=50 result had five such spots
against an outline that was otherwise good.

`smooth_boundary.py --edit` names a point instead of a threshold. Three
actions, each a targeted morphological operation on the feature at that point:

| Action | What it does | Mechanism |
|---|---|---|
| `cut:E,N` | Removes the narrow-necked limb there | Opening bridges **straight across the neck** — which is exactly "cut it off and close it with a straight line" |
| `fill:E,N` | Seals the concave inlet there | Closing spans the mouth of the bay |
| `drop:E,N` | Deletes the detached island there | Part removal; the main body is protected |

Coordinates are in the working CRS (EPSG:32610). Repeat `--edit` per fix.
`--edit-radius` (default 400 m) is the **reach** — it must exceed half the neck
or mouth width to find the feature. It does not control how much is removed;
the feature's own extent does that.

**Getting the coordinates:** hover over the spot in QGIS and read the
**Coordinate** box in the status bar. Anywhere inside the feature works — the
tool takes the component containing the point, or the nearest one.

Example, the five fixes found on the D=50 pilot outline:

```bash
python3 scripts/smooth_boundary.py \
    --in  data/vectors/portland_city_limits.geojson \
    --out data/vectors/boundary_smoothed.geojson \
    --scale 92593 --d 50 --chaikin 2 --dp 10 \
    --edit "cut:535344,5048230" \
    --edit "drop:518819,5041261" \
    --edit "drop:540031,5036484" \
    --edit "fill:519080,5042530" \
    --edit "fill:525646,5032262"
```

That is the committed pilot boundary: **one part, 924 vertices, 376.441 km²**,
worst intrusion 1.13 mm printed, mean deviation 0.09 mm. The reported
amputation of 16.99 mm is the north peninsula, removed deliberately — the
metric cannot tell an intentional `cut` from an accidental one.

- [ ] Every edit prints what it actually removed or added, in km² **and in
      printed mm**. Read those before accepting the result — a `fill` that
      reports 14 × 15 mm when you meant a 4 mm notch has found the wrong bay,
      and the fix is a better coordinate, not a different radius.
- [ ] Edits run **after** smoothing, and the geometry is healed with
      `buffer(0)` afterwards to clear boolean slivers.
- [ ] The chosen edits are recorded in the output file's `properties.edits`,
      so the polygon carries its own provenance. Re-running is reproducible.

#### The four edges are not the same problem

From the council-district basemap, reading the **outer perimeter only**:

| Edge | Character | What it needs |
|---|---|---|
| **North / NE** | Follows the Columbia; limits run to the state line mid-river. Broadly clean, one rectilinear staircase near the airport. | Little. Watch that river area stays flat at 0.19 m (§7). |
| **NW (Linnton)** | A long, genuinely linear diagonal along the ridge above Hwy 30. | Nothing. Do not smooth away a real straight line. |
| **East (toward Gresham)** | Rectilinear staircase, steps of a few hundred metres. | Moderate `D`. These are section-scale and worth keeping. |
| **South** | Comb of small teeth toward Tigard/Metzger/Lake Oswego. | This is the zig-zag case. Open+close plus Chaikin. |
| **West / SW (Cedar Mill, West Slope, Raleigh Hills)** | **Not a zig-zag.** A fringe of long narrow fingers around unincorporated islands, plus detached parts. | The hard case — see below. |

#### The western fringe will lose material, not just detail

The west side is not a wiggly edge on a solid blob. It is a set of narrow
peninsulas of city reaching between unincorporated pockets. Morphological
opening at radius `D` **amputates anything thinner than `2D`**. That is often
what you want — a 60 m-wide finger is 0.65 mm at pilot scale and cannot carry
printed geometry — but it is material loss, not smoothing, and it deserves a
deliberate decision rather than being discovered in the slicer.

The script therefore reports, per `D`:

- **parts** — how many separate polygons survive. A jump downward means fingers
  or exclaves were severed.
- **lost km²** and **biggest** — total and largest-single area removed.
- **mean width** (`2 × area / perimeter`) for the input, in printed mm, so you
  know going in how much of the shape is thin.

- [ ] Watch those columns as hard as Hausdorff. A `D` with a beautiful
      Hausdorff number that quietly deletes 4 km² of west-side Portland is the
      wrong answer.
- [ ] Detached parts: by default they are **kept**. `--largest-only` drops all
      but the biggest and prints exactly what it discarded — never silently.

#### What to keep versus what to erase

Not every jog is noise. Portland's annexation lines follow the PLSS grid, and
a quarter-quarter section is ¼ mile ≈ **402 m** — at pilot scale that is
**4.3 mm**, a real, legible, characteristic step you almost certainly want.
Lot-line jogs of 30–120 m are **0.3–1.3 mm** and are noise.

So the target is not "smooth everything". It is: erase below ~100 m, keep the
section-scale steps. A `D` much above 200 m starts eating the character.

> The script defaults to dropping interior rings, matching the
> 2026-08-24 decision to dissolve the enclaves. Pass `--keep-holes` to
> override.

> **Rebuild this at final scale.** At 1:31,250 the same 0.4 mm is only 12.5 m
> of ground, so a much smaller `D` is justified and much more of the real
> staircase survives. Do not carry the pilot's polygon forward.

### 8e — Buffer for the smoothing kernel

Add `--buffer-out` to the same `smooth_boundary.py` run — no separate QGIS
step, and the buffered copy is guaranteed to match the polygon you committed:

```bash
    --buffer-out data/vectors/boundary_buffered.geojson --buffer-m 50
```

  This is the mask you use for the raster clip. The extra 50 m gives step 9's
  averaging kernel real data to chew on right up to the true line, and the
  boolean prism in step 12 trims back to the true line anyway. Skipping this is
  how you get a soft dip around the entire perimeter.

### 8f — Check the tile grid against the boundary before going further

- [ ] Overlay the 4×3 pilot grid on the boundary. Each cell is 6.97 × 8.23 km.
- [ ] Flag any tile that comes out nearly empty, and any tile whose remaining
      material is too thin to carry a registration key.
- [ ] If two or more tiles are junk, reconsider the grid — or the cut.

### 8g — Clip

- [ ] **Raster → Extraction → Clip Raster by Mask Layer**
- [ ] Input: `dem_flat.tif`  ·  Mask: `boundary_buffered.geojson`
- [ ] **Check** "Match the extent of the clipped raster to the extent of the
      mask layer" — *off*. You want the bbox extent preserved so the tile grid
      stays aligned to `topo_params.py`.
- [ ] Assign nodata: `-9999`
- [ ] Output → `data/derived/dem_masked.tif`

---

## 8h — Re-derive the elevation constants from the MASKED DEM

**Do this here, not earlier.** `ELEV_MIN_M`, `ELEV_MAX_M` and
`MEAN_ELEV_FRACTION` in `topo_params.py` describe *the printed object*, and the
printed object is the masked map — not the raw rectangle.

The raw 10 m bbox reads **min 0.958 m, max 391.123 m, mean_fraction 0.1922**
against constants of 0.19 / 362.0 / 0.17. The 391 m is real, broad terrain
(its 15×15 neighbourhood averages 383.9 m) at **45.52653, -122.75310** — the
Tualatin Mountains crest along the Skyline corridor north-west of downtown.
At 1,283 ft it is ~95 ft above Portland's cited high point of 1,188 ft, so it
is almost certainly **outside the city limits** and the mask should remove it.

Why it cannot be ignored: `qgis_export_tiles.py` normalises against
`ELEV_MAX_M` and **clips to [0,1]**. Every cell above the ceiling prints as a
flat plateau at full height. 2,009 cells (0.149 km²) exceed 362 m in the raw
bbox.

**Two masks, for two different purposes.** The working raster is cut with the
**+50 m buffered** polygon so the resampling kernel has real data at the rim.
But the constants describe the *printed object*, which ends at the **true**
line — so they must be read from an unbuffered mask. Measured 2026-08-24:

| cutline | filled | min | max | cells > 362 | mean_fraction |
|---|---|---|---|---|---|
| true boundary | 50.4% | 0.958 | **361.996** | **0** | **0.1965** |
| +50 m buffered | 51.4% | 0.958 | 368.859 | 53 | 0.1954 |

Read constants from the first row. The 53 cells above the ceiling in the
buffered version live in the buffer ring and are removed by the mesh boolean;
they would otherwise clip to a plateau.

```bash
# working raster -- buffered cutline
gdalwarp -cutline data/vectors/boundary_buffered.geojson -dstnodata -9999 \
    data/derived/dem_32610.tif data/derived/dem_masked.tif

# constants -- TRUE boundary, no buffer
gdalwarp -cutline data/vectors/boundary_smoothed.geojson -dstnodata -9999 \
    data/derived/dem_32610.tif data/derived/dem_stats_only.tif
python3 scripts/dem_stats.py data/derived/dem_stats_only.tif
```

> **`ELEV_MAX_M = 362.0` is confirmed correct.** The masked maximum is
> **361.996 m** with zero cells above it. The 391 m in the raw rectangle was
> the Tualatin Mountains crest outside the city, exactly as suspected. The
> constant needed no change — the raw-bbox reading was the misleading one.

> **`ELEV_MIN_M` waits for step 7.** The masked minimum is 0.958 m, but p0.1
> and p1.0 both read 1.900 — the bulk of the low ground is the water plane, and
> flattening will raise the tail to meet it. Set it after water, not now. The
> difference is 0.94 m on a 361 m range: 0.26%, about 0.02 mm at pilot scale,
> invisible either way.

> **`MEAN_ELEV_FRACTION = 0.1958`** replaces the 0.17 placeholder — **SET
> 2026-08-24**, measured on `dem_stats_only.tif`. (A pre-reprojection estimate
> gave 0.1965; bilinear resampling shaves the extremes, and the pipeline
> raster is the authority.) This is not cosmetic — it is ~15% on every mass
> and time figure in the project: the pilot goes 26 h → **27 h**, and the 5x4
> final at 6" goes **8.8 kg / 508 h → 9.8 kg / 562 h**.

- [ ] Confirm the max has dropped back near 362 m. If it has, the overshoot
      was outside the boundary and nothing needs changing.
- [ ] If it has **not**, the high ground is inside the city and `ELEV_MAX_M`
      is simply wrong. Set it to the real masked max and regenerate every
      derived table (`docs/01`, `docs/09`) — that is the `docs/00` "highest
      elevation" row too.
- [ ] Set `ELEV_MIN_M` from the masked min. Note the raw data floors at
      exactly 1.900 m across a large share of cells, which looks like a
      pre-flattened water surface rather than true bathymetry.
- [x] **DONE 2026-08-24.** `MEAN_ELEV_FRACTION = 0.1958`,
      `MEAN_ELEV_FRACTION_IS_ESTIMATE = False`. `docs/01` and `docs/09`
      regenerated from it.
- [ ] Keep `ELEV_MIN_M` / `ELEV_MAX_M` identical in `topo_params.py` **and**
      `qgis_export_tiles.py`. They are duplicated and must not drift.
- [ ] Log the before/after in `docs/DECISIONS.md`.

---

## 9 — Resample to print resolution

At 1:92,593 one model millimetre is 92.6 m of ground. Targeting 6 DEM samples
per printed millimetre:

```
target_ground_res_m = (scale_denominator / 1000) / samples_per_mm
                    = (92,593 / 1000) / 6
                    = 15.4 m
```

- [ ] Resample. `-r average` both downsamples and removes lidar speckle in one
      pass, which is why `docs/03` calls for bilinear or cubic averaging:

The source is already 10 m, so this is a mild 1.5x downsample rather than the
25x one the 1 m path would have needed. Still do it — it aligns the grid and
kills speckle.

```bash
gdalwarp -tr 15.4 15.4 -r average -of GTiff \
    data/derived/dem_masked.tif data/derived/portland_dem_smooth.tif
```

- [ ] Optional, only if speckle survives: SAGA → Gaussian Filter, radius 2.
- [ ] Sanity: the output should be roughly 1,883 × 1,623 px. If it is far off,
      the extent drifted somewhere upstream.

> For the **final** at 1:31,250 this is 5.2 m, not 15.4. Recompute — do not
> copy this number forward.

---

## 10 — Normalise and tile

`scripts/qgis_export_tiles.py` does both, and exists specifically to get the
two things right that are easy to get wrong:

- **Project-wide normalisation.** Against 0.19 m and 362.0 m, never per-tile
  min/max. Per-tile normalisation makes every tile use the full 16-bit range
  and the terrain stops lining up across seams.
- **Shared edge pixels.** One-pixel overlap so both tiles generate their
  boundary vertices from identical values. Independently cropped tiles produce
  a visible ridge or gutter at every joint.

```bash
python3 scripts/qgis_export_tiles.py \
    --dem data/derived/portland_dem_smooth.tif \
    --out data/heightmaps \
    --cols 4 --rows 3 --phase pilot
```

- [ ] Confirm it prints `project range: 0.19 -> 362.00 m` — **not** an auto
      range. Never pass `--auto-range` for real tiles.
- [ ] Confirm no `[!] This DEM may be in FEET` warning.
- [ ] Confirm 12 files land in `data/heightmaps/`, named
      `pdx_pilot_rNNcNN.tif`, row 1 = north, col 1 = west.
- [ ] Note the per-tile "% of range" column — it tells you which tile holds the
      West Hills peak. That is your coupon tile for the exaggeration ladder.

Then get the real per-tile heights:

```bash
python3 scripts/tile_heights.py
```

- [ ] Fill `z_height_mm` and `est_hours` into `csv/tiles.csv`. Every print gets
      a row before it starts, not after it finishes.

---

## 11 — Prepared-file export: what you should now have

```
data/raw/portland_3dep_10m.tif         raw download (10 m; 1 m is gated)
data/derived/bbox.gpkg                 the exact rectangle everything clips to
data/derived/dem_filled.tif            voids filled
data/derived/dem_flat.tif              water flattened
data/derived/dem_masked.tif            boundary-masked, still full resolution
data/derived/dem_32610.tif             reprojected to metres -- everything reads this
data/derived/portland_dem_smooth.tif   15.4 m, print resolution
data/heightmaps/pdx_pilot_rNNcNN.tif   12 × 16-bit heightmaps, shared edges
data/vectors/boundary_smoothed.geojson   the TRUE cut line for step 12
data/vectors/boundary_buffered.geojson    the +50 m raster mask
```

- [ ] No DXF or SVG export is needed. `scripts/boundary_prism.py` reads the
      GeoJSON directly and writes an aligned, watertight STL prism in model
      millimetres — see step 12.

- [ ] Record the actual download date, the exact API query and the layer IDs
      you used in `docs/SOURCES.md`.

---

## 11b — Preview in Blender and choose the exaggeration

The heightmaps carry no exaggeration at all — they are normalised 0–65535.
Exaggeration enters exactly once, as the Displace **Strength** in millimetres.
So the way to choose it is to leave that field live and scrub it.

```bash
python3 scripts/qgis_export_tiles.py --dem data/derived/dem_masked.tif \
    --out data/heightmaps --cols 1 --rows 1 --phase preview

blender -b -P scripts/blender_heightmap_to_mesh.py -- \
    --heightmaps data/heightmaps --pattern "pdx_preview_*.tif" \
    --out /tmp --tile-w 313 --tile-h 270 \
    --relief-mm 15.6 --subdiv 800 \
    --true-relief-mm 3.91 \
    --preview data/preview.blend
```

`--preview` changes the script's behaviour: it builds **one** live scene, leaves
the Displace modifier **unapplied**, adds no base and no boolean, and saves a
`.blend`. Open it, select the object, scrub Strength.

- [ ] **Strength ÷ 3.91 = exaggeration** at pilot scale. The script prints the
      full ladder; 7.8 mm is 2×, 15.6 is 4×, 31.3 is 8×.
- [ ] Light it from a low angle. Flat-lit terrain always reads flatter than it
      prints, and most of Portland's eastside is flats.
- [ ] Ignore the flat apron beyond the city — terrain outside the boundary
      normalises to 0. The boundary boolean removes it. Judge the terrain.
- [ ] `--subdiv 800` gives roughly 2 vertices per printed mm: enough to judge
      shape, responsive enough to scrub. Use 4–6/mm only for the real tiles.
      Subdivision is now split per axis in proportion to the footprint, so the
      quads stay square on a non-square sheet.

Two caveats before committing to what you see:

1. **The screen has infinite Z resolution; the printer has 0.2 mm layers.**
   Terracing is worst on shallow slopes — most of this map — and exaggeration
   is what suppresses it. That argues for landing *higher* than the render
   suggests.
2. **Exaggeration is a budget.** `topo_params.py plan --tile-mm 90 --cols 4
   --rows 3` prints grams and hours per step, now from a measured
   `MEAN_ELEV_FRACTION` rather than a guess.

- [ ] Record the chosen value in `docs/DECISIONS.md` with the reasoning, then
      run the script again **without** `--preview` to export real tiles.

---

## 12 — What comes next (not this sheet)

**The Z-scale value.** Everything above is scale-independent in Z — the
heightmaps are normalised 0–65535 and carry no exaggeration at all. The
exaggeration enters exactly once, as the Blender Displace **Strength** in
millimetres:

```
Strength_mm = true_relief_mm × exaggeration = 3.91 × E     (pilot 4×3 @ 90mm)
```

Because normalisation was project-wide, that same Strength is correct for
every tile. That is the entire point of step 10.

Bring back a Z-scale — as an exaggeration multiple, a Z factor, or just "the
peak should stand this far off the wall" — and it converts to the other two
via `topo_params.py plan --target-height-mm <N>`.

**The boolean cut.** Use `scripts/boundary_prism.py` rather than importing a
DXF or SVG — getting either into Blender at the right scale *and position* is
fiddly, and silently wrong when it goes wrong. The script writes the prism
directly in model millimetres, aligned by reading the georeferenced extent of
the same raster the heightmap came from:

```bash
python3 scripts/boundary_prism.py \
    --boundary data/vectors/boundary_smoothed.geojson \
    --ref-raster data/derived/dem_masked.tif \
    --tile-w 313 --tile-h 270 \
    --z-min -5 --z-max 60 \
    --out data/prism.stl
```

- [ ] Confirm it reports **`non-manifold 0`**. A prism that is not watertight
      makes a boolean produce garbage rather than fail, which is why the check
      is there. (The first version used a filtered unconstrained Delaunay for
      the caps and left 16 non-manifold edges on this outline; it now uses
      shapely's constrained Delaunay, which is exact.)
- [ ] Confirm the X and Y scales it prints agree to within ~1%. A mismatch
      means `--tile-w`/`--tile-h` disagree with the raster aspect and the model
      is stretched.
- [ ] `--z-min` below the model's lowest point, `--z-max` above its highest, so
      the prism constrains XY only and cuts cleanly through Z.
- [ ] Blender: **File → Import → STL**, then a **Boolean** modifier on the
      terrain, Operation **Intersect**, Object = the prism. Apply.
- [ ] Re-run **3D-Print Toolbox → Check All** on every tile, not a sample.
      Booleans are the one operation here that can produce non-manifold
      geometry.

> The same prism works on the whole-map preview — it is what removes the flat
> apron, so you judge Portland's silhouette rather than a rectangle with a city
> in the middle of it.

---

## Gotcha checklist

- [ ] Vertical units confirmed metres, not feet (step 3)
- [ ] Reprojected out of EPSG:4269 degrees BEFORE any -tr, buffer or slope
- [ ] MEAN_ELEV_FRACTION taken from the FULL DEM, never a test crop
- [ ] Never EPSG:4326 for anything dimensional
- [ ] Vectors reprojected **before** buffering or simplifying
- [ ] Boundary regularised with open+close and Chaikin, not plain Simplify
- [ ] Deviation checked in printed mm, not just in metres
- [ ] Raster mask buffered +50 m so smoothing does not dip the rim
- [ ] Normalisation project-wide, never `--auto-range`
- [ ] One-pixel shared edge between tiles
- [ ] Resample target recomputed for the final's scale, not copied from here
- [ ] `ELEV_MIN_M` / `ELEV_MAX_M` still valid after water flattening
- [ ] `MEAN_ELEV_FRACTION` updated in `topo_params.py` from `dem_stats.py`
- [ ] Every decision made along the way logged in `docs/DECISIONS.md`
