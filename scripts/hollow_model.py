#!/usr/bin/env python3
"""
hollow_model.py -- Compare strategies for what goes UNDER the terrain surface.

The question: at high vertical exaggeration a tile is mostly structural filler
below the terrain. How should that volume be built?

Strategies modelled
-------------------
  SOLID       Sparse infill from the build plate up to the terrain. Baseline.
  SHELL_SUP   Constant-thickness shell following the terrain, perimeter walls
              only, open bottom, tear-away support filling the void.
  RIB_BOX     Hollow ribbed box from the plate up to the tile's LOWEST terrain
              point, capped with a flat ceiling that bridges between ribs.
              Solid infill above that. No support anywhere.
  RIB_SHELL   Ribs run from the plate all the way up to the underside of a
              terrain-following shell. No ceiling, no support, open bottom.

Everything is modelled as extruded-volume components rather than a blanket
"solid fraction", so the strategies can be compared honestly.

Usage
-----
  python3 hollow_model.py                       # all archetypes, default config
  python3 hollow_model.py --relief-mm 193.2 --shell-mm 12.7
  python3 hollow_model.py --shell-sweep
  python3 hollow_model.py --rib-sweep
  python3 hollow_model.py --overhang

No dependencies.
"""

from __future__ import annotations
import argparse
import math
from dataclasses import dataclass

MM_PER_INCH = 25.4
DENSITY_G_CM3 = 1.24

# ---------------------------------------------------------------------------
# PROCESS CONSTANTS -- Bambu X1C, 0.4mm nozzle, PLA
# ---------------------------------------------------------------------------
LAYER_MM = 0.20
EXTRUSION_W = 0.42
WALL_LOOPS = 3
WALL_T = WALL_LOOPS * EXTRUSION_W        # 1.26 mm
TOP_LAYERS = 5
BOTTOM_LAYERS = 4
INFILL = 0.15                            # sparse infill fraction
SHELL_INFILL = 0.25                      # denser inside the terrain shell

SUPPORT_DENSITY = 0.12
INTERFACE_LAYERS = 3
INTERFACE_DENSITY = 0.70

# The tile's underside faces the wall and is never seen. That means support
# under it can be far lighter than a cosmetic surface would need, and the
# shell's own bottom skin can be thinner. These two knobs dominate the result.
CFG = {
    "support_density": SUPPORT_DENSITY,
    "interface_layers": INTERFACE_LAYERS,
    "shell_bottom_layers": BOTTOM_LAYERS,
}

RIB_T = 4 * EXTRUSION_W                  # 1.68 mm, 4 extrusions wide
RIB_SPACING = 30.0
CEILING_LAYERS = 4                       # solid layers bridging between ribs

# Terrain is not flat, so surface skins cover more area than the footprint.
SURFACE_FACTOR = 1.15

# Throughput. Support and ribs involve far more travel per unit volume.
RATE_CM3_HR = 14.0
SUPPORT_TIME_MULT = 1.35
RIB_TIME_MULT = 1.25


@dataclass
class Tile:
    name: str
    w: float          # mm
    h: float          # mm
    n_min: float      # normalised elevation, 0..1 across the PROJECT range
    n_mean: float
    n_max: float

    @property
    def area(self):
        return self.w * self.h

    @property
    def perim(self):
        return 2 * (self.w + self.h)


@dataclass
class Result:
    strategy: str
    part_mm3: float
    waste_mm3: float
    hours: float
    bed_contact_mm2: float
    needs_support: bool
    support_removable: bool
    notes: str

    @property
    def part_g(self):
        return self.part_mm3 / 1000 * DENSITY_G_CM3

    @property
    def waste_g(self):
        return self.waste_mm3 / 1000 * DENSITY_G_CM3

    @property
    def total_g(self):
        return self.part_g + self.waste_g


def _skins(area):
    top = area * SURFACE_FACTOR * TOP_LAYERS * LAYER_MM
    bot = area * BOTTOM_LAYERS * LAYER_MM
    return top, bot


