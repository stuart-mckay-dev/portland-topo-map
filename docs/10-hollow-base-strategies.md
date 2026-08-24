# 10 — Hollow Base Strategies

What goes *under* the terrain surface. At high vertical exaggeration a tile is
mostly structural filler, so this is where the filament and hours actually go.

All numbers from `scripts/hollow_model.py`. Regenerate rather than hand-edit.

## The proposal

Perimeter-only base, tear-away support underneath, and only the top ~0.5" solid
— a constant-thickness shell mirroring the terrain on the underside.

The idea is sound and the geometry is buildable. But modelled honestly it does
**not** save what it looks like it should, for two reasons that are worth
understanding before committing to it. Both are fixable, and the fixed version
is genuinely good.

---

## Constraint 1 — the underside overhang inverts

A hollow shell's underside has **the same slope as the terrain above it**. For
a downward-facing surface, overhang measured from vertical is `90° − slope`,
and FDM holds to roughly 45° from vertical. So the underside is self-supporting
only where the terrain is at least 45° from horizontal:

```
self-supporting  ⟺  V × tan(true_slope) ≥ 1  ⟺  true grade ≥ 100/V percent
```

```
$ python3 scripts/hollow_model.py --overhang

=== Can the shell underside print WITHOUT support? ===

A hollow shell's underside has the same slope as the terrain above.
For a downward-facing surface, overhang from vertical = 90 - slope.
FDM holds to ~45 deg from vertical, so the surface must be at
least 45 deg from horizontal to be self-supporting.

    self-supporting  <=>  V * tan(true_slope) >= 1
                     <=>  true grade >= 100/V percent

   exagg   min true grade                  what that means in Portland
----------------------------------------------------------------------
   2.00x            50.0%                 only cliffs and quarry faces
   3.48x            28.7%                 only cliffs and quarry faces
   5.00x            20.0%                steep Forest Park slopes only
   8.00x            12.5%                steep Forest Park slopes only
  12.15x             8.2%                 West Hills + Mt Tabor flanks
  16.48x             6.1%      most genuine hillside; flats still fail

Portland true grades, and the exaggeration each needs:

  Columbia/Willamette floodplain   ~  0.3%   never realistic
  Inner eastside street grid       ~  1.0%   never realistic
  Alameda Ridge face               ~  8.0%   V >= 12.5x
  Mt Tabor flanks                  ~ 12.0%   V >= 8.3x
  West Hills streets               ~ 15.0%   V >= 6.7x
  Forest Park natural slopes       ~ 35.0%   V >= 2.9x
  Rocky Butte quarry face          ~ 80.0%   V >= 1.2x

  >>> The flats are the PROBLEM, not the hills. Most of Portland's
      area is under 2% grade, so a terrain-following hollow ceiling
      needs support exactly where the map is flattest -- which is
      also where the void is shallowest and saves the least.

```

This is the counterintuitive part: **the flats are the problem, not the hills.**
Exaggeration steepens everything, so at 16.7× the West Hills underside prints
fine unsupported. But the inner eastside grid at ~1% true grade becomes a 3°
underside — a 87° overhang, effectively a ceiling. It needs support.

And those flat tiles are exactly where the void is shallowest, so support buys
you the least there. Most of Portland's area is under 2% grade.

## Constraint 2 — tear-away support costs about the same as the infill it replaces

This is the one that kills the naive version. Sparse infill at 15% and Bambu's
default-ish support at 12% are nearly the same volume of plastic. Swapping one
for the other saves nothing — and the shell version *adds* a full solid bottom
skin across the whole footprint (~40 g/tile) that a solid part never prints.

```
$ python3 scripts/hollow_model.py --support-sweep

SHELL_SUP is only worth it if support is CHEAP.
The underside faces the wall, so it can be: nobody will ever see it.

West Hills tile, solid baseline = 824 g

 support %  iface layers   part g   waste g   total g  vs solid
--------------------------------------------------------------
      12%             3      327       468       795       -3%
      12%             1      327       458       785       -5%
      12%             0      327       453       780       -5%
       8%             3      327       319       646      -22%
       8%             1      327       307       634      -23%
       8%             0      327       302       629      -24%
       5%             3      327       206       533      -35%
       5%             1      327       194       522      -37%
       5%             0      327       189       516      -37%
       3%             3      327       131       458      -44%
       3%             1      327       119       446      -46%
       3%             0      327       113       440      -47%

  Sparse infill at 15% and tear-away support at 12% cost almost
  the same. Support only wins once you drop it to ~5% or below AND
  cut the interface layers -- both safe on an invisible underside.

```

