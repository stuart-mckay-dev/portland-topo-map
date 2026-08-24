# 02 — Data Sources

All endpoints below were verified August 2026. Record anything you actually
download in `docs/SOURCES.md` with the date and the exact query used.

## Elevation — bare earth

### Primary: USGS 3DEP 1 m DEM via OpenTopography

Best default. Already a bare-earth raster (no point-cloud processing needed),
1 m resolution, national coverage, public domain, and it supports bounding-box
subsetting through both the web UI and an API.

- Portal: <https://portal.opentopography.org/raster?opentopoID=OTNED.012021.4269.3>
- `opentopoID`: `OTNED.012021.4269.3`
- Resolution: 1 m
- Vertical datum: **NAVD88 (EPSG:5703), metres** — confirmed 2026-08-24 on a
  test crop: max 328.04 m against Council Crest's ~327 m, min 2.0 m at the
  Willamette.
- Horizontal CRS: **EPSG:4269 (NAD83, GEOGRAPHIC — degrees)**. Verified
  2026-08-24. An earlier revision of this doc claimed the API delivers a local
  UTM zone; it does not. Pixel size comes back in degrees, so **any** `-tr`,
  buffer or slope operation must wait until after a reprojection.
- Licence: US Government public domain, cite USGS 3DEP

An API key (free, registration required) allows scripted bbox downloads. See
`scripts/fetch_dem.py`, and run it with `--dry-run` first to see the size.

> **The 1 m tier is gated. Verified 2026-08-24.** OpenTopography's own dataset
> page states 1 m access is *"currently restricted to U.S. academic
> institutions with .edu addresses, plus educators and OpenTopography+
> members."* A perfectly valid free key returns **HTTP 401 on `USGS1m`** while
> `USGS10m` and `USGS30m` return 200. Diagnose with
> `python3 scripts/fetch_dem.py --check-key`, which sweeps all tiers.
>
> Two free routes to 1 m if it is ever actually needed:
>
> - **USGS The National Map** — 3DEP is public domain and USGS distributes the
>   1 m tiles itself, without OpenTopography's gate.
>   <https://apps.nationalmap.gov/downloader/>
> - **DOGAMI / Oregon Lidar Consortium** — see below; often crisper in the
>   West Hills anyway.
>
> But read the sampling table before assuming 1 m is needed at all.

> **Download size.** The full project bbox at 1 m is roughly 747 km2, i.e.
> ~747 megapixels — about **3.0 GB uncompressed float32**. This is a slow
> download and a slow first open in QGIS. It is also far finer than the printer
> can resolve: at 1:31,250 one printed millimetre spans ~31 m of ground, so
> ~31 DEM pixels collapse into a single millimetre. Resample early (doc 03
> step 4).

### How much resolution does this project actually need?

`1 printed mm = scale_denominator / 1000` metres of ground. A 0.4 mm extrusion
is the finest feature that can physically print.

| Configuration | 1 mm = | 10 m DEM gives | finest printable feature |
|---|---|---|---|
| pilot 4×3 @ 90 mm, 1:92,593 | 92.6 m | 9.3 samples/mm | 37.0 m |
| final 5×4 @ 200 mm, 1:31,250 | 31.3 m | 3.1 samples/mm | 12.5 m |
| final 7×6 @ 200 mm, 1:20,833 | 20.8 m | 2.1 samples/mm | 8.3 m |

`docs/03` targets 4–8 samples per printed mm. So:

- **Pilot: 10 m is comfortably sufficient** — 9.3 samples/mm, above target.
  1 m would be ~93× finer than anything the nozzle can render.
- **Final at 5×4: 10 m is adequate** — 3.1 samples/mm, slightly under target,
  but the 12.5 m printable-feature floor is close to the data resolution
  anyway.
- **Final at 7×6: 10 m starts to bite** — 2.1 samples/mm against an 8.3 m
  printable floor. This is the one configuration that genuinely wants better
  than 10 m, and DOGAMI or USGS TNM are the free routes to it.