def solid(t: Tile, base, relief, **kw) -> Result:
    H = base + relief * t.n_mean
    top, bot = _skins(t.area)
    walls = t.perim * H * WALL_T
    interior = max(0.0, t.area * H - walls - top - bot)
    part = walls + top + bot + interior * INFILL
    return Result("SOLID", part, 0.0, part / 1000 / RATE_CM3_HR,
                  t.area, False, True,
                  "baseline; stiff; max bed adhesion")


def shell_sup(t: Tile, base, relief, shell_mm, **kw) -> Result:
    H = base + relief * t.n_mean
    shell = min(shell_mm, H)
    void = max(0.0, H - shell)

    top, _ = _skins(t.area)
    # the shell gets its own bottom skin -- an internal ceiling over support
    sbl = CFG["shell_bottom_layers"]
    shell_bot = t.area * SURFACE_FACTOR * sbl * LAYER_MM
    shell_core = max(0.0, t.area * shell - top - shell_bot)
    walls = t.perim * H * WALL_T
    part = walls + top + shell_bot + shell_core * SHELL_INFILL

    il = CFG["interface_layers"]
    sd = CFG["support_density"]
    sup_body = t.area * max(0.0, void - il * LAYER_MM) * sd
    sup_iface = t.area * il * LAYER_MM * INTERFACE_DENSITY
    waste = sup_body + sup_iface

    hrs = (part / 1000 / RATE_CM3_HR) + (waste / 1000 / RATE_CM3_HR * SUPPORT_TIME_MULT)
    # the support columns also sit on the plate and help hold the tile down
    bed = t.perim * WALL_T + t.area * sd
    return Result("SHELL_SUP", part, waste, hrs, bed, True, True,
                  "open bottom = support reachable; needs a brim")