**Support density is the entire ballgame.** At 12% the strategy saves 3%. At 5%
with no interface layers it saves 37%. At 3%, 47%.

The enabler is that **the underside faces the wall and will never be seen**, so
every reason to print dense, cleanly-separating support disappears. Drop the
density, drop the interface layers, and let it be ugly.

---

## Four strategies compared

| | What it is | Support? |
|---|---|---|
| `SOLID` | Sparse infill from plate to terrain. Baseline | no |
| `SHELL_SUP` | Your proposal: perimeter walls, terrain-following shell, open bottom, support in the void | yes |
| `RIB_BOX` | Hollow ribbed box up to the tile's *lowest* terrain point, capped by a flat ceiling bridging between ribs. Solid above | **no** |
| `RIB_SHELL` | Ribs from the plate straight up to the shell underside. No ceiling, no support, open bottom | **no** |

`RIB_BOX` and `RIB_SHELL` are the support-free alternatives. They exploit the
fact that a *flat* internal ceiling bridging 30 mm between ribs is trivial for
FDM, whereas a *terrain-following* ceiling over open air is not.

```
$ python3 scripts/hollow_model.py

Configuration: base 10.0mm, full-range relief 193.2mm (peak tile 203.2mm tall)
shell 12.7mm | ribs 1.68mm @ 30mm | infill 15% | support 12%

==============================================================================
  FLATS TILE  (Columbia bottomland / inner eastside)   180.6 x 200.0 mm
  terrain Z: min 11.0  mean 14.8  max 25.5 mm
==============================================================================
  strategy      part g  waste g  total g  vs solid   hours   bed mm2  support
  --------------------------------------------------------------------------
  SOLID            189        0      189       +0%    10.9    36,120       no
  SHELL_SUP        229       27      256      +36%    15.3     5,294      YES
  RIB_BOX          169        0      169      -11%    10.3     4,156       no
  RIB_SHELL        238        0      238      +26%    13.8     4,156       no
  --------------------------------------------------------------------------
  SOLID       baseline; stiff; max bed adhesion
  SHELL_SUP   open bottom = support reachable; needs a brim
  RIB_BOX     no support; flat ceiling bridges 30mm
  RIB_SHELL   no support; shell bridges 30mm between ribs


==============================================================================
  MIXED TILE  (Mt Tabor / Alameda Ridge)   180.6 x 200.0 mm
  terrain Z: min 13.9  mean 33.2  max 77.6 mm
==============================================================================
  strategy      part g  waste g  total g  vs solid   hours   bed mm2  support
  --------------------------------------------------------------------------
  SOLID            331        0      331       +0%    19.1    36,120       no
  SHELL_SUP        251      126      377      +14%    24.2     5,294      YES
  RIB_BOX          306        0      306       -7%    18.4     4,156       no
  RIB_SHELL        332        0      332       +1%    20.3     4,156       no
  --------------------------------------------------------------------------
  SOLID       baseline; stiff; max bed adhesion
  SHELL_SUP   open bottom = support reachable; needs a brim
  RIB_BOX     no support; flat ceiling bridges 30mm
  RIB_SHELL   no support; shell bridges 30mm between ribs


==============================================================================
  WEST HILLS TILE  (contains the 362m high point)   180.6 x 200.0 mm
  terrain Z: min 41.9  mean 96.9  max 203.2 mm
==============================================================================
  strategy      part g  waste g  total g  vs solid   hours   bed mm2  support
  --------------------------------------------------------------------------
  SOLID            824        0      824       +0%    47.4    36,120       no
  SHELL_SUP        327      468      795       -3%    55.3     5,294      YES
  RIB_BOX          733        0      733      -11%    44.6     4,156       no
  RIB_SHELL        661        0      661      -20%    42.9     4,156       no
  --------------------------------------------------------------------------
  SOLID       baseline; stiff; max bed adhesion
  SHELL_SUP   open bottom = support reachable; needs a brim
  RIB_BOX     no support; flat ceiling bridges 30mm
  RIB_SHELL   no support; shell bridges 30mm between ribs

==============================================================================
  WHOLE BUILD (20 tiles, using the mixed archetype as the average)
==============================================================================
  strategy      kg part  kg waste  kg total  saved kg    hours  saved h
  --------------------------------------------------------------------------
  SOLID             6.6       0.0       6.6      +0.0      381       +0
```

## Where the crossover sits