**The road masks do not need a sharp DEM.** They are rasterised from the
PortlandMaps *vector* centrelines (doc 03 step 7), so their crispness comes
from the vectors and the output grid, not from DEM resolution. The earlier
advice to "keep the 1 m original for the road-mask step" was wrong and has
been removed.

### Alternative: Oregon DOGAMI / Oregon Lidar Consortium

Higher quality in places and the source of the classic Portland bare-earth
hillshades. Worth comparing against 3DEP for the West Hills, where DOGAMI's
collection is often crisper.

- Lidar Viewer: <https://gis.dogami.oregon.gov/maps/lidarviewer/>
- Program page: <https://www.oregon.gov/dogami/lidar/pages/index.aspx>
- Products: bare-earth hillshade, bare-earth slope, canopy height
- Download granularity: 7.5-minute USGS quadrangle
- Coverage: ~99% of Oregon as of January 2026

> **Units warning.** Some Oregon lidar deliverables are in **international
> feet**, not metres. Check the raster's units before scaling. A missed
> conversion introduces a silent 3.2808× error in vertical exaggeration that
> will look plausible right up until you print it.

### Also available

- DOGAMI data mirrored on OpenTopography:
  <https://portal.opentopography.org/lidarDataset?opentopoID=OTLAS.022011.2992.1>
- Metro RLIS — regional GIS, requires an account for some layers.

## Vectors — streets and bikeways

City of Portland Open Data, served from the PortlandMaps ArcGIS REST endpoint.
Every layer below supports `?f=geojson` queries and can be pulled with
`scripts/fetch_pdx_vectors.py`.

Base service:
`https://www.portlandmaps.com/od/rest/services/COP_OpenData_Transportation/MapServer`

| Layer | ID | Contents |
|---|---|---|
| Streets | 68 | Street centrelines, Portland + Multnomah/Clark/Washington counties |
| Bicycle Network | **75** | Citywide bike network with facility-type classification |
| Recommended Bicycle Routes | 183 | Developed bikeways, richer connection typing |
| Recommended Bicycle Route Points | 206 | Difficult connections, bike shops, elevation changes |

Native spatial reference is **EPSG:102100 / 3857 (Web Mercator)**. Reproject to
your working CRS before any distance or buffer operation — buffering in Web
Mercator at Portland's latitude overestimates widths by about 35%.

### Bicycle Network (layer 75) — the important one

This layer carries the classification that drives the colour extensions in
`docs/07-roads-and-color.md`.

**Fields:** `TranPlanID`, `SegmentName`, `Status`, `Facility`, `YearBuilt`,
`YearRetired`, `SCS`, `LengthMiles`

**`Status` domain** — filter to `ACTIVE` for anything that exists today:

| Code | Meaning |
|---|---|
| `ACTIVE` | Active |
| `PLANNED` | Planned |
| `RECOMM` | Recommended |
| `RETIRED` | Retired |
| `NONE` | No status defined |

**`Facility` domain** — this is the field to colour by:

| Code | Facility type |
|---|---|
| `NG` | Neighborhood Greenway |
| `PBL` | Protected Bike Lane |
| `BBL` | Buffered Bike Lane |
| `BL` | Bike Lane |
| `TRL` | Off-Street Paths / Trails |
| `SIR` | Separated in-Roadway |
| `ESR` | Enhanced Shared Roadway |
| `ABL` | Advisory Bike Lane |
| `NONE` | No Facility |

**`SCS` domain** — coarser grouping, useful for the first colour extension:

| Code | Meaning |
|---|---|
| `GREENWAY` | Neighborhood Greenway |
| `MAJBIKEWAY` | Major City Bikeway |
| `OTHERLANE` | Other Significant Bike Lanes |
| `NONE` | None |