def rib_box(t: Tile, base, relief, shell_mm, rib_spacing, **kw) -> Result:
    """Hollow ribbed box up to the tile's lowest terrain point, then solid."""
    H = base + relief * t.n_mean
    box_h = max(0.0, base + relief * t.n_min - CEILING_LAYERS * LAYER_MM)
    above = max(0.0, H - box_h)

    walls = t.perim * H * WALL_T
    n_x = max(0, int(t.w // rib_spacing) - 1)
    n_y = max(0, int(t.h // rib_spacing) - 1)
    rib_len = n_x * t.h + n_y * t.w
    ribs = rib_len * RIB_T * box_h
    ceiling = t.area * CEILING_LAYERS * LAYER_MM if box_h > 0 else 0.0

    top, _ = _skins(t.area)
    interior = max(0.0, t.area * above - top)
    part = walls + ribs + ceiling + top + interior * INFILL

    hrs = ((part - ribs) / 1000 / RATE_CM3_HR) + (ribs / 1000 / RATE_CM3_HR * RIB_TIME_MULT)
    return Result("RIB_BOX", part, 0.0, hrs,
                  t.perim * WALL_T + rib_len * RIB_T, False, True,
                  f"no support; flat ceiling bridges {rib_spacing:.0f}mm")


def rib_shell(t: Tile, base, relief, shell_mm, rib_spacing, **kw) -> Result:
    """Ribs from the plate to the underside of a terrain-following shell."""
    H = base + relief * t.n_mean
    shell = min(shell_mm, H)
    rib_h = max(0.0, H - shell)

    walls = t.perim * H * WALL_T
    n_x = max(0, int(t.w // rib_spacing) - 1)
    n_y = max(0, int(t.h // rib_spacing) - 1)
    rib_len = n_x * t.h + n_y * t.w
    ribs = rib_len * RIB_T * rib_h

    top, _ = _skins(t.area)
    shell_bot = t.area * SURFACE_FACTOR * CFG["shell_bottom_layers"] * LAYER_MM
    shell_core = max(0.0, t.area * shell - top - shell_bot)
    part = walls + ribs + top + shell_bot + shell_core * SHELL_INFILL

    hrs = ((part - ribs) / 1000 / RATE_CM3_HR) + (ribs / 1000 / RATE_CM3_HR * RIB_TIME_MULT)
    return Result("RIB_SHELL", part, 0.0, hrs,
                  t.perim * WALL_T + rib_len * RIB_T, False, True,
                  f"no support; shell bridges {rib_spacing:.0f}mm between ribs")


STRATEGIES = [solid, shell_sup, rib_box, rib_shell]


def run(t: Tile, base, relief, shell_mm, rib_spacing, n_tiles=None):
    return [f(t, base, relief, shell_mm=shell_mm, rib_spacing=rib_spacing)
            for f in STRATEGIES]


def print_tile(t: Tile, base, relief, shell_mm, rib_spacing):
    rs = run(t, base, relief, shell_mm, rib_spacing)
    baseline = rs[0]
    Hmean = base + relief * t.n_mean
    Hmin = base + relief * t.n_min
    Hmax = base + relief * t.n_max

    print()
    print("=" * 78)
    print(f"  {t.name}   {t.w:.1f} x {t.h:.1f} mm")
    print(f"  terrain Z: min {Hmin:.1f}  mean {Hmean:.1f}  max {Hmax:.1f} mm")
    print("=" * 78)
    print(f"  {'strategy':<11} {'part g':>8} {'waste g':>8} {'total g':>8} "
          f"{'vs solid':>9} {'hours':>7} {'bed mm2':>9} {'support':>8}")
    print("  " + "-" * 74)
    for r in rs:
        delta = (r.total_g / baseline.total_g - 1) * 100
        sup = "YES" if r.needs_support else "no"
        print(f"  {r.strategy:<11} {r.part_g:>8.0f} {r.waste_g:>8.0f} "
              f"{r.total_g:>8.0f} {delta:>+8.0f}% {r.hours:>7.1f} "
              f"{r.bed_contact_mm2:>9,.0f} {sup:>8}")
    print("  " + "-" * 74)
    for r in rs:
        print(f"  {r.strategy:<11} {r.notes}")
    print()


# A 5x4 grid over Portland is mostly low ground. Placeholder distribution --
# replace with real counts from `python3 scripts/tile_heights.py --stats`.
BUILD_MIX = [("flats", 11), ("mixed", 6), ("hills", 3)]


def cmd_build(a):
    ts = {"flats": tiles(a.tile_w, a.tile_h)[0],
          "mixed": tiles(a.tile_w, a.tile_h)[1],
          "hills": tiles(a.tile_w, a.tile_h)[2]}
    print("\n" + "=" * 78)
    print("  WHOLE BUILD, 20 tiles with a realistic height mix")
    print(f"  {BUILD_MIX[0][1]} flats + {BUILD_MIX[1][1]} mixed + "
          f"{BUILD_MIX[2][1]} hills   (placeholder -- see tile_heights.py)")
    print("=" * 78)
    totals = {}
    for i, f in enumerate(STRATEGIES):
        g = h = w = 0.0
        for key, n in BUILD_MIX:
            r = f(ts[key], a.base_mm, a.relief_mm,
                  shell_mm=a.shell_mm, rib_spacing=a.rib_spacing)
            g += r.part_g * n; w += r.waste_g * n; h += r.hours * n
        totals[f.__name__] = (g, w, h)
    b = totals["solid"]
    print(f"  {'strategy':<12} {'kg part':>9} {'kg waste':>9} {'kg total':>9} "
          f"{'vs solid':>9} {'hours':>8} {'days':>7}")
    print("  " + "-" * 74)
    for f in STRATEGIES:
        g, w, h = totals[f.__name__]
        tot = (g + w) / 1000
        base = (b[0] + b[1]) / 1000
        print(f"  {f.__name__.upper():<12} {g/1000:>9.2f} {w/1000:>9.2f} "
              f"{tot:>9.2f} {100*(tot/base-1):>+8.0f}% {h:>8.0f} {h/24:>7.1f}")
    print()
    print("  BEST-OF: pick the cheapest strategy per tile")
    g = w = h = 0.0
    picks = []
    for key, n in BUILD_MIX:
        rs = [f(ts[key], a.base_mm, a.relief_mm, shell_mm=a.shell_mm,
                rib_spacing=a.rib_spacing) for f in STRATEGIES]
        best = min(rs, key=lambda r: r.total_g)
        picks.append((key, n, best.strategy, best.total_g))
        g += best.part_g * n; w += best.waste_g * n; h += best.hours * n
    for key, n, name, tg in picks:
        print(f"    {n:>2} x {key:<7} -> {name:<11} {tg:>6.0f} g each")
    tot = (g + w) / 1000
    base = (b[0] + b[1]) / 1000
    print(f"  {'MIXED':<12} {g/1000:>9.2f} {w/1000:>9.2f} {tot:>9.2f} "
          f"{100*(tot/base-1):>+8.0f}% {h:>8.0f} {h/24:>7.1f}")
    print()


def cmd_crossover(a):
    print("\nAt what tile height does hollowing start to pay?\n")
    print("Sweeping mean terrain height for one tile, all strategies.\n")
    print(f"{'mean Z mm':>10} {'SOLID g':>9} {'SHELL_SUP':>10} {'RIB_BOX':>9} "
          f"{'RIB_SHELL':>10}   {'winner':>10}")
    print("-" * 70)
    for hmm in [15, 20, 25, 30, 40, 50, 70, 100, 140, 190]:
        nm = (hmm - a.base_mm) / a.relief_mm
        t = Tile("probe", a.tile_w, a.tile_h, max(0.0, nm * 0.35), nm,
                 min(1.0, nm * 2.0))
        rs = [f(t, a.base_mm, a.relief_mm, shell_mm=a.shell_mm,
                rib_spacing=a.rib_spacing) for f in STRATEGIES]
        win = min(rs, key=lambda r: r.total_g)
        print(f"{hmm:>10.0f} " + " ".join(f"{r.total_g:>9.0f}" for r in rs)
              + f"   {win.strategy:>10}")
    print()


def cmd_support_sweep(a):
    print("\nSHELL_SUP is only worth it if support is CHEAP.")
    print("The underside faces the wall, so it can be: nobody will ever see it.\n")
    t = tiles(a.tile_w, a.tile_h)[2]
    base_g = solid(t, a.base_mm, a.relief_mm).total_g
    print(f"West Hills tile, solid baseline = {base_g:.0f} g\n")
    print(f"{'support %':>10} {'iface layers':>13} {'part g':>8} {'waste g':>9} "
          f"{'total g':>9} {'vs solid':>9}")
    print("-" * 62)
    for sd in [0.12, 0.08, 0.05, 0.03]:
        for il in [3, 1, 0]:
            CFG["support_density"] = sd
            CFG["interface_layers"] = il
            r = shell_sup(t, a.base_mm, a.relief_mm, shell_mm=a.shell_mm,
                          rib_spacing=a.rib_spacing)
            print(f"{sd:>9.0%} {il:>13} {r.part_g:>8.0f} {r.waste_g:>9.0f} "
                  f"{r.total_g:>9.0f} {100*(r.total_g/base_g-1):>+8.0f}%")
    CFG["support_density"] = SUPPORT_DENSITY
    CFG["interface_layers"] = INTERFACE_LAYERS
    print("\n  Sparse infill at 15% and tear-away support at 12% cost almost")
    print("  the same. Support only wins once you drop it to ~5% or below AND")
    print("  cut the interface layers -- both safe on an invisible underside.")
    print()


def cmd_default(a):
    base, relief = a.base_mm, a.relief_mm
    print(f"\nConfiguration: base {base}mm, full-range relief {relief}mm "
          f"(peak tile {base+relief:.1f}mm tall)")
    print(f"shell {a.shell_mm}mm | ribs {RIB_T:.2f}mm @ {a.rib_spacing:.0f}mm "
          f"| infill {INFILL:.0%} | support {SUPPORT_DENSITY:.0%}")
    for t in tiles(a.tile_w, a.tile_h):
        print_tile(t, base, relief, a.shell_mm, a.rib_spacing)

    print("=" * 78)
    print("  WHOLE BUILD (20 tiles, using the mixed archetype as the average)")
    print("=" * 78)
    mixed = tiles(a.tile_w, a.tile_h)[1]
    rs = run(mixed, base, relief, a.shell_mm, a.rib_spacing)
    b = rs[0]
    print(f"  {'strategy':<11} {'kg part':>9} {'kg waste':>9} {'kg total':>9} "
          f"{'saved kg':>9} {'hours':>8} {'saved h':>8}")
    print("  " + "-" * 74)
    for r in rs:
        print(f"  {r.strategy:<11} {r.part_g*20/1000:>9.1f} "
              f"{r.waste_g*20/1000:>9.1f} {r.total_g*20/1000:>9.1f} "
              f"{(b.total_g-r.total_g)*20/1000:>+9.1f} {r.hours*20:>8.0f} "
              f"{(b.hours-r.hours)*20:>+8.0f}")
    print()


def tiles(w, h):
    return [
        Tile("FLATS TILE  (Columbia bottomland / inner eastside)", w, h,
             0.005, 0.025, 0.080),
        Tile("MIXED TILE  (Mt Tabor / Alameda Ridge)", w, h,
             0.020, 0.120, 0.350),
        Tile("WEST HILLS TILE  (contains the 362m high point)", w, h,
             0.165, 0.450, 1.000),
    ]


def cmd_shell_sweep(a):
    print("\nRIB_SHELL total grams vs shell thickness "
          f"(relief {a.relief_mm}mm, ribs @ {a.rib_spacing:.0f}mm)\n")
    ts = tiles(a.tile_w, a.tile_h)
    hdr = f"{'shell mm':>10}" + "".join(f"{t.name.split()[0]:>14}" for t in ts)
    print(hdr); print("-" * len(hdr))
    for s in [3, 4, 6, 8, 10, 12.7, 16, 20]:
        row = f"{s:>10.1f}"
        for t in ts:
            r = rib_shell(t, a.base_mm, a.relief_mm, shell_mm=s,
                          rib_spacing=a.rib_spacing)
            row += f"{r.total_g:>14.0f}"
        print(row)
    print("\nSolid baseline for comparison:")
    row = f"{'--':>10}"
    for t in ts:
        row += f"{solid(t, a.base_mm, a.relief_mm).total_g:>14.0f}"
    print(row)
    print()


def cmd_rib_sweep(a):
    print(f"\nRIB_SHELL: rib spacing vs grams and max unsupported bridge span")
    print(f"(shell {a.shell_mm}mm, relief {a.relief_mm}mm, mixed tile)\n")
    t = tiles(a.tile_w, a.tile_h)[1]
    print(f"{'spacing mm':>12} {'grams':>9} {'bridge span':>13} {'verdict':>28}")
    print("-" * 66)
    for s in [15, 20, 25, 30, 40, 50, 70, 100]:
        r = rib_shell(t, a.base_mm, a.relief_mm, shell_mm=a.shell_mm, rib_spacing=s)
        if s <= 30:
            v = "safe, standard bridging"
        elif s <= 50:
            v = "ok on flat spans, sag on slopes"
        else:
            v = "expect sag / droop"
        print(f"{s:>12.0f} {r.total_g:>9.0f} {s:>11.0f}mm {v:>28}")
    print()


def cmd_overhang(a):
    print("\n=== Can the shell underside print WITHOUT support? ===\n")
    print("A hollow shell's underside has the same slope as the terrain above.")
    print("For a downward-facing surface, overhang from vertical = 90 - slope.")
    print("FDM holds to ~45 deg from vertical, so the surface must be at")
    print("least 45 deg from horizontal to be self-supporting.\n")
    print("    self-supporting  <=>  V * tan(true_slope) >= 1")
    print("                     <=>  true grade >= 100/V percent\n")
    print(f"{'exagg':>8} {'min true grade':>16} {'what that means in Portland':>44}")
    print("-" * 70)
    for V in [2, 3.48, 5, 8, 12.15, 16.48]:
        g = 100.0 / V
        if g > 50: m = "essentially nothing qualifies"
        elif g > 25: m = "only cliffs and quarry faces"
        elif g > 12: m = "steep Forest Park slopes only"
        elif g > 8: m = "West Hills + Mt Tabor flanks"
        else: m = "most genuine hillside; flats still fail"
        print(f"{V:>7.2f}x {g:>15.1f}% {m:>44}")
    print()
    print("Portland true grades, and the exaggeration each needs:\n")
    for name, gr in [("Columbia/Willamette floodplain", 0.3),
                     ("Inner eastside street grid", 1.0),
                     ("Alameda Ridge face", 8.0),
                     ("Mt Tabor flanks", 12.0),
                     ("West Hills streets", 15.0),
                     ("Forest Park natural slopes", 35.0),
                     ("Rocky Butte quarry face", 80.0)]:
        need = 100.0 / gr
        ok = "never realistic" if need > 25 else f"V >= {need:.1f}x"
        print(f"  {name:<32} ~{gr:>5.1f}%   {ok}")
    print()
    print("  >>> The flats are the PROBLEM, not the hills. Most of Portland's")
    print("      area is under 2% grade, so a terrain-following hollow ceiling")
    print("      needs support exactly where the map is flattest -- which is")
    print("      also where the void is shallowest and saves the least.")
    print()


def cmd_thinning(a):
    print("\nSHELL THINNING ON SLOPES\n")
    print("If the shell is generated by offsetting the terrain DOWN IN Z by t,")
    print("its true thickness measured perpendicular to the surface is only")
    print("t * cos(slope). On steep terrain the shell gets dangerously thin --")
    print("and steep terrain is exactly where the tile is tallest and most")
    print("needs the strength.\n")
    print(f"nominal Z-offset shell = {a.shell_mm:.1f} mm\n")
    print(f"{'terrain slope':>14} {'true thickness':>16} {'verdict':>28}")
    print("-" * 62)
    for deg in [0, 15, 30, 45, 60, 68, 75, 80, 85]:
        t_true = a.shell_mm * math.cos(math.radians(deg))
        if t_true < 3 * EXTRUSION_W:
            v = "BELOW 3 WALL LINES -- fails"
        elif t_true < 2.0:
            v = "too thin, no infill fits"
        elif t_true < 5.0:
            v = "thin but printable"
        else:
            v = "fine"
        print(f"{deg:>13}d {t_true:>15.2f}mm {v:>28}")
    print()
    print("  FIX: use a true perpendicular offset (Blender Solidify with")
    print("  'Even Thickness' / complex mode, or a Shrinkwrap-based offset)")
    print("  rather than a plain Z displacement. If you must use a Z offset,")
    print("  size it for the steepest slope you care about, not the average.")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-mm", type=float, default=10.0)
    ap.add_argument("--relief-mm", type=float, default=193.2,
                    help="full-range relief; 193.2 = the 8-inch case")
    ap.add_argument("--shell-mm", type=float, default=12.7, help="0.5 inch")
    ap.add_argument("--rib-spacing", type=float, default=RIB_SPACING)
    ap.add_argument("--tile-w", type=float, default=180.6)
    ap.add_argument("--tile-h", type=float, default=200.0)
    ap.add_argument("--shell-sweep", action="store_true")
    ap.add_argument("--rib-sweep", action="store_true")
    ap.add_argument("--overhang", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--crossover", action="store_true")
    ap.add_argument("--support-sweep", action="store_true")
    ap.add_argument("--thinning", action="store_true")
    ap.add_argument("--support-density", type=float, default=None)
    ap.add_argument("--interface-layers", type=int, default=None)
    ap.add_argument("--shell-bottom-layers", type=int, default=None)
    a = ap.parse_args()
    if a.support_density is not None: CFG["support_density"] = a.support_density
    if a.interface_layers is not None: CFG["interface_layers"] = a.interface_layers
    if a.shell_bottom_layers is not None:
        CFG["shell_bottom_layers"] = a.shell_bottom_layers
    if a.overhang: cmd_overhang(a)
    elif a.build: cmd_build(a)
    elif a.crossover: cmd_crossover(a)
    elif a.support_sweep: cmd_support_sweep(a)
    elif a.thinning: cmd_thinning(a)
    elif a.shell_sweep: cmd_shell_sweep(a)
    elif a.rib_sweep: cmd_rib_sweep(a)
    else: cmd_default(a)


if __name__ == "__main__":
    main()