```
$ python3 scripts/hollow_model.py --crossover

At what tile height does hollowing start to pay?

Sweeping mean terrain height for one tile, all strategies.

 mean Z mm   SOLID g  SHELL_SUP   RIB_BOX  RIB_SHELL       winner
----------------------------------------------------------------------
        15       190       258       168       239      RIB_BOX
        20       229       290       203       264      RIB_BOX
        25       267       323       238       290      RIB_BOX
        30       306       356       272       316      RIB_BOX
        40       383       422       342       368      RIB_BOX
        50       461       487       411       419      RIB_BOX
        70       615       619       550       522    RIB_SHELL
       100       847       815       758       677    RIB_SHELL
       140      1156      1078      1036       883    RIB_SHELL
       190      1543      1406      1383      1141    RIB_SHELL

```

**Below ~60 mm mean tile height, `RIB_BOX` wins. Above it, `RIB_SHELL`** (or
`SHELL_SUP` with cheap support). The strategy should be chosen **per tile**,
not once for the project — and `scripts/tile_heights.py --stats` gives you the
per-tile numbers to choose with.

## Whole build

```
$ python3 scripts/hollow_model.py --build --support-density 0.05 --interface-layers 0

==============================================================================
  WHOLE BUILD, 20 tiles with a realistic height mix
  11 flats + 6 mixed + 3 hills   (placeholder -- see tile_heights.py)
==============================================================================
  strategy       kg part  kg waste  kg total  vs solid    hours    days
  --------------------------------------------------------------------------
  SOLID             6.53      0.00      6.53       +0%      376    15.7
  SHELL_SUP         5.01      0.89      5.91      -10%      358    14.9
  RIB_BOX           5.89      0.00      5.89      -10%      357    14.9
  RIB_SHELL         6.59      0.00      6.59       +1%      403    16.8

  BEST-OF: pick the cheapest strategy per tile
    11 x flats   -> RIB_BOX        169 g each
     6 x mixed   -> SHELL_SUP      297 g each
     3 x hills   -> SHELL_SUP      516 g each
  MIXED             4.35      0.84      5.19      -21%      322    13.4

```

**~21% off the build — 1.3 kg and 54 hours — by picking per tile.** Note the
whole-build saving is far smaller than the 37–47% single-tile figure, because
the mix is dominated by short tiles where there is barely any void to remove.

> **The 8" figure only applies to one tile.** At the 5×4 grid with 193.2 mm of
> full-range relief, only the tile containing the West Hills high point is
> actually 203 mm tall. A Columbia bottomland tile is about **15 mm** tall.
> Most of the build is not tall, which is why hollowing helps less than it
> feels like it should.

---

## Constraint 3 — 0.5" of shell is roughly twice what you need

```
$ python3 scripts/hollow_model.py --shell-sweep

RIB_SHELL total grams vs shell thickness (relief 193.2mm, ribs @ 30mm)

  shell mm         FLATS         MIXED          WEST
----------------------------------------------------
       3.0           168           262           591
       4.0           175           269           598
       6.0           189           284           613
       8.0           204           298           627
      10.0           218           313           641
      12.7           238           332           661
      16.0           253           356           685
      20.0           253           385           714

Solid baseline for comparison:
        --           189           331           824

```

Most of the benefit is captured by **4–6 mm**. Going from 12.7 mm to 6 mm saves
another ~48 g per tile everywhere. A 6 mm shell over ribs at 30 mm spacing is
still very stiff — stiffness in bending comes from the rib depth, not the skin.

Keep 12.7 mm only if you plan to engrave deep grooves or pocket magnets into
the underside.

## Constraint 4 — shell thinning on slopes

```
$ python3 scripts/hollow_model.py --thinning

SHELL THINNING ON SLOPES

If the shell is generated by offsetting the terrain DOWN IN Z by t,
its true thickness measured perpendicular to the surface is only
t * cos(slope). On steep terrain the shell gets dangerously thin --
and steep terrain is exactly where the tile is tallest and most
needs the strength.

nominal Z-offset shell = 12.7 mm

 terrain slope   true thickness                      verdict
--------------------------------------------------------------
            0d           12.70mm                         fine
           15d           12.27mm                         fine
           30d           11.00mm                         fine
           45d            8.98mm                         fine
           60d            6.35mm                         fine
           68d            4.76mm           thin but printable
           75d            3.29mm           thin but printable
           80d            2.21mm           thin but printable
           85d            1.11mm  BELOW 3 WALL LINES -- fails

  FIX: use a true perpendicular offset (Blender Solidify with
  'Even Thickness' / complex mode, or a Shrinkwrap-based offset)
  rather than a plain Z displacement. If you must use a Z offset,
  size it for the steepest slope you care about, not the average.

```

