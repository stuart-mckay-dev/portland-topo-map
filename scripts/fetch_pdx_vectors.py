#!/usr/bin/env python3
"""
fetch_pdx_vectors.py -- Pull street and bicycle-network vectors from the
City of Portland ArcGIS REST endpoint as GeoJSON.

Endpoints verified 2026-08. Layer field domains are documented in
docs/02-data-sources.md.

Usage:
  python3 fetch_pdx_vectors.py bike      --out data/raw/bike_network.geojson
  python3 fetch_pdx_vectors.py bike      --active-only --facility NG
  python3 fetch_pdx_vectors.py streets   --out data/raw/streets.geojson
  python3 fetch_pdx_vectors.py bike --split-by-facility --out-dir data/raw/bike

Output is EPSG:4326 by default (--wkid to change). Reproject to the project
CRS before buffering -- see docs/03-qgis-workflow.md.

Only stdlib. No dependencies.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = ("https://www.portlandmaps.com/od/rest/services/"
        "COP_OpenData_Transportation/MapServer")

LAYERS = {
    "streets": 68,
    "bike": 75,
    "bike_recommended": 183,
    "bike_points": 206,
}

# Facility codes from the WS1_BNFacilityTypeCVD domain on layer 75.
FACILITY_CODES = {
    "NG":   "Neighborhood Greenway",
    "PBL":  "Protected Bike Lane",
    "BBL":  "Buffered Bike Lane",
    "BL":   "Bike Lane",
    "TRL":  "Off-Street Paths/Trails",
    "SIR":  "Separated in-Roadway",
    "ESR":  "Enhanced Shared Roadway",
    "ABL":  "Advisory Bike Lane",
    "NONE": "No Facility",
}

# Suggested collapse to four classes, to fit the AMS's four slots.
# See docs/07-roads-and-color.md.
FACILITY_GROUPS = {
    "separated": ["TRL", "PBL"],
    "greenway":  ["NG"],
    "painted":   ["BBL", "BL", "SIR"],
    "shared":    ["ESR", "ABL"],
}

PAGE = 1000


def query(layer_id: int, where: str, wkid: int, verbose=True):
    """Page through an ArcGIS REST layer and return a merged GeoJSON dict."""
    features = []
    offset = 0
    while True:
        params = {
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": str(wkid),
            "f": "geojson",
            "resultOffset": str(offset),
            "resultRecordCount": str(PAGE),
        }
        url = f"{BASE}/{layer_id}/query?" + urllib.parse.urlencode(params)
        if verbose:
            print(f"  fetching offset {offset}...", file=sys.stderr)
        with urllib.request.urlopen(url, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        if "error" in data:
            raise SystemExit(f"ArcGIS error: {data['error']}")
        batch = data.get("features", [])
        features.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        time.sleep(0.3)
    return {"type": "FeatureCollection", "features": features}


def write(fc, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(fc, f)
    print(f"  wrote {len(fc['features']):,} features -> {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layer", choices=list(LAYERS))
    ap.add_argument("--out", default=None)
    ap.add_argument("--out-dir", default="data/raw")
    ap.add_argument("--wkid", type=int, default=4326)
    ap.add_argument("--where", default=None, help="raw SQL WHERE override")
    ap.add_argument("--active-only", action="store_true",
                    help="bike layers: Status='ACTIVE'")
    ap.add_argument("--facility", nargs="*", default=None,
                    help=f"filter Facility codes: {' '.join(FACILITY_CODES)}")
    ap.add_argument("--split-by-facility", action="store_true",
                    help="write one GeoJSON per facility code")
    ap.add_argument("--split-by-group", action="store_true",
                    help="write one GeoJSON per collapsed 4-colour group")
    a = ap.parse_args()

    lid = LAYERS[a.layer]

    clauses = []
    if a.where:
        clauses.append(f"({a.where})")
    if a.active_only:
        clauses.append("Status = 'ACTIVE'")
    if a.facility:
        codes = ",".join(f"'{c}'" for c in a.facility)
        clauses.append(f"Facility IN ({codes})")
    where = " AND ".join(clauses) if clauses else "1=1"

    if a.split_by_facility or a.split_by_group:
        groups = (FACILITY_GROUPS if a.split_by_group
                  else {c: [c] for c in FACILITY_CODES if c != "NONE"})
        for name, codes in groups.items():
            codelist = ",".join(f"'{c}'" for c in codes)
            w = f"{where} AND Facility IN ({codelist})" if where != "1=1" \
                else f"Facility IN ({codelist})"
            print(f"[{name}] {w}")
            fc = query(lid, w, a.wkid)
            write(fc, os.path.join(a.out_dir, f"bike_{name}.geojson"))
        return

    out = a.out or os.path.join(a.out_dir, f"{a.layer}.geojson")
    print(f"[{a.layer}] layer {lid}  WHERE {where}")
    fc = query(lid, where, a.wkid)
    write(fc, out)


if __name__ == "__main__":
    main()
