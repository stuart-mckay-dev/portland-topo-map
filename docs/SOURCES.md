# Source Log

Record every dataset you actually download: what, from where, when, and the
exact query. Future-you will need to reproduce this.

| Date | Dataset | Source | Query / extent | File | Licence |
|---|---|---|---|---|---|
| | USGS 3DEP 1 m DEM | OpenTopography `OTNED.012021.4269.3` | bbox | | US Gov public domain |
| | Bicycle Network | PortlandMaps layer 75 | `Status='ACTIVE'` | | City of Portland open data |
| | Streets | PortlandMaps layer 68 | | | City of Portland open data |

## Endpoints

- 3DEP via OpenTopography — <https://portal.opentopography.org/raster?opentopoID=OTNED.012021.4269.3>
- DOGAMI Lidar Viewer — <https://gis.dogami.oregon.gov/maps/lidarviewer/>
- PortlandMaps Transportation MapServer —
  `https://www.portlandmaps.com/od/rest/services/COP_OpenData_Transportation/MapServer`
- Portland Open Data portal — <https://gis-pdx.opendata.arcgis.com/>

## Attribution for public display

- Elevation: USGS 3D Elevation Program (3DEP) / Oregon Dept. of Geology and
  Mineral Industries, Oregon Lidar Consortium
- Streets and bicycle network: City of Portland Bureau of Transportation