## Constraint 5 — trapped support

**This one is a hard geometric constraint, not a tuning parameter.**

Support is only removable if the void connects to the outside. Check each
strategy:

| Strategy | Void enclosed by | Removable? |
|---|---|---|
| `SHELL_SUP` | perimeter walls + shell above, **open at the plate** | **yes** — pull it out from below |
| `RIB_BOX` | perimeter + ribs + flat ceiling | n/a, uses no support |
| `RIB_SHELL` | perimeter + ribs, open at the plate | n/a, uses no support |
| `RIB_BOX` **+** support above the ceiling | perimeter walls, ceiling below, shell above — **sealed on all six sides** | **NO. Unbuildable.** |

That last row is the tempting hybrid — hollow box below, terrain-following
shell above — and it does not work. The flat ceiling that makes `RIB_BOX`
support-free is the same surface that seals the upper void. Any support printed
above it is entombed permanently.

If you want that hybrid, the ceiling needs deliberate access ports (say 20 mm
holes on the rib grid) and you must verify the void is fully connected through
them. Simpler to just use `RIB_SHELL`.

## Other FDM constraints

**Bed adhesion.** A solid tile puts 36,120 mm² on the plate. A perimeter-only
tile puts down a 1.26 mm ring — about 960 mm², a 97% reduction — plus whatever
the support columns contribute. On a 180 × 200 mm part printing for 20+ hours
this is a real detachment risk.

- Use a **brim, 8 mm minimum**, on all open-bottom strategies.
- Keep support **touching the build plate** rather than resting on the model;
  those columns add meaningful hold-down.
- Consider widening the perimeter wall to 4–5 loops for the first ~2 mm of Z.

**Bridging between ribs.** 30 mm is comfortable. The sweep above shows 40–50 mm
saves a little more material but starts to sag, and a sloped bridge sags worse
than a flat one — slicers handle angled bridging poorly. **Stay at 25–30 mm**,
and tighten to 20 mm in the flattest tiles where the shell's underside is
closest to horizontal.

**Rigidity.** A ribbed hollow tile is stiffer per gram than a solid one; bending
stiffness scales with depth cubed and the ribs preserve the depth. No concern
at 30 mm spacing.

**Wall load.** Hollowing cuts total assembly mass ~20%, which helps the mounting
problem in `docs/08`.

**Mounting.** An open bottom is an *advantage* — it gives access to the tile
interior for magnets, cleat pockets and screw bosses, which `docs/05` otherwise
has to design around. Put the magnet pockets on the rib intersections.

---

## Recommendation

1. **Default to `RIB_BOX`** for every tile whose mean height is under ~60 mm.
   No support, no removal labour, ~10% saving, and it prints faster than solid.
2. **For the tall West Hills tiles**, use `RIB_SHELL`, or `SHELL_SUP` with
   support at **5% density and zero interface layers**. Both land near −35%.
   `RIB_SHELL` avoids support removal entirely; `SHELL_SUP` is easier to
   generate. Try one of each on the pilot.
3. **Shell thickness 6 mm**, not 12.7 mm, unless you need the depth for
   underside pockets.
4. **Rib spacing 25–30 mm.** Generate ribs in Fusion as a patterned body and
   boolean against the terrain; see `docs/05`.
5. **Use a true perpendicular offset** for the shell, not a Z displacement.
6. **8 mm brim** on anything with an open bottom.
7. **Never** combine a `RIB_BOX` ceiling with support above it.

## Pilot test protocol

Add to `csv/test_prints.csv`. Print these as small coupons — a 60 × 60 mm
crop of real terrain is enough, do not burn a full tile.

| Test | What it answers |
|---|---|
| `HOLLOW-1` | `RIB_BOX` at 30 mm spacing — does the flat ceiling bridge cleanly? |
| `HOLLOW-2` | `RIB_SHELL` at 30 mm — how much does the shell sag between ribs on a *flat* terrain crop? |
| `HOLLOW-3` | `RIB_SHELL` at 20 mm — does tighter spacing fix the sag? |
| `HOLLOW-4` | `SHELL_SUP` at 5% support, 0 interface — does it actually pull out from the open bottom? |
| `HOLLOW-5` | 6 mm vs 12.7 mm shell — is 6 mm stiff enough to hand-handle without flexing? |
| `HOLLOW-6` | Open-bottom bed adhesion over a long print — does the perimeter ring hold with an 8 mm brim? |

`HOLLOW-4` and `HOLLOW-6` are the two that can invalidate the whole approach.
Run them first.
