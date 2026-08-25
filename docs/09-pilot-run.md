# 09 — Phase 1 Pilot Run

> Numbers regenerated 2026-08-24 after the bbox resize and again after
> `MEAN_ELEV_FRACTION` was measured (0.1958). The front half of this run is written out step by step
> in `docs/11-pilot-runsheet.md`.

## Purpose

The pilot is **not a small version of the artwork**. It is a test of the
pipeline. Its job is to answer questions that cannot be answered on a screen,
before the final build commits several hundred machine-hours.

Questions the pilot must answer:

1. What vertical exaggeration actually looks right on a wall?
2. Do tile seams disappear, and is the shared-edge DEM cut correct?
3. At what groove depth and width do engraved roads read clearly?
4. Does paint-filling grooves work, and does it look better than AMS colour?
5. How long does a tile really take, and how much filament does it really use?
6. Does the registration/mounting scheme actually align?

## Recommended pilot configuration

A complete map of Portland at small scale — the whole city, all tiles, so that
seams, assembly and composition are genuinely tested.

```
$ python3 scripts/topo_params.py plan --tile-mm 90 --cols 4 --rows 3 \
      --label "PILOT 4x3 @ 90mm" --target-height-mm 40
==========================================================================
  PLAN: PILOT 4x3 @ 90mm
==========================================================================
  Grid                4 cols x 3 rows = 12 tiles
  Finished wall       313 x 270 mm   (12.3" x 10.6")
  Tile footprint      78.3 x 90.0 mm   (aspect 0.870)
  Ground per tile     7.25 x 8.33 km
  Horizontal scale    1 : 92,593
  1 mm of model       = 92.6 m of ground
  True (1x) relief    3.91 mm for the full 362 m range
  Base slab           4.0 mm under the lowest point

  VERTICAL EXAGGERATION
  ----------------------------------------------------------------------
   exagg    relief   total H  off wall   Z factor   g/tile  h/tile  total kg  total h
  ----------------------------------------------------------------------
    1.0x      3.9mm      7.9mm      0.3"    0.0108      12    0.7      0.1       8
    2.0x      7.8mm     11.8mm      0.5"    0.0216      14    0.8      0.2       9
    3.0x     11.7mm     15.7mm      0.6"    0.0324      15    0.9      0.2      11
    4.0x     15.6mm     19.6mm      0.8"    0.0432      17    1.0      0.2      12
    6.0x     23.4mm     27.4mm      1.1"    0.0648      21    1.2      0.3      15
    8.0x     31.3mm     35.3mm      1.4"    0.0864      25    1.4      0.3      17
   10.0x     39.1mm     43.1mm      1.7"    0.1080      29    1.6      0.3      20
   12.0x     46.9mm     50.9mm      2.0"    0.1296      32    1.9      0.4      22
  ----------------------------------------------------------------------
  Z factor = model mm of height per real metre of elevation.
            Multiply your DEM (in metres) by this in Blender/QGIS.

  >> To put the peak at exactly 40.0mm total (1.6") off the wall:
     vertical exaggeration = 9.213x
     Z factor              = 0.0995 mm per metre
     est. filament         = 0.3 kg over 12 tiles
     est. print time       = 19 h (0.8 days continuous)

```

**Why this configuration:**

- 12 tiles at 78.3 × 90 mm gang **six-up on one plate** (235 × 180 mm), so the
  whole pilot is **two print jobs**, not twelve.
- ~27 hours total and about half a kilogram of filament — a weekend, and a
  few dollars of PLA.
- The finished piece is ~12.3" × 10.6", big enough to hang up and live with for a
  week before deciding on the final.
- Every pipeline stage runs exactly as it will for the final. Nothing is
  skipped or simulated.

## Before the pilot: the exaggeration ladder

Do this first. It is one plate and it answers the biggest open question.

Pick **one** tile — the one containing the West Hills high point, since it has
the largest relief range — and print it four times at different exaggerations
on a single plate:

| Coupon | Exaggeration | Purpose |
|---|---|---|
| A | 2× | The "accurate" end |
| B | 4× | |
| C | 7× | |
| D | 11× | Approaching the drama end |

Print them, put them on the actual wall, at the actual viewing distance, under
the actual lighting, and look at them for a few days. Exaggeration is a
perceptual decision and it does not survive being made on a monitor.

Record the choice in `docs/DECISIONS.md`.

> Note the coupons should be at **pilot scale**, but exaggeration is
> scale-relative — a 4× tile looks the same shape at any size. What changes
> with scale is how much *detail* survives, which is what the full pilot tests.

## Pilot task list

