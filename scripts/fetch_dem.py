#!/usr/bin/env python3
"""
fetch_dem.py -- Download the USGS 3DEP 1 m bare-earth DEM for the Portland
bounding box from OpenTopography.

Needs a free OpenTopography API key:
  https://portal.opentopography.org/  ->  register  ->  request an API key
Set it as an environment variable:
  export OPENTOPO_API_KEY=xxxxxxxx

Usage:
  python3 scripts/fetch_dem.py --out data/raw/portland_3dep_1m.tif
  python3 scripts/fetch_dem.py --center-lat 45.5152 --center-lon -122.6784 --margin-m 500

The default bbox is the project bbox from docs/00-project-spec.md, centred on
downtown Portland. If you have an exact bbox in a projected CRS, pass
--south/--north/--west/--east in WGS84 degrees instead.

Only stdlib.
"""

from __future__ import annotations
import argparse
import math
import os
import sys
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://portal.opentopography.org/API/usgsdem"
DEMTYPE = "USGS1m"           # USGS 3DEP 1 metre

# Project bbox dimensions, metres (docs/00-project-spec.md)
BBOX_W_M = 29_000.0
BBOX_H_M = 25_000.0

# Centroid of the Portland city-limits EXTENT, not downtown.
# Downtown-centring clipped the city by 2.2 km east / 3.0 km north,
# which is fatal once the map is cut to the boundary silhouette.
# UTM 10N E 527,009.0  N 5,043,315.6.  See docs/DECISIONS.md 2026-08-24.
CENTER_LAT = 45.542853
CENTER_LON = -122.654030


def bbox_from_center(lat, lon, w_m, h_m, margin_m=0.0):
    """Convert a metre-sized box centred on lat/lon into WGS84 degrees."""
    w = w_m + 2 * margin_m
    h = h_m + 2 * margin_m
    dlat = (h / 2.0) / 111_320.0
    dlon = (w / 2.0) / (111_320.0 * math.cos(math.radians(lat)))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


DEFAULT_KEY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "OpenTopography_API_Key.txt")


def read_key_file(path):
    """Pull the token out of a key file that may also carry a label line.

    Accepts a bare token on its own line, or KEY=VALUE. Picks the longest
    line that looks like a token, so a human-readable label above it is fine.
    """
    try:
        with open(path) as f:
            raw = f.read()
    except OSError:
        return None
    best = None
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            line = line.split("=", 1)[1].strip().strip("'\"")
        if re.fullmatch(r"[A-Za-z0-9._-]{16,}", line):
            if best is None or len(line) > len(best):
                best = line
    return best


def _probe(url, key, label):
    """Fire a tiny request and report the status plus the server's own words."""
    shown = url.replace(key, "***") if key else url
    print(f"\n  {label}")
    print(f"    GET {shown[:120]}...")
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            body = r.read(400)
            print(f"    -> HTTP {r.status}  {len(body)} bytes of {r.headers.get('Content-Type')}")
            return r.status
    except urllib.error.HTTPError as e:
        body = e.read(400).decode("utf-8", "replace").strip()
        print(f"    -> HTTP {e.code}  {e.reason}")
        if body:
            print(f"    server says: {body[:300]}")
        return e.code
    except Exception as e:
        print(f"    -> {type(e).__name__}: {e}")
        return None


