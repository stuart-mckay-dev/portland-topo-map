#!/usr/bin/env python3
"""
color_cost.py -- Estimate AMS filament-change waste for the two colouring
strategies available to this project.

The headline result: on a heightfield, colouring by XY POSITION (roads, bike
routes) is enormously more expensive than colouring by Z HEIGHT (elevation
bands), because roads follow the terrain and therefore appear on nearly every
layer, forcing a tool change on nearly every layer.

Usage:
  python3 color_cost.py --tile-height-mm 50.8 --colors 4
  python3 color_cost.py --tile-height-mm 203.2 --colors 4 --flush-mm3 300
  python3 color_cost.py --sweep
"""

from __future__ import annotations
import argparse

DENSITY_G_CM3 = 1.24

# Bambu Studio computes flush volume per ORDERED colour pair; it depends
# strongly on how far apart the two colours are. Verify your own number by
# slicing a two-colour test and reading the reported flush total.
FLUSH_LOW = 130     # similar colours, tuned-down matrix
FLUSH_TYPICAL = 300 # mixed palette, stock matrix
FLUSH_HIGH = 700    # black <-> white, stock matrix


def xy_colour_cost(height_mm, layer_mm, n_colors, flush_mm3, road_layer_frac=1.0):
    """Roads/bike routes: colour varies by XY, so most layers need changes."""
    layers = height_mm / layer_mm
    changes_per_layer = max(0, n_colors - 1)
    total_changes = layers * changes_per_layer * road_layer_frac
    waste_mm3 = total_changes * flush_mm3
    return layers, total_changes, waste_mm3


def z_band_cost(n_bands, flush_mm3):
    """Elevation banding: colour varies by Z only, one change per band edge."""
    total_changes = max(0, n_bands - 1)
    return total_changes, total_changes * flush_mm3


def g(mm3):
    return mm3 / 1000.0 * DENSITY_G_CM3


def report(height_mm, layer_mm, n_colors, flush_mm3, n_bands, part_g=None):
    print()
    print("=" * 70)
    print(f"  Tile height {height_mm:.1f}mm | layer {layer_mm}mm | "
          f"{n_colors} colours | flush {flush_mm3} mm3/change")
    print("=" * 70)

    layers, changes, waste = xy_colour_cost(height_mm, layer_mm, n_colors, flush_mm3)
    print(f"\n  STRATEGY A -- colour roads/bike routes by XY position")
    print(f"    layers in tile          {layers:>12,.0f}")
    print(f"    tool changes            {changes:>12,.0f}")
    print(f"    purge waste             {waste/1000:>12,.0f} cm3   "
          f"({g(waste):,.0f} g)")
    if part_g:
        print(f"    waste / part mass       {g(waste)/part_g:>12,.1f} x")

    bchanges, bwaste = z_band_cost(n_bands, flush_mm3)
    print(f"\n  STRATEGY B -- colour by elevation band (Z only), {n_bands} bands")
    print(f"    tool changes            {bchanges:>12,.0f}")
    print(f"    purge waste             {bwaste/1000:>12,.2f} cm3   "
          f"({g(bwaste):,.1f} g)")

    if bwaste > 0:
        print(f"\n  Strategy A costs {waste/bwaste:,.0f}x more filament in purge alone.")
    print()


def sweep():
    print()
    print("Purge waste per tile, STRATEGY A (XY road colour), 0.2mm layers")
    print("grams of wasted filament, by tile height and palette size\n")
    heights = [25.4, 50.8, 76.2, 101.6, 152.4, 203.2]
    print(f"{'tile H':>10} {'2 col':>10} {'3 col':>10} {'4 col':>10} {'6 col':>10}")
    print("-" * 54)
    for h in heights:
        row = f'{h:>7.1f}mm'
        for c in [2, 3, 4, 6]:
            _, _, w = xy_colour_cost(h, 0.2, c, FLUSH_TYPICAL)
            row += f" {g(w):>9,.0f}"
        print(row)
    print(f"\n(at {FLUSH_TYPICAL} mm3/change; a tuned-down matrix at {FLUSH_LOW} "
          f"cuts these by {100*(1-FLUSH_LOW/FLUSH_TYPICAL):.0f}%)")

    print("\n\nPurge waste per tile, STRATEGY B (elevation bands)\n")
    print(f"{'bands':>10} {'grams':>10}")
    print("-" * 22)
    for b in [3, 4, 6, 8, 12, 16]:
        _, w = z_band_cost(b, FLUSH_TYPICAL)
        print(f"{b:>10} {g(w):>10.1f}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile-height-mm", type=float, default=50.8)
    ap.add_argument("--layer-mm", type=float, default=0.2)
    ap.add_argument("--colors", type=int, default=4)
    ap.add_argument("--flush-mm3", type=int, default=FLUSH_TYPICAL)
    ap.add_argument("--bands", type=int, default=6)
    ap.add_argument("--part-g", type=float, default=210.0,
                    help="mass of the tile itself, for the ratio")
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()
    if a.sweep:
        sweep()
    else:
        report(a.tile_height_mm, a.layer_mm, a.colors, a.flush_mm3, a.bands, a.part_g)


if __name__ == "__main__":
    main()
