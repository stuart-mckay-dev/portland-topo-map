# 01 — Scale, Tiling and Vertical Exaggeration

All numbers in this document are produced by `scripts/topo_params.py`. The
command that generated each block is shown above it. **Do not hand-edit these
tables** — regenerate them.

> Regenerated 2026-08-24 after the bbox was recentred and resized to
> 29,000 × 25,000 m, and again after `MEAN_ELEV_FRACTION` was measured from
> the boundary-masked DEM (**0.1958**), and again on 2026-08-24 when the
> base slab went 10 mm -> **4 mm**. See `docs/DECISIONS.md`.

## The three linked quantities

Everything follows from the finished wall width:

```
scale_denominator = 29,000,000 mm of ground / wall_width_mm
true_relief_mm    = 361,810 mm of elevation / scale_denominator
exaggeration      = desired_relief_mm / true_relief_mm
Z_factor          = (1000 / scale_denominator) * exaggeration
```

`Z_factor` is the number you actually type into Blender's Displace modifier
strength or QGIS band arithmetic: **model millimetres of height per real metre
of elevation.**

Note that "projection off the wall" in the tables below is *total* height and
therefore **includes the 4 mm base slab**. Relief is total minus 4.

## Why Portland needs vertical exaggeration

Portland is 29.0 km wide and 362 m tall. That is a ratio of about 80:1. At true
1:1 scale on a 900 mm wall, the entire elevation range — river to the highest
point in the West Hills — is **11.2 mm**. Against a 900 mm width, that reads as
essentially flat.

Exaggeration is therefore mandatory, and the only question is how much. Note
the trade: exaggeration is a budget item, not a free style knob. Relief drives
volume, and volume drives both filament mass and print hours roughly linearly.

There is one benefit beyond looks: exaggeration also *reduces visible layer
terracing*. Terracing is worst on shallow slopes, where a 0.2 mm layer step
spreads across many millimetres of XY. Portland's flats are exactly this case.
Pushing exaggeration up steepens those slopes and tightens the terraces.

## Choosing the grid

The bbox aspect is now **1.1600:1**. That is very nearly 7:6 (1.1667), so a
**7 × 6 grid produces almost perfectly square tiles** — the squarest available
under the 200 mm cap. Before the recentring the aspect was 1.1288 and the
squarest grid was 9 × 8; the change is a real improvement, because 7 × 6 is 42
tiles rather than 72.

```
$ python3 scripts/topo_params.py grid --max-tile-mm 200 --top 10

Candidate grids with a max tile edge of 200mm, ranked by tile squareness:

    grid  tiles         tile mm  aspect         wall mm         wall in        scale  1x relief
-----------------------------------------------------------------------------------------------
7x6          42   198.9x200.0     0.994    1392x1200      54.8"x47.2"   1:    20,833     17.37mm
8x7          56   200.0x197.0     1.015    1600x1379      63.0"x54.3"   1:    18,125     19.96mm
9x8          72   200.0x194.0     1.031    1800x1552      70.9"x61.1"   1:    16,111     22.46mm
6x5          30   193.3x200.0     0.967    1160x1000      45.7"x39.4"   1:    25,000     14.47mm
10x9          90   200.0x191.6     1.044    2000x1724      78.7"x67.9"   1:    14,500     24.95mm
5x4          20   185.6x200.0     0.928     928x800       36.5"x31.5"   1:    31,250     11.58mm
10x8          80   185.6x200.0     0.928    1856x1600      73.1"x63.0"   1:    15,625     23.16mm
9x7          63   180.4x200.0     0.902    1624x1400      63.9"x55.1"   1:    17,857     20.26mm
4x3          12   174.0x200.0     0.870     696x600       27.4"x23.6"   1:    41,667      8.68mm
8x6          48   174.0x200.0     0.870    1392x1200      54.8"x47.2"   1:    20,833     17.37mm

```

Square-ish tiles are not required — they are just easier to pack on the plate,
easier to handle, and less likely to warp asymmetrically. A 0.9 aspect (the
5×4 grid) is perfectly fine.

## Candidate configurations

```
$ python3 scripts/topo_params.py compare

PILOT CANDIDATES (small, fast, validates the whole pipeline)
  3x2     6 tiles    69.6x90.0  mm  wall 8.2"x7.1"    1: 138,889  @40mm tall: 13.82x   0.1kg     8h
  4x3    12 tiles    78.3x90.0  mm  wall 12.3"x10.6"   1:  92,593  @40mm tall:  9.21x   0.3kg    19h
  4x3    12 tiles    87.0x100.0 mm  wall 13.7"x11.8"   1:  83,333  @40mm tall:  8.29x   0.4kg    23h
  5x4    20 tiles    74.2x80.0  mm  wall 14.6"x12.6"   1:  78,125  @40mm tall:  7.77x   0.5kg    26h

FINAL CANDIDATES (200mm tiles)
  4x3    12 tiles   174.0x200.0 mm  wall 27.4"x23.6"   1:  41,667  2"= 5.39x ( 1.9kg  110h)  6"=17.09x ( 4.8kg  276h)
  4x4    16 tiles   200.0x172.4 mm  wall 31.5"x27.2"   1:  36,250  2"= 4.69x ( 2.5kg  145h)  6"=14.87x ( 6.3kg  365h)
  5x4    20 tiles   185.6x200.0 mm  wall 36.5"x31.5"   1:  31,250  2"= 4.04x ( 3.4kg  195h)  6"=12.82x ( 8.5kg  491h)
  6x5    30 tiles   193.3x200.0 mm  wall 45.7"x39.4"   1:  25,000  2"= 3.23x ( 5.3kg  305h)  6"=10.25x (13.3kg  767h)
  7x6    42 tiles   198.9x200.0 mm  wall 54.8"x47.2"   1:  20,833  2"= 2.69x ( 7.6kg  440h)  6"= 8.55x (19.2kg 1104h)

```