def check_key(key, south=45.50, north=45.52, west=-122.70, east=-122.68):
    """Probe every collection and every 3DEP tier over the same tiny box.

    The tiers are entitled and staged separately, and 3DEP 1 m coverage is
    NOT national -- it exists only where 1 m lidar-derived DEMs have been
    published. So a key can be perfectly valid at 30 m and still be refused
    at 1 m, either for entitlement or for coverage.
    """
    print("\n  Key check. Same key, same box, every collection and tier.")
    bbox = f"south={south}&north={north}&west={west}&east={east}"
    res = {}
    res["global/SRTMGL3"] = _probe(
        f"https://portal.opentopography.org/API/globaldem?demtype=SRTMGL3&{bbox}"
        f"&outputFormat=GTiff&API_Key={key}", key, "globaldem / SRTMGL3")
    for tier in ("USGS30m", "USGS10m", "USGS1m"):
        res[f"3DEP/{tier}"] = _probe(
            f"{API}?datasetName={tier}&{bbox}&outputFormat=GTiff&API_Key={key}",
            key, f"usgsdem / {tier}")

    print("\n  Summary:")
    for k, v in res.items():
        print(f"    {k:18s} {v}")

    print("\n  Verdict:")
    ok = {k for k, v in res.items() if v == 200}
    if "3DEP/USGS1m" in ok:
        print("    1 m works here. The original 401 was not the tier -- re-check the")
        print("    exact command you ran.")
    elif "3DEP/USGS30m" in ok or "3DEP/USGS10m" in ok:
        print("    The key and 3DEP access are FINE; 1 m specifically is refused.")
        print("    Two causes, and they are distinguishable:")
        print("      - NO 1 m COVERAGE over this box. 3DEP 1 m is not national. Check")
        print("        the coverage map before assuming the key is at fault:")
        print("        https://portal.opentopography.org/raster?opentopoID=OTNED.012021.4269.3")
        print("      - 1 m is entitled separately on your account.")
        print("    Either way the project has a ready fallback: --dataset USGS10m.")
        print("    At the pilot's 1:92,593 the useful ground resolution is 15.4 m,")
        print("    so 10 m is already finer than the pilot can resolve. Only the")
        print("    FINAL's road masks genuinely want 1 m.")
    elif ok:
        print("    Only the global collection works. 3DEP access is not enabled.")
    else:
        print("    Nothing works. Key is wrong or inactive.")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/raw/portland_3dep_1m.tif")
    ap.add_argument("--center-lat", type=float, default=CENTER_LAT)
    ap.add_argument("--center-lon", type=float, default=CENTER_LON)
    ap.add_argument("--margin-m", type=float, default=200.0,
                    help="pad beyond the project bbox; 200m is plenty")
    ap.add_argument("--south", type=float)
    ap.add_argument("--north", type=float)
    ap.add_argument("--west", type=float)
    ap.add_argument("--east", type=float)
    ap.add_argument("--format", default="GTiff", choices=["GTiff", "AAIGrid", "HFA"])
    ap.add_argument("--api-key", default=os.environ.get("OPENTOPO_API_KEY"))
    ap.add_argument("--api-key-file", default=DEFAULT_KEY_FILE,
                    help="file holding the token; a label line above it is fine. "
                         "Defaults to OpenTopography_API_Key.txt at the repo root.")
    ap.add_argument("--dataset", default=DEMTYPE,
                    choices=["USGS1m", "USGS10m", "USGS30m"],
                    help="3DEP resolution tier")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-key", action="store_true",
                    help="probe two endpoints to diagnose a 401 and exit")
    a = ap.parse_args()

    if not a.api_key and a.api_key_file:
        a.api_key = read_key_file(a.api_key_file)
        if a.api_key:
            print(f"  key         read from {a.api_key_file}")

    if a.check_key:
        if not a.api_key:
            sys.exit(f"No key found. Tried --api-key, $OPENTOPO_API_KEY and\n{a.api_key_file}")
        print(f"  fingerprint {a.api_key[:4]}...{a.api_key[-4:]}  ({len(a.api_key)} chars)")
        if all(v is not None for v in (a.south, a.north, a.west, a.east)):
            check_key(a.api_key, a.south, a.north, a.west, a.east)
        else:
            check_key(a.api_key)
        return

    if all(v is not None for v in (a.south, a.north, a.west, a.east)):
        s, n, w, e = a.south, a.north, a.west, a.east
    else:
        s, n, w, e = bbox_from_center(a.center_lat, a.center_lon,
                                      BBOX_W_M, BBOX_H_M, a.margin_m)

    print(f"  bbox  S {s:.6f}  N {n:.6f}  W {w:.6f}  E {e:.6f}")
    span_w = (e - w) * 111_320.0 * math.cos(math.radians((s + n) / 2))
    span_h = (n - s) * 111_320.0
    print(f"  span  {span_w:,.0f} x {span_h:,.0f} m")
    gsd = {"USGS1m": 1.0, "USGS10m": 10.0, "USGS30m": 30.0}[a.dataset]
    km2 = span_w * span_h / 1e6
    mpx = span_w * span_h / (gsd * gsd) / 1e6
    print(f"  dataset     {a.dataset}  ({gsd:g} m ground sample distance)")
    print(f"  ~{km2:,.0f} km2  = ~{mpx:,.1f} Mpx at {gsd:g} m  "
          f"(~{mpx * 4 / 1e3:.2f} GB uncompressed float32)")

    if not a.api_key:
        sys.exit(f"\nNo API key. Tried --api-key, $OPENTOPO_API_KEY and\n"
                 f"{a.api_key_file}\n"
                 "Register free at https://portal.opentopography.org/")

    params = {
        "datasetName": a.dataset,
        "south": f"{s:.6f}", "north": f"{n:.6f}",
        "west": f"{w:.6f}", "east": f"{e:.6f}",
        "outputFormat": a.format,
        "API_Key": a.api_key,
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"

    if a.dry_run:
        print("\n  would GET:")
        print("  " + url.replace(a.api_key, "***"))
        return

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    print(f"\n  downloading -> {a.out}  (this takes a while)")
    with urllib.request.urlopen(url, timeout=1800) as r, open(a.out, "wb") as f:
        total = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            total += len(chunk)
            print(f"\r  {total / 1e6:,.1f} MB", end="", flush=True)
    print(f"\n  done: {total / 1e6:,.1f} MB")
    print("\n  Next:")
    print("    1. python3 scripts/dem_stats.py " + a.out)
    print("       CONFIRM THE VERTICAL UNITS ARE METRES. The full project DEM")
    print("       maxes at ~362 m; a sub-crop maxes wherever its own high point")
    print("       is. A max near 3.28x the expected figure means FEET.")
    print("    2. Note the CRS. 3DEP arrives GEOGRAPHIC (EPSG:4269, degrees).")
    print("       Reproject to EPSG:32610 before any resample or buffer.")
    print("    3. Follow docs/11-pilot-runsheet.md from step 3.")


if __name__ == "__main__":
    main()