- [ ] Download 3DEP 1 m DEM for the bbox; confirm units are metres
- [ ] Merge, void-fill, flatten water in QGIS
- [ ] Resample to pilot print resolution
- [ ] Normalise project-wide to 16-bit
- [ ] Cut the 4×3 tile grid with shared edge pixels
- [ ] Mask to the dissolved, simplified city-limits polygon (`docs/11` §8)
- [ ] Boolean-cut each tile to the boundary prism and re-check manifold
- [ ] Print the exaggeration ladder; choose a value; record it
- [ ] Pull street + bike vectors; build masks at three groove widths
- [ ] Blender: generate all 12 tiles via script
- [ ] Verify seam continuity on two adjacent tiles before printing anything
- [ ] Fusion: registration keys; print edge coupons and test the fit
- [ ] Slice two ganged plates; print
- [ ] Test paint-fill on one tile's grooves
- [ ] Test AMS elevation banding on one tile
- [ ] Dry-fit the full grid on a table; measure cumulative error
- [ ] Mount and live with it for a week
- [ ] Update `topo_params.py` constants with measured time/mass
- [ ] Record every decision in `docs/DECISIONS.md`

## What to measure and feed back

| Measurement | Feeds into |
|---|---|
| Actual grams per tile | `SOLID_FRACTION` in `topo_params.py` |
| Actual hours per tile | `PRINT_RATE_CM3_PER_HR` |
| Mean elevation from the DEM | `MEAN_ELEV_FRACTION` (run `scripts/dem_stats.py`) |
| Cumulative alignment error across the grid | registration clearance in Fusion |
| Groove depth that reads best | doc 07 parameters |
| Chosen exaggeration | everything |

Once these are calibrated, the final-phase estimates from `topo_params.py`
become trustworthy — and only then is it reasonable to commit to a wall size.

## Gate to Phase 2

Do not start the final until:

1. Wall locations are measured and a final dimension is chosen.
2. Exaggeration is chosen from physical coupons.
3. A pilot tile seam is judged acceptable.
4. `topo_params.py` constants are calibrated from real prints.
5. `docs/DECISIONS.md` records all of the above with dates.

---

## Measured tile slope distribution (2026-08-24)

Computed from the exported heightmaps at 10.04 m post spacing, with the
boundary cliff eroded 4 px so the mask edge does not pollute the gradient.
`terr>1mm` is the fraction of each tile whose terrace steps would be wider
than 1 mm at a 0.20 mm layer and 2.047x exaggeration — i.e. plainly visible.

```
tile                cover   median    p75    p90    <2%   >15%  terr>1mm
pdx_pilot_r01c01      57%     4.3%  28.5%  47.5%    38%    35%       60%
pdx_pilot_r01c02      57%    12.7%  28.0%  73.5%    17%    44%       42%
pdx_pilot_r01c03      33%    19.2%  45.1% 119.7%    27%    56%       37%
pdx_pilot_r02c01      28%    31.3%  42.2%  53.9%     5%    79%       13%
pdx_pilot_r02c02      95%     3.1%  15.4%  37.9%    38%    25%       70%
pdx_pilot_r02c03     100%     5.5%   9.8%  18.7%    15%    14%       75%
pdx_pilot_r02c04      72%     7.4%  13.7%  25.3%    11%    22%       62%
pdx_pilot_r03c02      84%    12.5%  21.7%  35.6%    10%    41%       39%
pdx_pilot_r03c03      60%     5.0%  10.6%  21.8%    17%    17%       73%
pdx_pilot_r03c04      47%     5.4%  19.1%  38.4%    20%    30%       61%
```

**Terracing is worst on gentle ground, not on the hills.** Step width is
`layer / (grade x exaggeration)`, so it grows as the slope flattens. On steep
ground the steps compress below the extrusion width and disappear into the
wall. `r02c01` is 79% steep and shows visible terracing on only 13% of its
area; `r02c03` is the reverse.

**The 0.4 mm nozzle is currently the resolution bottleneck, not the DEM.**

```
heightmap post spacing   10.04 m ground  =  0.109 mm model
0.4 nozzle, 0.42 mm bead  =  3.9 heightmap px  =  39 m of ground
0.2 nozzle, 0.21 mm bead  =  1.9 heightmap px  =  19 m of ground
```

A 0.4 mm bead smears roughly four source posts together. A 0.2 mm nozzle would
resolve detail that is genuinely present in the data and currently discarded.
It also makes Z terracing *more* visible, not less, because the visibility
floor drops from 0.42 mm to 0.21 mm. The two effects pull in opposite
directions. See `OPEN-QUESTIONS.md`.
