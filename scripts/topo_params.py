#!/usr/bin/env python3
"""
topo_params.py -- The single source of truth for PortlandTopo dimensional math.

Every number in docs/ that touches scale, tile size, vertical exaggeration,
print height, filament mass or wall load is produced by this script. If you
change a project parameter, change it HERE and regenerate the docs tables.
Do not hand-edit derived numbers into the markdown.

Usage
-----
  python3 topo_params.py plan --wall-width-mm 903
  python3 topo_params.py plan --tile-mm 200 --cols 5
  python3 topo_params.py plan --tile-mm 100 --cols 4 --label pilot
  python3 topo_params.py exagg --wall-width-mm 903
  python3 topo_params.py compare
  python3 topo_params.py grid --max-tile-mm 200

No third-party dependencies. Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field, asdict

# ---------------------------------------------------------------------------
# PORTLAND CONSTANTS
# ---------------------------------------------------------------------------
# Bounding box of the City of Portland, OR as supplied by the project owner.
# 17.32 mi E-W x 15.34 mi N-S.
BBOX_W_M = 29_000.0        # East-West extent, metres
BBOX_H_M = 25_000.0        # North-South extent, metres
ASPECT = BBOX_W_M / BBOX_H_M   # ~1.1600 : 1, wider than tall
# Sized to the Portland city-limits extent (28,578.6 x 24,602.4 m in
# EPSG:32610) plus ~200 m margin, centred on that extent's centroid --
# NOT on downtown. See docs/DECISIONS.md 2026-08-24.

# Elevation extremes (NAVD88 metres).
ELEV_MIN_M = 0.19          # Columbia River, 0.62 ft
ELEV_MAX_M = 362.0         # 1,188 ft, high point in the West Hills
ELEV_RANGE_M = ELEV_MAX_M - ELEV_MIN_M

# Mean elevation as a FRACTION of the full range. Used only for filament and
# mass estimates. Portland is dominated by low-lying flats (Willamette/Columbia
# floodplain, inner eastside) with terrain concentrated in the West Hills,
# Rocky Butte, Mt Tabor and Powell Butte -- so the mean sits well below the
# midpoint. 0.17 is a working placeholder.
#
# >>> REPLACE THIS with the real value once you have the DEM. Run:
# >>>     python3 scripts/dem_stats.py data/derived/portland_dem.tif
# >>> and paste the reported mean_fraction here.
MEAN_ELEV_FRACTION = 0.1958
MEAN_ELEV_FRACTION_IS_ESTIMATE = False

# ---------------------------------------------------------------------------
# PRINTER CONSTANTS -- Bambu Lab X1 Carbon + AMS
# ---------------------------------------------------------------------------
BED_X_MM = 256.0
BED_Y_MM = 256.0
BED_Z_MM = 256.0

# Practical working envelope. The advertised 256^3 is the outer limit, not a
# promise every millimetre is usable: prime lines, exclusion zones, the purge
# tower and brim all eat into it, and large flat-bottomed parts warp at the
# corners well before you reach the edge. SAFE_XY is the size this project
# treats as "prints reliably without babysitting".
SAFE_XY_MM = 200.0         # 8 inches -- the project default
STRETCH_XY_MM = 230.0      # ~9 inches -- possible, expect more corner lift
SAFE_Z_MM = 240.0          # leave headroom under the gantry

# Material / process assumptions (PLA, 0.2mm layer, 0.4mm nozzle).
FILAMENT_DENSITY_G_CM3 = 1.24
SOLID_FRACTION = 0.28      # effective solid ratio: walls + top/bottom + ~15% infill
PRINT_RATE_CM3_PER_HR = 14.0  # observed X1C throughput on large textured surfaces

BASE_MM = 4.0              # lowest elevation sits this far off the build plate
                           # Was 10.0 until 2026-08-24. See DECISIONS.md --
                           # halves pilot mass and time, but leaves only 4 mm
                           # under the flats for recessed mounting hardware.

MM_PER_INCH = 25.4


# ---------------------------------------------------------------------------
# CORE MODEL
# ---------------------------------------------------------------------------
@dataclass
class Plan:
    label: str
    cols: int
    rows: int
    wall_w_mm: float
    wall_h_mm: float
    tile_w_mm: float
    tile_h_mm: float
    scale_denom: float
    true_relief_mm: float
    base_mm: float = BASE_MM

    # ---- derived helpers -------------------------------------------------
    @property
    def n_tiles(self) -> int:
        return self.cols * self.rows

    @property
    def tile_aspect(self) -> float:
        return self.tile_w_mm / self.tile_h_mm

    @property
    def ground_per_tile_km(self) -> tuple:
        return (BBOX_W_M / self.cols / 1000.0, BBOX_H_M / self.rows / 1000.0)

    @property
    def mm_per_metre_ground(self) -> float:
        """Horizontal millimetres of model per metre of real ground."""
        return 1000.0 / self.scale_denom

    def relief_for_exagg(self, v: float) -> float:
        """Peak relief above the base plane, in mm, at vertical exaggeration v."""
        return self.true_relief_mm * v

    def exagg_for_relief(self, relief_mm: float) -> float:
        """Vertical exaggeration needed to put the peak at relief_mm above base."""
        return relief_mm / self.true_relief_mm

    def exagg_for_total_height(self, total_mm: float) -> float:
        return self.exagg_for_relief(total_mm - self.base_mm)

    def total_height_for_exagg(self, v: float) -> float:
        return self.base_mm + self.relief_for_exagg(v)

    def z_scale_factor(self, v: float) -> float:
        """
        The number to type into Blender's displace modifier / QGIS band scaling.
        Model mm of Z per real metre of elevation.
        """
        return self.mm_per_metre_ground * v

    # ---- estimates -------------------------------------------------------
    def tile_volume_cm3(self, v: float) -> float:
        """Rough solid-equivalent extruded volume for an AVERAGE tile."""
        mean_relief = self.relief_for_exagg(v) * MEAN_ELEV_FRACTION
        bulk_mm3 = self.tile_w_mm * self.tile_h_mm * (self.base_mm + mean_relief)
        return bulk_mm3 * SOLID_FRACTION / 1000.0

    def tile_mass_g(self, v: float) -> float:
        return self.tile_volume_cm3(v) * FILAMENT_DENSITY_G_CM3

    def tile_hours(self, v: float) -> float:
        return self.tile_volume_cm3(v) / PRINT_RATE_CM3_PER_HR

    def total_mass_kg(self, v: float) -> float:
        return self.tile_mass_g(v) * self.n_tiles / 1000.0

    def total_hours(self, v: float) -> float:
        return self.tile_hours(v) * self.n_tiles

    def spools_1kg(self, v: float) -> float:
        return self.total_mass_kg(v)

    # ---- validation ------------------------------------------------------
    def warnings(self, v: float) -> list:
        w = []
        longest = max(self.tile_w_mm, self.tile_h_mm)
        if longest > STRETCH_XY_MM:
            w.append(f"TILE TOO BIG: {longest:.0f}mm exceeds the {STRETCH_XY_MM:.0f}mm stretch limit.")
        elif longest > SAFE_XY_MM:
            w.append(f"Tile {longest:.0f}mm is past the {SAFE_XY_MM:.0f}mm comfort zone -- expect corner warp; use a brim and draft-shield.")
        th = self.total_height_for_exagg(v)
        if th > SAFE_Z_MM:
            w.append(f"PEAK TILE {th:.0f}mm tall exceeds the {SAFE_Z_MM:.0f}mm safe Z.")
        if v > 12:
            w.append(f"Exaggeration {v:.1f}x is very high -- terrain will read as spiky rather than topographic.")
        if v < 1.5:
            w.append(f"Exaggeration {v:.1f}x is low -- relief of {self.relief_for_exagg(v):.1f}mm may read as nearly flat on a wall.")
        return w


def build_plan(cols: int, rows: int, wall_w_mm: float, label: str = "plan") -> Plan:
    wall_h_mm = wall_w_mm / ASPECT
    tile_w = wall_w_mm / cols
    tile_h = wall_h_mm / rows
    scale_denom = (BBOX_W_M * 1000.0) / wall_w_mm
    true_relief = (ELEV_RANGE_M * 1000.0) / scale_denom
    return Plan(
        label=label, cols=cols, rows=rows,
        wall_w_mm=wall_w_mm, wall_h_mm=wall_h_mm,
        tile_w_mm=tile_w, tile_h_mm=tile_h,
        scale_denom=scale_denom, true_relief_mm=true_relief,
    )


def plan_from_tile(cols: int, rows: int, tile_mm: float, label: str = "plan") -> Plan:
    """Treat tile_mm as the LONGEST tile edge and fit the wall to it."""
    # tile_w = W/cols ; tile_h = W/(ASPECT*rows). Whichever is larger is pinned.
    w_from_width = tile_mm * cols
    w_from_height = tile_mm * rows * ASPECT
    wall_w = min(w_from_width, w_from_height)
    return build_plan(cols, rows, wall_w, label)


def near_square_grids(max_tile_mm: float, max_tiles: int = 90) -> list:
    """Enumerate candidate grids, ranked by how square the tiles come out."""
    out = []
    for cols in range(2, 13):
        for rows in range(2, 13):
            if cols * rows > max_tiles:
                continue
            p = plan_from_tile(cols, rows, max_tile_mm)
            squareness = abs(math.log(p.tile_aspect))
            out.append((squareness, p))
    out.sort(key=lambda t: t[0])
    return [p for _, p in out]


# ---------------------------------------------------------------------------
# REPORTING
# ---------------------------------------------------------------------------
def _inches(mm: float) -> str:
    return f'{mm / MM_PER_INCH:.1f}"'


def print_plan(p: Plan, exaggs=None) -> None:
    exaggs = exaggs or [1, 2, 3, 4, 6, 8, 10, 12]
    print()
    print("=" * 74)
    print(f"  PLAN: {p.label}")
    print("=" * 74)
    print(f"  Grid                {p.cols} cols x {p.rows} rows = {p.n_tiles} tiles")
    print(f"  Finished wall       {p.wall_w_mm:.0f} x {p.wall_h_mm:.0f} mm   ({_inches(p.wall_w_mm)} x {_inches(p.wall_h_mm)})")
    print(f"  Tile footprint      {p.tile_w_mm:.1f} x {p.tile_h_mm:.1f} mm   (aspect {p.tile_aspect:.3f})")
    gx, gy = p.ground_per_tile_km
    print(f"  Ground per tile     {gx:.2f} x {gy:.2f} km")
    print(f"  Horizontal scale    1 : {p.scale_denom:,.0f}")
    print(f"  1 mm of model       = {p.scale_denom / 1000:.1f} m of ground")
    print(f"  True (1x) relief    {p.true_relief_mm:.2f} mm for the full {ELEV_RANGE_M:.0f} m range")
    print(f"  Base slab           {p.base_mm:.1f} mm under the lowest point")
    print()
    print("  VERTICAL EXAGGERATION")
    print("  " + "-" * 70)
    print(f"  {'exagg':>6} {'relief':>9} {'total H':>9} {'off wall':>9} {'Z factor':>10} {'g/tile':>8} {'h/tile':>7} {'total kg':>9} {'total h':>8}")
    print("  " + "-" * 70)
    for v in exaggs:
        th = p.total_height_for_exagg(v)
        flag = ""
        if th > SAFE_Z_MM:
            flag = "  << over Z"
        print(f"  {v:>5.1f}x {p.relief_for_exagg(v):>8.1f}mm {th:>8.1f}mm {_inches(th):>9} "
              f"{p.z_scale_factor(v):>9.4f} {p.tile_mass_g(v):>7.0f} {p.tile_hours(v):>6.1f} "
              f"{p.total_mass_kg(v):>8.1f} {p.total_hours(v):>7.0f}{flag}")
    print("  " + "-" * 70)
    print("  Z factor = model mm of height per real metre of elevation.")
    print("            Multiply your DEM (in metres) by this in Blender/QGIS.")
    if MEAN_ELEV_FRACTION_IS_ESTIMATE:
        print(f"  NOTE: mass/time use an ESTIMATED mean elevation fraction of")
        print(f"        {MEAN_ELEV_FRACTION}. Re-run dem_stats.py to replace it.")
    print()


def cmd_plan(args) -> None:
    if args.wall_width_mm:
        cols, rows = args.cols, args.rows
        p = build_plan(cols, rows, args.wall_width_mm, args.label)
    elif args.tile_mm:
        p = plan_from_tile(args.cols, args.rows, args.tile_mm, args.label)
    else:
        raise SystemExit("Give either --wall-width-mm or --tile-mm")

    exaggs = args.exagg if args.exagg else None
    print_plan(p, exaggs)

    if args.target_height_mm:
        v = p.exagg_for_total_height(args.target_height_mm)
        print(f"  >> To put the peak at exactly {args.target_height_mm:.1f}mm total "
              f"({_inches(args.target_height_mm)}) off the wall:")
        print(f"     vertical exaggeration = {v:.3f}x")
        print(f"     Z factor              = {p.z_scale_factor(v):.4f} mm per metre")
        print(f"     est. filament         = {p.total_mass_kg(v):.1f} kg over {p.n_tiles} tiles")
        print(f"     est. print time       = {p.total_hours(v):.0f} h "
              f"({p.total_hours(v)/24:.1f} days continuous)")
        print()

    for w in p.warnings(args.check_exagg or 6):
        print(f"  [!] {w}")
    print()

    if args.json:
        d = asdict(p)
        d["n_tiles"] = p.n_tiles
        print(json.dumps(d, indent=2))


def cmd_grid(args) -> None:
    print()
    print(f"Candidate grids with a max tile edge of {args.max_tile_mm:.0f}mm, "
          f"ranked by tile squareness:")
    print()
    hdr = f"{'grid':>8} {'tiles':>6} {'tile mm':>15} {'aspect':>7} {'wall mm':>15} {'wall in':>15} {'scale':>12} {'1x relief':>10}"
    print(hdr)
    print("-" * len(hdr))
    for p in near_square_grids(args.max_tile_mm)[:args.top]:
        print(f"{p.cols}x{p.rows:<6} {p.n_tiles:>6} "
              f"{p.tile_w_mm:>7.1f}x{p.tile_h_mm:<7.1f} {p.tile_aspect:>7.3f} "
              f"{p.wall_w_mm:>7.0f}x{p.wall_h_mm:<7.0f} "
              f"{_inches(p.wall_w_mm):>7}x{_inches(p.wall_h_mm):<7} "
              f"1:{p.scale_denom:>10,.0f} {p.true_relief_mm:>9.2f}mm")
    print()


def cmd_exagg(args) -> None:
    p = build_plan(args.cols, args.rows, args.wall_width_mm, args.label)
    print()
    print(f"{p.label}: 1:{p.scale_denom:,.0f}, true relief {p.true_relief_mm:.2f}mm")
    print()
    print(f"{'total H off wall':>18} {'exagg':>8} {'Z factor':>10} {'est kg':>8} {'est hours':>10}")
    print("-" * 58)
    for inches in [0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8]:
        mm = inches * MM_PER_INCH
        if mm <= p.base_mm:
            continue
        v = p.exagg_for_total_height(mm)
        over = "  << over Z" if mm > SAFE_Z_MM else ""
        print(f'{inches:>7.2f}" ={mm:>7.1f}mm {v:>7.2f}x {p.z_scale_factor(v):>9.4f} '
              f"{p.total_mass_kg(v):>7.1f} {p.total_hours(v):>9.0f}{over}")
    print()


def cmd_compare(args) -> None:
    print()
    print("PILOT CANDIDATES (small, fast, validates the whole pipeline)")
    for cols, rows, tile in [(3, 2, 90), (4, 3, 90), (4, 3, 100), (5, 4, 80)]:
        p = plan_from_tile(cols, rows, tile, f"pilot {cols}x{rows} @ {tile}mm")
        v = p.exagg_for_total_height(40.0)
        print(f"  {p.cols}x{p.rows:<3} {p.n_tiles:>3} tiles  "
              f"{p.tile_w_mm:>6.1f}x{p.tile_h_mm:<6.1f}mm  "
              f"wall {_inches(p.wall_w_mm)}x{_inches(p.wall_h_mm):<7} "
              f"1:{p.scale_denom:>8,.0f}  "
              f"@40mm tall: {v:>5.2f}x  {p.total_mass_kg(v):>4.1f}kg  {p.total_hours(v):>4.0f}h")
    print()
    print("FINAL CANDIDATES (200mm tiles)")
    for cols, rows in [(4, 3), (4, 4), (5, 4), (6, 5), (7, 6)]:
        p = plan_from_tile(cols, rows, SAFE_XY_MM, f"final {cols}x{rows}")
        v6 = p.exagg_for_total_height(6 * MM_PER_INCH)
        v2 = p.exagg_for_total_height(2 * MM_PER_INCH)
        print(f"  {p.cols}x{p.rows:<3} {p.n_tiles:>3} tiles  "
              f"{p.tile_w_mm:>6.1f}x{p.tile_h_mm:<6.1f}mm  "
              f"wall {_inches(p.wall_w_mm)}x{_inches(p.wall_h_mm):<7} "
              f"1:{p.scale_denom:>8,.0f}  "
              f'2"={v2:>5.2f}x ({p.total_mass_kg(v2):>4.1f}kg {p.total_hours(v2):>4.0f}h)  '
              f'6"={v6:>5.2f}x ({p.total_mass_kg(v6):>4.1f}kg {p.total_hours(v6):>4.0f}h)')
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("plan", help="full report for one configuration")
    p1.add_argument("--wall-width-mm", type=float)
    p1.add_argument("--tile-mm", type=float, help="longest tile edge")
    p1.add_argument("--cols", type=int, default=5)
    p1.add_argument("--rows", type=int, default=4)
    p1.add_argument("--label", default="plan")
    p1.add_argument("--target-height-mm", type=float,
                    help="solve exaggeration for this total height off the wall")
    p1.add_argument("--exagg", type=float, nargs="*")
    p1.add_argument("--check-exagg", type=float)
    p1.add_argument("--json", action="store_true")
    p1.set_defaults(func=cmd_plan)

    p2 = sub.add_parser("grid", help="rank candidate grids by tile squareness")
    p2.add_argument("--max-tile-mm", type=float, default=SAFE_XY_MM)
    p2.add_argument("--top", type=int, default=15)
    p2.set_defaults(func=cmd_grid)

    p3 = sub.add_parser("exagg", help="exaggeration needed for each wall projection")
    p3.add_argument("--wall-width-mm", type=float, required=True)
    p3.add_argument("--cols", type=int, default=5)
    p3.add_argument("--rows", type=int, default=4)
    p3.add_argument("--label", default="plan")
    p3.set_defaults(func=cmd_exagg)

    p4 = sub.add_parser("compare", help="side-by-side pilot and final candidates")
    p4.set_defaults(func=cmd_compare)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