Read the final block carefully. The two columns on the right are the whole
argument: at a 5×4 grid, going from 2" to 6" of relief takes the build from
4.6 kg / 267 h to 9.8 kg / 562 h.

## What 8 inches actually costs

The owner's stated tolerance is up to 8" (203 mm) of projection. Here is what
each projection depth requires at the 5×4 grid:

```
$ python3 scripts/topo_params.py exagg --wall-width-mm 928 --cols 5 --rows 4

plan: 1:31,250, true relief 11.58mm

  total H off wall    exagg   Z factor   est kg  est hours
----------------------------------------------------------
   0.50" =   12.7mm    0.75x    0.0240     1.5        85
   0.75" =   19.0mm    1.30x    0.0416     1.8       103
   1.00" =   25.4mm    1.85x    0.0591     2.1       122
   1.25" =   31.8mm    2.40x    0.0767     2.4       140
   1.50" =   38.1mm    2.95x    0.0942     2.8       159
   2.00" =   50.8mm    4.04x    0.1293     3.4       195
   2.50" =   63.5mm    5.14x    0.1645     4.0       232
   3.00" =   76.2mm    6.24x    0.1996     4.7       269
   4.00" =  101.6mm    8.43x    0.2698     6.0       343
   5.00" =  127.0mm   10.62x    0.3400     7.2       417
   6.00" =  152.4mm   12.82x    0.4102     8.5       491
   7.00" =  177.8mm   15.01x    0.4804     9.8       565
   8.00" =  203.2mm   17.21x    0.5506    11.1       639

```

And at the 7×6 grid, which is now the squarest option:

```
$ python3 scripts/topo_params.py exagg --wall-width-mm 1392 --cols 7 --rows 6

plan: 1:20,833, true relief 17.37mm

  total H off wall    exagg   Z factor   est kg  est hours
----------------------------------------------------------
   0.50" =   12.7mm    0.50x    0.0240     3.3       191
   0.75" =   19.0mm    0.87x    0.0416     4.0       232
   1.00" =   25.4mm    1.23x    0.0591     4.7       274
   1.25" =   31.8mm    1.60x    0.0767     5.5       315
   1.50" =   38.1mm    1.96x    0.0942     6.2       357
   2.00" =   50.8mm    2.69x    0.1293     7.6       440
   2.50" =   63.5mm    3.43x    0.1645     9.1       523
   3.00" =   76.2mm    4.16x    0.1996    10.5       606
   4.00" =  101.6mm    5.62x    0.2698    13.4       772
   5.00" =  127.0mm    7.08x    0.3400    16.3       938
   6.00" =  152.4mm    8.55x    0.4102    19.2      1104
   7.00" =  177.8mm   10.01x    0.4804    22.1      1271
   8.00" =  203.2mm   11.47x    0.5506    24.9      1437

```

Four things to take from these tables:

1. **8" at the 5×4 scale means 16.7× exaggeration.** That is well past the
   point where terrain reads as terrain; the West Hills become a wall and
   Mt Tabor becomes a spike. Physical-relief-map convention sits around 1.5–3×
   for regional maps and 3–6× for dramatic display pieces.
2. **The cost is not linear in perceived drama.** Going 2" → 8" quadruples the
   projection but only adds ~150% to filament, because most tiles are
   low-lying and the base slab dominates their volume (that was computed at the
   original 10 mm base; at 4 mm the relief carries proportionally more of it). The *time* cost is real
   though: +443 hours at 5×4.
3. **A bigger wall gets you the same relief for less exaggeration.** At 7×6,
   8" of projection needs **11.1×** rather than 16.7×, and 6" needs **8.2×**
   rather than 12.3×. If dramatic relief is the priority, buying it with wall
   area rather than with exaggeration produces a more natural-looking result.

   > **Correction, 2026-08-24.** An earlier revision of this document claimed
   > 8" at 7×6 needed "only ~8×". That conflated the 6" and 8" rows. The 8.2×
   > figure is the **6"** row. The error was propagated into `docs/DECISIONS.md`
   > and has been corrected there too.

4. **But wall area is the expensive axis in absolute terms.** 7×6 at 6" is
   22.0 kg and 1,266 hours, against 9.8 kg and 562 hours for 5×4 at 6". The
   *proportions* look better; the *bill* is more than double. Exaggeration
   buys drama cheaply and badly; wall area buys it expensively and well.

## Recommended starting point

Do not commit. Print the exaggeration ladder described in `docs/09-pilot-run.md`
and look at it on an actual wall. As a starting hypothesis:

- **2.5–4×** if the goal is a map that reads as accurate terrain.
- **5–8×** if the goal is sculptural drama and you accept the West Hills
  looking steeper than they are.
- **Above 10×** only with a specific artistic reason.

## Per-tile Z heights vary

Only the tile containing the West Hills high point needs the full height. A
tile covering the inner eastside flats might be 12 mm tall. Slice each tile to
its own bounding box rather than padding them all to a common height — it saves
a great deal of time and filament, and it is why the mass estimates above are
lower than a naive `footprint × peak height` calculation would suggest.

Run `scripts/tile_heights.py` after the DEM is tiled to get the real per-tile
maximum for the active configuration.

> With the boundary cut in play, perimeter tiles lose material and their
> estimates fall further. Do not re-derive the whole-build total until
> `tile_heights.py` has run against boundary-cut tiles.