> For "all greenways in green, everything else default", filter
> `SCS = 'GREENWAY'` **or** `Facility = 'NG'`. The two are near-identical but
> not byte-for-byte equal; `Facility` is the more literal reading and is what
> the scripts default to.

### Regional alternative

Oregon Metro's Bike There network covers the metro area beyond city limits but
carries almost no attribution — only a `Name` field, no facility typing. Use it
only if you extend the map past the city boundary.

`https://gis.oregonmetro.gov/arcgis/rest/services/transit/BikeThere/MapServer/0`

## Water

Needed if you want the Willamette and Columbia as flat planes or as a separate
AMS colour. Options: PortlandMaps hydrography layers, USGS NHD, or OSM
`natural=water` extracts. Flattening water to a constant elevation is usually
worth doing — lidar returns off water surfaces are noisy and produce a visibly
rippled river.

## Boundary

Verified August 2026. Two services carry the polygons; Metro's is the more
convenient because city limits and the UGB sit in one service.

**Oregon Metro — `BoundaryDataWebMerc`** (native SR EPSG:3857). Note the
last column is the area of the **bounding rectangle**, not of the polygon —
Portland's actual land area is far smaller, which is why a boundary-masked
DEM comes back only ~50–60% filled:

`https://gis.oregonmetro.gov/arcgis/rest/services/OpenData/BoundaryDataWebMerc/MapServer`

| Layer | ID | Fields | True ground extent | Extent area |
|---|---|---|---|---|
| City Limits | **0** | `OBJECTID`, `CITYNAME` | 28.44 x 24.53 km (`CITYNAME='Portland'`) | 697 km2 |
| Metro Boundary | 3 | — | larger | — |
| Urban Growth Boundary | **6** | `OBJECTID`, `UGB` | 61.37 x 41.35 km | 2,538 km2 |

**City of Portland — `COP_OpenData_Boundary`**:
`https://www.portlandmaps.com/od/rest/services/COP_OpenData_Boundary/MapServer`
Layer **10** is `City Boundaries`.

Example pull:

```
curl -o data/vectors/portland_city_limits.geojson \
  "https://gis.oregonmetro.gov/arcgis/rest/services/OpenData/BoundaryDataWebMerc/MapServer/0/query?where=CITYNAME%3D%27Portland%27&outFields=*&outSR=4326&f=geojson"
```

### Which one, and what it costs

The **city limits** are effectively the project bbox already — 28.44 x 24.53 km
against the bbox's 27.87 x 24.69 km. The bbox was evidently derived from them.
It is 566 m narrower than the real city, so the current rectangle clips a thin
sliver; widen by ~600 m to capture the whole thing.

The **UGB is 3.7x the area** and a different project. At any wall width the
scale denominator more than doubles. Critically, it covers terrain above the
West Hills, so `ELEV_MAX_M = 362.0` in `topo_params.py` and
`qgis_export_tiles.py` would be wrong and would silently compress the map.
Re-derive every constant before using it.

### The project historically did NOT cut to a boundary

The rectangular bbox was a deliberate choice: the map includes unincorporated
pockets and slices of neighbouring cities, because terrain does not stop at a
jurisdiction line. Cutting to a boundary reverses that decision — see
`docs/11-pilot-runsheet.md` section 0 for the four consequences, and log the
choice in `docs/DECISIONS.md`.

Practical notes if you do cut:

- Portland's city limits contain enclaves (Maywood Park) and unincorporated
  pockets, which become real holes in the map unless dissolved out.
- Reproject out of Web Mercator **before** buffering or simplifying;
  at Portland's latitude Web Mercator overstates distance by ~43%.
- Simplify to print scale or the annexation staircases print as noise:
  ~40 m tolerance at the pilot's 1:92,593, ~15 m at a 1:31,250 final.

## Attribution

Record in `docs/SOURCES.md`, and if the piece is ever shown publicly,
credit at minimum: USGS 3DEP, Oregon DOGAMI/OLC, and the City of Portland
Bureau of Transportation.
