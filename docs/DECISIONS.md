# Decision Log

Append-only. Newest at the top. Every entry needs a date, the decision, and the
reasoning — the reasoning is the part you will want in six months.

Status values: `DECIDED` · `PROVISIONAL` · `OPEN` · `SUPERSEDED`

---

## 2026-08-24 — Heightmaps MUST be Non-Color. sRGB decoding bends the terrain.

**DECIDED.** The most consequential bug found in this pipeline.

Blender treats an image texture as **sRGB by default** and applies the
sRGB-to-linear transfer function on read. On a heightmap that is silent and
catastrophic, because it is a **curve**, not a scale: it barely touches values
near 1.0 and crushes values near 0. Every elevation was wrong by a different
amount. The map's hypsometry was bent.

Measured on tile r01c02: the heightmap held u16 8826 = 0.1347 of full range =
**0.875 mm** of relief. Blender displaced **0.106 mm**. And
`sRGB_to_linear(0.1347) x 6.5 = 0.1058`. Exact.

| tile | correct | with sRGB decode | error |
|---|---|---|---|
| r02c01 (holds the peak) | 6.50 mm | 6.50 mm | none |
| r01c01 | 5.93 mm | 5.27 mm | -11% |
| r02c03 | 3.52 mm | 1.65 mm | -53% |
| r01c02 | 0.88 mm | 0.11 mm | **-88%** |

*Why it hid:* the tile holding the project high point was pixel-perfect, and the
error grew as elevation fell. It presented as "the flats look flat" -- which is
exactly what a low-exaggeration relief map is supposed to look like. Nothing
about it resembled a bug.

*It also corrupted a design decision.* The exaggeration was chosen visually
against this distorted model, where the flats were crushed toward zero while
the West Hills stood at full height. That inflated the apparent contrast, which
is why 3x and 4x read as "comically spiky". **Re-judge exaggeration against the
corrected model.**

*Fix:* `img.colorspace_settings.name = "Non-Color"` on load. Elevation is data,
not colour.

*Guard:* the script now reads the texture's peak value and compares
`peak x relief_mm` against the evaluated Z span, exiting if they differ by more
than 5%. All twelve tiles now agree to within 0.1%. This check catches colour
management, bad normalisation, and any future misreading of the texture --
none of which announce themselves.

## 2026-08-24 — Measured pilot cost: 174 g / 10 h, not 0.3 kg / 19 h

**DECIDED.** From the actual cut tile volumes.

Summing the boundary-cut solids: **502.0 cm3 bulk over 10 printed tiles**
(r01c04 and r03c01 hold 0.60 cm3 between them and are not printed). At
`SOLID_FRACTION = 0.28`: **140.6 cm3 of plastic, 174 g, 10.0 h**.

`topo_params.py` estimated 0.3 kg / 19 h. It is not wrong -- it models **full
rectangular tiles** and has no knowledge of the boundary cut, which removes
~47% of the grid. Both numbers are correct for what they describe.

*How to apply:* for any boundary-cut configuration, scale `topo_params.py`
mass and time by the city's share of the grid area (**52.5%** for Portland
against a boundary-fitted grid). Do not add a fudge factor to
`SOLID_FRACTION` -- that constant means something else and is calibrated from
printed tiles.

---

## 2026-08-24 — Never Solidify a masked heightmap. Extrude and cap instead.

**DECIDED.** Root cause of the empty-boolean failure, found by bisection.

The whole-map preview was built as a displaced sheet plus a **Solidify**
modifier to give it thickness for the Boolean. Intersect returned an empty mesh
every time.

*The cause:* the masked heightmap has a **near-vertical cliff at the city
boundary** -- terrain drops to 0 across a single texel. Solidify offsets along
vertex normals, and offsetting across a vertical wall folds the new surface
through itself. Blender's Exact solver rejects self-intersecting input by
returning **empty**, not by erroring.

*Why it survived four rounds of debugging:* the solidified body reported
**0 non-manifold edges, 0 loose vertices, and a correct positive signed volume
(+852,291 mm3 against ~845,100 expected)**. Every invariant available said it
was a valid solid. Self-intersection is visible to none of them.

*What actually found it:* `scripts/boolean_probe.py` -- bisecting each operand
against a known-good reference cube.

```
A  cube    INTERSECT cube          8 verts   OK   -> booleans work
B  cube    INTERSECT prism        36 verts   OK   -> prism is fine
C  terrain INTERSECT cube          0 verts   EMPTY -> terrain is the fault
D  terrain INTERSECT prism         0 verts   EMPTY
```

*The fix:* build the preview the same way real tiles are built -- extrude the
boundary edge loop straight down to Z=0 and cap it. A vertical skirt cannot
self-intersect. Confirmed: 280,203 faces, Z 0.00 -> 16.49 mm.

*Cost:* Displace must be applied before the Boolean, so preview mode with
`--prism` no longer scrubs Strength live. Change exaggeration by re-running.
Without `--prism` the live-scrub behaviour is unchanged.

**How to apply, generally:** when an operation silently yields nothing, stop
inspecting the suspect input and **bisect against a known-good reference**.
Three separate invariants were needed across this pipeline -- evaluated vertex
count for the flat sheets, signed volume for the inverted prism, and an actual
boolean against a cube for this -- and no settings panel showed any of them.

---

## 2026-08-24 — Ring winding decides whether a boolean works. Check volume, not just edges.

**DECIDED.** `boundary_prism.py` forces CCW exteriors and verifies signed volume.

Every prism written before this fix was **inside-out**. Shapely does not
guarantee ring winding, and the smoothed boundary's exterior ring came out
**clockwise** (signed area −376,441,050). Winding sets the face normals, so the
prism was a mirror-image solid.

*Why it took four rounds to find:* an inverted solid is invisible. Blender draws
backfaces, so the prism looked perfectly correct in the viewport. Boolean
**Intersect** against it returns an EMPTY mesh with no error, because
intersecting with the complement of a region is empty. Every symptom pointed
elsewhere — first at the cutter being hidden, then at n-gon tessellation, then
at the axis convention, then at mesh size. Three of those were real bugs and
were fixed on the way, which made the underlying one harder to see, not easier.

*The check that actually distinguishes it:* **signed volume**, via the
divergence theorem. Positive means outward normals and a real solid; negative
means inside-out.

The edge-manifold test that had been passing all along cannot catch this: a
mirror-image solid still uses every edge exactly twice. **Watertight and
correctly-oriented are different properties**, and only the second one makes a
boolean behave. The script now prints the volume against its analytically
expected value (`area x height`) and refuses to write a negative one.

*How to apply, generally:* when a geometric operation silently produces nothing,
test an invariant of the OUTPUT rather than inspecting the inputs. Volume,
vertex count and evaluated bounds each caught a different failure in this
pipeline; not one of them was visible in a settings panel.

---

## 2026-08-24 — Base slab change propagated into the scripts

**DONE.** Follow-up to "Base slab reduced from 10 mm to 4 mm" above. The
constant changed but three scripts still carried their own copies of it, so
tiles kept coming out with a 10 mm slab and would have needed cutting in the
slicer.

- `scripts/blender_heightmap_to_mesh.py` now imports `BASE_MM` from
  `topo_params.py` and uses it as the `--base-mm` argparse default (fallback
  4.0 if the import fails, with the source printed at run time). `--base-mm`
  should now be **omitted** from the export command; pass it only to override
  the project constant for a one-off.
- `scripts/qgis_export_tiles.py` now imports `ELEV_MIN_M` / `ELEV_MAX_M` from
  `topo_params.py` the same way, rather than duplicating them.
- Docs regenerated: `docs/09` plan block re-run at the new constant, `docs/01`,
  `docs/11`.

Expected tallest tile after re-export at `--relief-mm 8.0`: **12.00 mm**
(4.0 base + 8.0 relief). Anything else means the constant did not take.

**Consequence flagged, not yet decided:** at 4 mm the recessed-mounting note in
`OPEN-QUESTIONS.md` 5c no longer holds — a 6 x 3 mm magnet leaves 1 mm of floor
at the river. That section has been rewritten with the three options (place
mounts under higher terrain, use thinner hardware, or thicken locally). Does
not block the pilot, which is not being mounted.

---

## 2026-08-24 — Base slab reduced from 10 mm to 4 mm

**DECIDED.** Owner direction. Supersedes the 2026-08-20 "Base slab at 10 mm".

*What it buys,* measured against the boundary-cut pilot footprint of
44,537 mm2 over 10 printed tiles at 2.03x:

| base | bulk | plastic | mass | time |
|---|---|---|---|---|
| 10 mm | 515.1 cm3 | 144.2 cm3 | 179 g | 10.3 h |
| **4 mm** | **247.9 cm3** | **69.4 cm3** | **86 g** | **5.0 h** |

**More than half the pilot's mass and time.** The base slab, not the relief,
was the dominant volume -- which is also why exaggeration is so cheap here.

*What it costs.* The 2026-08-20 entry justified 10 mm as "rigidity for a
wall-mounted plate and a substrate for registration and mounting features."
Both are now thinner arguments:

- **Recessed mounting.** A 6 x 3 mm magnet needs 3 mm of pocket plus cover.
  At a 4 mm base the flats leave **1 mm of cover** -- printable but weak.
  Under the West Hills there is 4 + 8 = **12 mm**, which is ample. The owner's
  own instinct (2026-08-24, `OPEN-QUESTIONS` 5c) to place mounts "underneath
  the mountain terrain where available" is therefore no longer optional at
  4 mm; it is **required**. Pocket placement is now constrained by terrain.
- **Rigidity.** 4 mm across a 78 x 90 mm pilot tile is stiff enough. Across a
  **200 mm final tile it is not obviously so**, and thin flat parts also warp
  more. Re-evaluate the base independently for Phase 2 rather than carrying
  4 mm forward by default.

*Also affected:* every "total height off the wall" figure now includes 4 mm,
not 10. `docs/01` regenerated. Pilot peak is 4 + 8 = **12.0 mm**.

---

## 2026-08-24 — Pilot vertical exaggeration: 2.03x (Displace Strength 8.0 mm)

**DECIDED.** Supersedes the 1.66x entry below.

```
Displace Strength   8.000 mm
true 1x relief      3.935 mm   (4x3 boundary-fitted grid, 1:91,943)
exaggeration        2.033x
peak off the wall   18.0 mm (0.71") including the 10 mm base slab
cost                10 printed tiles, ~515 cm3 bulk, ~179 g, ~10.3 h
```

Chosen visually against the **corrected** model, after the sRGB colour-space
bug was fixed. The earlier 1.66x was picked against a model whose flats had
been crushed by up to 88% while the West Hills stood at full height -- which
inflated the hill-to-flat contrast and made 3x and 4x read as "comically
spiky". With correct hypsometry the same eye chose **higher** exaggeration.

*A design decision made against unverified geometry is not a decision.* This is
the concrete cost of the colour-space bug, and the reason the relief
cross-check now runs on every tile.

*The extra 0.38x is nearly free:* +5 g and +20 minutes over 1.65x, because the
10 mm base slab dominates tile volume, not the relief.

*Terracing at 2.03x*, horizontal run per 0.2 mm layer:

| true grade | @1.65x | @2.03x | @2.03x, 0.1 mm layers |
|---|---|---|---|
| 0.5% | 24.1 mm | 19.7 mm | 9.8 mm |
| 1.0% | 12.0 mm | 9.9 mm | 4.9 mm |
| 2.0% | 6.0 mm | 4.9 mm | 2.5 mm |

Still the thing to evaluate on the printed pilot. Portland's inner eastside runs
0.5-2%. Dropping to 0.1 mm layers halves every figure and is the first lever to
try if the banding reads badly.

---

## 2026-08-24 — SUPERSEDED: pilot exaggeration 1.66x (Strength 6.5 mm)

**SUPERSEDED** by the 2.03x entry above. Retained because the reasoning matters:
this value was chosen against a gamma-bent model and is the worked example of
why geometry gets verified before it gets judged.

**DECIDED for the pilot.** Chosen visually in Blender against the whole-map
preview, per the owner's stated method.

```
Displace Strength   6.500 mm
true 1x relief      3.91 mm      (pilot 4x3 @ 90 mm, 1:92,593)
exaggeration        1.663x
Z factor            0.0180 mm per metre
peak off the wall   16.5 mm (0.65") including the 10 mm base slab
pilot cost          0.3 kg / 19 h over 12 tiles
```

This is below the 2.5-4x that `docs/01` suggests for "reads as accurate
terrain", and at the low end of the 1.5-3x convention for regional relief maps.
It is a deliberate choice toward the accurate end.

**Consequence 1 -- water flattening becomes unnecessary for the pilot.** At
Z factor 0.0180, a 1 m lidar ripple on the river surface is **0.018 mm, or 0.09
of a 0.2 mm layer**. Invisible. Step 7 can be skipped, and `ELEV_MIN_M` stops
blocking the pilot. (It returns at a final: the same ripple is 0.53 mm, 2.7
layers, at 8" projection.)

**Consequence 2 -- the flats will terrace, and this is the thing to look for on
the printed pilot.** Terrace width = layer height / (true grade x exaggeration):

| true grade | @1.66x | @3x | @6.5x |
|---|---|---|---|
| 0.5% | **24.1 mm** | 13.3 mm | 6.2 mm |
| 1.0% | **12.0 mm** | 6.7 mm | 3.1 mm |
| 2.0% | 6.0 mm | 3.3 mm | 1.5 mm |

Portland's inner eastside runs 0.5-2%, so expect 6-24 mm steps on a 313 mm
map -- contour banding across half the piece. 0.1 mm layers halve every figure.

*Why proceed anyway:* the pilot costs 0.3 kg and 19 h, and whether that banding
reads as a defect or as a feature is exactly the question a screen render cannot
answer. That is what the pilot is for. Revisit before Phase 2.

## 2026-08-24 — Two of the twelve pilot tiles are effectively empty

**DECIDED: print 10, not 12.**

`boundary_prism.py --cols 4 --rows 3` reports how much of each tile the city
actually occupies after the boundary cut:

```
r01c01 51.7%   r01c02 53.3%   r01c03 29.1%   r01c04  0.1%   <- empty
r02c01 26.5%   r02c02 94.2%   r02c03  100%   r02c04 64.9%
r03c01  0.2%   <- empty       r03c02 80.3%   r03c03 57.8%   r03c04 42.1%
```

**r01c04 (0.1%)** and **r03c01 (0.2%)** contain essentially no city. Printing
them yields a nearly blank plate. Since the boundary cut removes their content
anyway, omitting them costs nothing visually -- the silhouette is identical --
and saves two tiles of time and filament.

This is the `docs/11` step 8f check ("flag any tile that comes out nearly
empty"), now done arithmetically rather than by eye. Mark both `omitted` in
`csv/tiles.csv` rather than deleting the rows, so the grid stays legible.

*Also worth noting:* r02c03 is 100% inside the city, so it needs no boolean at
all -- its prism is a plain rectangle.

---

## 2026-08-24 — Evaluated two prior workflows. Neither replaces this pipeline.

**DECIDED.** Reviewed from transcripts of the owner's earlier reference videos.

### A. STL -> Instant Meshes -> Fusion T-Spline -> NURBS

Purpose: convert a faceted scan mesh into a NURBS/BRep body so Fusion's solid
tools will operate on it. **Does not apply here**, for three reasons:

1. **The quad-remesh destroys the map.** The workflow targets ~10,000 vertices.
   At the pilot's 1:92,593 that is **269 m of ground per vertex** -- Mt Tabor
   (~800 m across) becomes 3 vertices, Rocky Butte 2. `docs/04` asks for 4-6
   vertices per printed mm, i.e. 1.3-3.0 M for the pilot map. That is 130-300x
   denser. The technique suits a smooth head scan; terrain is the opposite case.
2. **NURBS is not the deliverable.** The output here is a watertight STL for a
   slicer. Heightfield -> quad cage -> T-Spline -> BRep -> mesh is a lossy round
   trip back to where it started.
3. **Our mesh lacks the defects it repairs.** That source came from an online
   terrain exporter with duplicate vertices, duplicate faces and a box skirt.
   Ours is a grid primitive, displaced and boundary-capped by a script we
   control -- grid topology cannot produce duplicates.

**Worth keeping from it:** the warning that on STL-derived surfaces, Fusion
**shell almost always fails**, **surface offset very often fails**, and fillets
fail above a small radius (0.5 mm failed where 0.2 mm worked), all from high
curvature. *This bears directly on `docs/10`.* If `RIB_SHELL`'s terrain-following
shell were ever built as a Fusion shell or surface-offset, it would fail exactly
this way. It must be a **second displaced heightfield** -- same heightmap,
offset down by the shell thickness -- which is cheap and cannot fail that way.

Also worth keeping: Blender's **Merge by Distance** (the 2.79 "Remove Doubles",
now `M` in Edit Mode) as a cheap sanity check on exported tiles.

### B. BLOSM / OSM cityscapes with per-feature colour

Purpose: import OSM terrain + buildings + roads + water into Blender, extrude
each feature to a different height, export one STL per feature, then load them
into the slicer as **one object with multiple parts** and assign a filament to
each -- avoiding manual colour painting.

**The multi-part technique does NOT dodge the purge cost.** Purge is driven by
**tool changes per layer**, not by how the geometry is organised. On a
heightfield, roads follow the terrain through the full Z range, so nearly every
layer still contains two or more colours and still forces a change. Separate
bodies change the authoring convenience, not the layer content.
`scripts/color_cost.py` measured the real cost: ~283 g/tile of purge at 2"
relief, ~1.1 kg/tile at 8", ~23 kg across 20 tiles. **The engrave + paint-fill
decision stands.**

**But the same technique is the right mechanism for the strategy we DID choose.**
`docs/DECISIONS` reserves the AMS for **Z elevation banding**, which costs one
change per band per tile (~2 g for six bands). Rather than painting height
ranges in the slicer, boolean-intersect the terrain against a stack of Z-slabs
to get one body per band, export them separately, and load as a multi-part
object. That is more deterministic than slicer painting and gives band edges
that align across tiles by construction. Fold into the AMS-1 coupon.

**Buildings are out of scope, and the arithmetic is decisive.** At the pilot a
house footprint is 0.13 mm and a street ROW 0.19 mm -- both under the 0.4 mm
nozzle floor. They only become printable at a 5x4 or 7x6 final. And there is a
deeper conflict: **terrain is exaggerated and buildings cannot be.** At 5x4 with
12.3x, a 100 m tower is 3.2 mm at true scale -- invisible beside hills stretched
12x -- or 39 mm if exaggerated to match, which is absurd. Buildings and
exaggerated relief do not coexist.

**Not adopted:** CADMapper -> Illustrator layers -> DXF -> Fusion extrude. Free
tier caps at 1 km2; this bbox is 725 km2.

**Rejected as a downgrade:** "extrude the terrain down an excessive amount and
chop it flat in the slicer". `blender_heightmap_to_mesh.py` already extrudes the
boundary loop to Z=0 and caps it, giving an exact 10 mm base slab and a clean
vertical skirt for tiles to butt against.

**Adopted:** the **Solidify** modifier for features too thin to print, which is
the raised-feature analogue of the `WIDTH-1` coupon's rule that a groove must
exceed one extrusion width.

---

## 2026-08-24 — Boundary fixes are point-addressed, not threshold-addressed

**DECIDED.** `scripts/smooth_boundary.py --edit ACTION:E,N[:R]`.

Review of the D=50 outline found it good except in five specific places: a long
narrow peninsula in the north, two detached islands created by the smoothing,
and two concave inlets that should be sealed.

*Why a global threshold is the wrong instrument:* the outline carries dozens of
bays and limbs of comparable area. Measured on the D=50 result, the eight
largest bays run 0.20–0.87 km² and the eight largest narrow-necked limbs run
0.23–0.80 km². Any area cut-off that reaches the five wanted features also
takes a dozen that were fine.

*Three actions, each targeted at one point:*

- `cut` — opening at the given radius, then subtract the component at that
  point. Opening bridges **straight across the neck**, which is precisely
  "cut the peninsula off and close it with a straight line".
- `fill` — closing at the given radius, then union the component at that point.
  Closing spans the mouth of the inlet.
- `drop` — remove the detached part at that point. The largest part is
  protected, so the main body can never be deleted by a stray coordinate.

The radius is **reach**, not severity: it must exceed half the neck or mouth
width to find the feature, but the feature's own extent determines what moves.

*The five committed edits, confirmed against the map:*

```
cut  at 535344,5048230   north peninsula   0.2873 km2   6.9 x 25.6 mm printed
drop at 518819,5041261   SW island         0.0513 km2   6.0 mm2 printed
drop at 540031,5036484   SE island         0.0085 km2   1.0 mm2 printed
fill at 519080,5042530   SW bay            0.1173 km2   6.8 x  7.9 mm printed
fill at 525646,5032262   S  bay            0.0492 km2   3.9 x  3.3 mm printed
```

Result: **one part**, 924 vertices, 376.441 km² (100.03% of the original area),
worst intrusion 1.13 mm printed, mean deviation 0.09 mm.

The reported worst **amputation of 16.99 mm is the north peninsula, removed on
purpose**. It is not a smoothing artefact and should not be read as one — the
metric cannot tell a deliberate `cut` from an accidental one, so the intent
lives here in the log.

*How to apply:* every edit prints what it moved in km² and printed mm. A `fill`
reporting 14 x 15 mm when a 4 mm notch was intended has found the wrong bay —
the fix is a better coordinate, not a larger radius. Edits are recorded in the
output's `properties.edits` so the polygon carries its own provenance.

---

## 2026-08-24 — Boundary smoothing has a cliff at D = 75 m. Stay below it.

**DECIDED.** `D = 50 m` for the pilot, hard ceiling `D < 75 m`.

Measured on the real polygon (376.33 km², 182.0 km perimeter, 14,707 vertices,
mean width 4,136 m) at the pilot's 1:92,593:

```
 D(m)  D(mm)  pts  verts  AMPUTATE m     mm  INTRUDE m     mm    lost    gain
    0   0.00    1  1,099          42   0.45         38   0.41   0.181   0.221
   25   0.27    4  1,014         195   2.10         22   0.24   0.271   0.305
   50   0.54    3    954         235   2.53         48   0.52   0.380   0.671
   75   0.81    2    871       1,571  16.96         57   0.61   0.784   1.006  <-- CLIFF
  100   1.08    1    798       1,571  16.96         90   0.98   0.830   1.591
```

Between D=50 and D=75 the worst-case amputation jumps **6.7x for a 1.5x change
in D**. Morphological opening severs a narrow neck and a whole limb of the city
falls off: a **0.2793 km² piece, 659 x 2,316 m**, which at pilot scale is
**7.1 x 25.0 mm** — a 25 mm limb on a 313 mm map. It sits at
**45.5767 to 45.5976 N, -122.547 W**, a narrow north-south strip in the
north-east near the Columbia.

*How to apply:* if D=50 does not straighten the zig-zag enough, raise
`--chaikin`, **not** D. Chaikin is corner-cutting, not a size filter, so it
cannot amputate a limb. D is the only knob that deletes material.

## 2026-08-24 — Report deviation in both directions, never one Hausdorff

**DECIDED.** Correction to `scripts/smooth_boundary.py`.

A single symmetric Hausdorff distance reports only the larger of two opposite
phenomena, and they are not equivalent:

- **AMPUTATION** — max over the *original* outline of its distance to the new
  geometry. Material cut away. Irreversible; it is the city's shape being lost.
- **INTRUSION** — max over the *new* outline of its distance to the original.
  A notch filled in. It claims ground that was never in the city, but it does
  not destroy anything.

At D=75 the two are **1,571 m and 57 m**. One number would have reported 1,571
with no indication of which kind it was, and the earlier symmetric column did
exactly that — the catastrophic case and the harmless case were
indistinguishable until they were separated.

The sweep now prints both, flags a `<-- CLIFF` above 5 mm of amputation, and
reports `lost` and `gain` km² separately for the same reason.

*Also fixed:* sub-printable parts are now dropped from the input before any
measurement (`--min-part-mm2`, default 4.0 mm² printed). Three slivers of
0.0032, 0.0021 and 0.0006 km² — 0.38, 0.25 and 0.07 mm² printed — were being
carried into the statistics. And a Douglas-Peucker cleanup is applied to every
sweep row so the vertex counts reflect what would actually be exported
(1,099 rather than 59,616 at D=0; Chaikin quadruples vertices per iteration).

---

## 2026-08-24 — `ELEV_MIN_M = 0.19` looks like a decimal error for 1.9

**OPEN — resolve at step 8h with the rest of the elevation constants.**

`topo_params.py` and `qgis_export_tiles.py` both carry `ELEV_MIN_M = 0.19`,
annotated in `docs/DECISIONS.md` as "Columbia River, 0.62 ft". The 10 m DEM
disagrees. Value-frequency analysis of the raw download:

```
   1.900 m   259,223 cells   2.583%   (19.18 km2)
   2.000 m    82,177 cells   0.819%   ( 6.08 km2)
   1.910 m    66,462 cells   0.662%   ( 4.92 km2)
   2.956 m    20,064 cells   0.200%   ( 1.48 km2)
   2.855 m    17,222 cells   0.172%   ( 1.27 km2)
   2.875 m    14,217 cells   0.142%   ( 1.05 km2)
```

The dominant flat water surface sits at exactly **1.900 m**, not 0.19 m. And
1.900 m = **6.23 ft**, against the recorded "0.62 ft" — a displaced decimal
point in the original figure is the obvious reading.

*Magnitude:* 1.71 m of error on a 362 m range is 0.5%. At the pilot's Z factor
it is 0.14 mm; at the final 5x4 at 8" projection (Z factor 0.534) it is
0.91 mm — small, but it also shifts the datum the 10 mm base slab is measured
from.

*Resolve* by taking `ELEV_MIN_M` from the masked DEM at step 8h, and correct
the "0.62 ft" annotation in the 2026-08-20 base-slab entry at the same time.

## 2026-08-24 — 3DEP water is partly pre-flattened, at inconsistent levels

**DECIDED.** Step 7 is still required; do not skip it.

9.46% of the raw DEM sits below 5 m, and that low ground carries **387 distinct
values**. Water is flattened in patches, but at several different elevations:
roughly **1.90–1.91 m** (Columbia, ~24 km2 combined), **2.00 m** (~6 km2), and
a cluster around **2.86–2.98 m** (Willamette — which matches `docs/03`'s
"Willamette through downtown sits near 3 m").

*How to apply:* `docs/03` step 3 already calls for two separate constants. Use
the measured values rather than the doc's round numbers, and rasterise the two
rivers as separate masks — forcing both to one constant would put a visible
1 m step where they meet at Kelley Point.

---

## 2026-08-24 — MEAN_ELEV_FRACTION measured: 0.1958. ELEV_MAX_M confirmed at 362.0.

**DECIDED.** Set in `topo_params.py`, `IS_ESTIMATE = False`. Supersedes the
"constants are OPEN" entry below.

Measured on `dem_stats_only.tif` — the DEM cut with the **true** smoothed
boundary, not the +50 m buffered cutline that feeds the working raster:

```
valid 3,764,426 of 7,526,385 grid cells (50.0% filled)
min 1.337   max 361.951   mean 71.927   mean_fraction 0.1958
```

**`ELEV_MAX_M = 362.0` was correct all along.** The masked maximum is 361.951 m
with zero cells above the ceiling. The 391 m seen in the raw rectangle was the
Tualatin Mountains crest outside the city limits, and the mask removed it
exactly as predicted. No change needed — the raw-bbox reading was the
misleading one, not the constant.

**Two masks, deliberately.** The working raster `dem_masked.tif` uses the
**+50 m buffered** cutline so the resampling kernel has real data at the rim;
that version reads max 368.859 with 53 cells above the ceiling, all inside the
buffer ring and removed later by the mesh boolean. Constants come from the
unbuffered version. Mixing them up would import a wrong ceiling.

**Cost of the correction:** `MEAN_ELEV_FRACTION` was a 0.17 placeholder; 0.1958
is ~15% higher, and it multiplies every mass and time estimate in the project.

| | old (0.17) | measured (0.1958) |
|---|---|---|
| pilot 4x3 @ 90 mm, 7.68x | 0.4 kg / 26 h | **0.5 kg / 27 h** |
| final 5x4 at 2" | 4.4 kg / 251 h | **4.6 kg / 267 h** |
| final 5x4 at 6" | 8.8 kg / 508 h | **9.8 kg / 562 h** |
| final 7x6 at 6" | 19.8 kg / 1,143 h | **22.0 kg / 1,266 h** |

`docs/01` and `docs/09` regenerated from the new constant the same day.

**`ELEV_MIN_M` stays OPEN.** The masked minimum is 1.337 m, but p1 reads 1.900 —
the low ground is dominated by the water plane and step 7's flattening will
raise the tail to meet it. Set it after water, not from this run. The gap is
0.94 m on a 361 m range: 0.26%, about 0.02 mm at pilot scale.

---

## 2026-08-24 — Elevation constants are OPEN until the DEM is masked

**OPEN — blocks tiling, not the QGIS work before it.**

Full 10 m bbox, unmasked: **min 0.958 m, max 391.123 m, mean_fraction 0.1922**,
against constants of `ELEV_MIN_M = 0.19`, `ELEV_MAX_M = 362.0`,
`MEAN_ELEV_FRACTION = 0.17`.

The 391 m is **real terrain, not a spike** — its immediate eight neighbours are
390–391 m and its 15×15 neighbourhood averages 383.9 m. It sits at
**45.52653, -122.75310**, on the Tualatin Mountains crest along the Skyline
corridor NW of downtown. 391 m = 1,283 ft, about 95 ft above Portland's cited
high point of 1,188 ft (362 m), so it is very likely **outside the city limits**
and the boundary mask should remove it. 2,009 cells (0.149 km²) exceed 362 m;
they cluster in one ridge segment, lat 45.5234–45.5279, lon −122.7553–−122.7469.

*Why this is not cosmetic:* `qgis_export_tiles.py` normalises against
`ELEV_MAX_M` and **clips to [0,1]**. Anything above the ceiling prints as a flat
plateau at full height — a mesa where a ridge should be.

*Resolution:* mask to the boundary first, then re-run `dem_stats.py` on the
masked DEM and set all three constants from it. Step **8h** in
`docs/11-pilot-runsheet.md`. `dem_stats.py` now refuses to offer the
`mean_fraction` paste instruction when handed the raw rectangle (>120% of bbox)
or a partial crop (<80%), and warns when a raster breaches the elevation
constants.

*Also noted:* the raw data floors at exactly **1.900 m** across a large share of
cells (p0.1 = p1.0 = 1.900), which reads as a pre-flattened water surface. The
smoke crop showed a similar exact floor at 2.000 m. Worth confirming before
doing step 7's water flattening by hand.

## 2026-08-24 — 3DEP 1/3 arc-second pixels are not square

**DECIDED.** The `USGS10m` product is 1/3 arc-second: 0.000093° in both axes,
which at 45.5°N is **7.2 m in x and 10.3 m in y**. The reprojection in step 5b
therefore carries `-tr 10 10` to produce square metre pixels before any
downstream step assumes isotropy.

---

## 2026-08-24 — 3DEP arrives GEOGRAPHIC, not UTM. Reproject before anything.

**DECIDED.** Correction to `docs/02`, found on the first real download.

`docs/02` stated the API delivers "a local UTM zone — Portland is UTM 10N
(EPSG:32610)". It does not. The smoke crop came back as **EPSG:4269 (NAD83,
geographic)** with pixel size in **degrees**.

*Why it matters:* `gdalwarp -tr 15.4 15.4` on a degrees raster requests
15.4-**degree** pixels, and a buffer in degrees is meaningless. The resample,
water mask, boundary buffer and tiling steps all assume metres. A mandatory
reprojection step (`5b`) now sits immediately after import in
`docs/11-pilot-runsheet.md`, and `dem_stats.py` prints a warning when handed a
geographic raster.

*Project CRS stays EPSG:32610*, but the original reasoning is void. It was
chosen because "the raster never gets warped"; a warp is now unavoidable
either way. It stays only because the recorded bbox centroid and city-limits
extent are already expressed in it. EPSG:6559 (NAD83(2011) / Oregon North) is
equally defensible and avoids a NAD83→WGS84 datum shift — but that shift is
~1–2 m, which is 0.05 mm at 1:31,250 and invisible.

## 2026-08-24 — Vertical units confirmed metres

**DECIDED.** Smoke crop over Council Crest: **max 328.04 m** (Council Crest is
~327 m), **min 2.00 m** (the Willamette). Metres, NAVD88. No 0.3048 conversion
needed on the 3DEP path.

Also noted: p1 and p5 both read exactly 2.00, so a meaningful share of cells
sit at precisely that value — 3DEP appears to deliver the Willamette surface
already flat here. Verify on the full DEM before assuming step 7's water
flattening can be reduced; it may equally be a nodata fill.

## 2026-08-24 — MEAN_ELEV_FRACTION must come from the full DEM, never a crop

**DECIDED.** Guard added to `scripts/dem_stats.py`.

The smoke crop reported `mean_fraction = 0.3470` under an instruction to paste
it into `topo_params.py`, whose placeholder is **0.17**. Pasting it would have
roughly doubled every filament and print-time estimate in the project.

*Why:* `mean_fraction` is a whole-map statistic — where the average cell sits
within the elevation range. The smoke box was deliberately chosen as Council
Crest down to the river, i.e. the hilliest 16 km² available. Portland's real
mean is dragged far down by the flat eastside. A hilly crop reads high; a
bottomland crop would read low.

*How to apply:* `dem_stats.py` now computes what fraction of the project bbox
the input covers and **refuses to offer the paste instruction below 80%**,
printing a warning instead. Only a project-wide DEM may set
`MEAN_ELEV_FRACTION`.

---

## 2026-08-24 — The pilot runs on 3DEP 10 m, not 1 m

**DECIDED.** Supersedes the same-day choice to "pull the 1 m anyway".

`USGS1m` returns **HTTP 401** for this account while `USGS10m`, `USGS30m` and
the global collection all return 200 with the same key. Not a bad key.
OpenTopography's dataset page states 1 m access is *"currently restricted to
U.S. academic institutions with .edu addresses, plus educators and
OpenTopography+ members."*

*Why this costs nothing at pilot scale:* at 1:92,593 one printed millimetre is
92.6 m of ground, so a 10 m DEM gives **9.3 samples per printed mm** against
`docs/03`'s 4–8 target. The finest feature a 0.4 mm extrusion can render is
37 m of ground. A 1 m DEM would have been ~93x finer than anything printable.

*Why it may cost something later:*

| Config | 1 mm = | 10 m gives | printable floor |
|---|---|---|---|
| pilot 4x3, 1:92,593 | 92.6 m | 9.3 samples/mm | 37.0 m |
| final 5x4, 1:31,250 | 31.3 m | 3.1 samples/mm | 12.5 m |
| final 7x6, 1:20,833 | 20.8 m | 2.1 samples/mm | 8.3 m |

Only **7x6** genuinely wants better than 10 m. If the final lands there, the
free routes are **USGS The National Map** (3DEP is public domain; USGS
distributes 1 m itself without OpenTopography's gate) or **DOGAMI/OLC**, which
is often crisper in the West Hills regardless.

*Also corrected:* `docs/02` and `docs/03` both said to keep the 1 m original
"for the road-mask step". That was wrong. Road masks are rasterised from
PortlandMaps **vector** centrelines, so their crispness depends on the vectors
and the output grid, not on DEM resolution. Nothing in the road pipeline
samples the DEM.

*Diagnostic:* `python3 scripts/fetch_dem.py --check-key` sweeps the global
collection and all three 3DEP tiers over one tiny box and prints the server's
own error text.

---

## 2026-08-24 — Bbox recentred on the city limits and resized to 29,000 x 25,000 m

**DECIDED 2026-08-24.** Discovered while scoping the boundary cut.

`fetch_dem.py` centres the bbox on downtown Portland (45.5152, -122.6784) and
sizes it 27,870 x 24,690 m. The Portland city-limits polygon, in EPSG:32610, is
**28,578.6 x 24,602.4 m** and sits well north and east of downtown centre:

```
current bbox   X 511,183.8 .. 539,053.8    Y 5,027,890.6 .. 5,052,580.6
city limits    X 512,719.7 .. 541,298.3    Y 5,031,014.4 .. 5,055,616.9

  WEST   city is 1,535.9 m inside the bbox
  EAST   city extends 2,244.5 m BEYOND the bbox   <-- clipped
  SOUTH  city is 3,123.9 m inside the bbox
  NORTH  city extends 3,036.3 m BEYOND the bbox   <-- clipped
```

Against a rectangular map this was harmless — the bbox was just a framing
choice. Against a boundary cut it is not: the silhouette would be sliced flat
along its north and east edges, which is exactly where the shape is most
recognisable.

*Fix, applied:* recentre on the city-limits extent centroid
(X 527,009.0, Y 5,043,315.6) and size to **29,000 x 25,000 m** — the extent
plus roughly 200 m of margin, rounded.

*Applied:* `BBOX_W_M` = 29,000.0 and `BBOX_H_M` = 25,000.0 in
`topo_params.py`; `CENTER_LAT` = 45.542853, `CENTER_LON` = -122.654030 and the
same bbox constants in `fetch_dem.py`. Every derived table in `docs/01` and
`docs/09` regenerated the same day. Verified the new bbox clears the city
limits by ~211 m east/west and ~199 m north/south on all four sides.

*Side effect, and it is a good one:* aspect goes 1.1288 -> 1.1600, and the
squarest grid at a 200 mm tile cap becomes **7x6 (tile aspect 0.994, 42 tiles,
1392 x 1200 mm wall, 1:20,833)**, replacing 9x8 — 42 tiles instead of 72. That
is also the grid `docs/01` recommends for buying relief with wall area instead
of exaggeration: 8" of projection at 7x6 needs **11.1x** against 16.7x at 5x4,
and 6" needs 8.2x against 12.3x. The two arguments now point the same way.

Note the absolute cost still runs the other way: 7x6 at 6" is 19.8 kg and
1,143 h, against 8.8 kg and 508 h for 5x4 at 6".

Pilot impact is negligible: 4x3 @ 90 mm goes 1:91,444 -> 1:92,593, wall
305 x 270 -> 313 x 270 mm.

---

## 2026-08-24 — Cut the map to the Portland city-limits boundary

**DECIDED.** Reverses the rectangular-bbox choice recorded in `docs/02`.

Boundary is Oregon Metro `BoundaryDataWebMerc` layer **0**, filtered
`CITYNAME='Portland'`. Not the UGB (layer 6) and not the Metro district
(layer 3) — the UGB is 3.7x the area, more than doubles the scale denominator
at any wall width, and covers terrain above the West Hills, which would make
`ELEV_MAX_M = 362.0` wrong and silently compress the whole map.

**Enclaves are dissolved out.** Maywood Park and the unincorporated pockets do
not become holes in the map. Delete-holes with an area threshold.

**The outline is simplified to print scale**, not used raw: ~40 m tolerance at
the pilot's 1:92,593 (about 0.43 mm printed), ~15 m at a 1:31,250 final.
Portland's annexation lines staircase at parcel scale and print as noise
otherwise. The pilot's simplified polygon must not be reused at final scale.

**Masking and the cut are separate operations.** Raster mask in QGIS so terrain
outside the line does not distort the project-wide normalisation; mesh boolean
in Blender against a prism extruded from the simplified polygon, because a mask
alone yields a flat apron at base-slab height, not a vertical edge. The raster
mask uses a **+50 m buffered** polygon so the resampling kernel does not dip the
rim; the boolean trims back to the true line.

*Why the boolean is acceptable here:* `docs/04`'s "displace, no booleans" rule
is about road engraving, where thousands of road solids would be catastrophic.
One boundary prism per tile is cheap, and the 3D-Print Toolbox check catches
the non-manifold risk.

*Consequences accepted:* perimeter tiles are no longer rectangles, so
registration keys and the mounting scheme in `docs/08` need per-tile treatment;
some grid cells may come out nearly empty and must be checked against the
boundary before slicing.

*Procedure:* `docs/11-pilot-runsheet.md`.

---

## 2026-08-24 — Hollow base strategy is chosen per tile, not per project

**PROVISIONAL** — to be confirmed by the HOLLOW-* coupons in `docs/10`.

`RIB_BOX` (ribbed hollow box up to the tile's lowest terrain point, flat ceiling
bridging between ribs) for tiles under ~60 mm mean height. `RIB_SHELL` (ribs
straight up to a terrain-following shell) above that. Shell **6 mm**, not the
12.7 mm originally proposed. Rib spacing 25–30 mm. 8 mm brim on any open bottom.

*Why:* modelled in `scripts/hollow_model.py`. Three findings drove it:

1. **The underside overhang inverts.** A shell's underside has the terrain's
   slope, so it self-supports only above 45° after exaggeration. Portland's
   flats — most of the map's area — become near-horizontal ceilings needing
   support, and they are also where the void is shallowest.
2. **Support ≈ the infill it replaces.** At 12% density the whole strategy
   saves 3%. It only becomes worthwhile at ~5% with zero interface layers,
   which is safe because the underside faces the wall. Then it saves 37%.
3. **The crossover is ~60 mm mean tile height.** Below it the ribbed box wins;
   above it the shell wins. A single project-wide choice is wrong either way.

Whole-build effect: about **−21%, 1.3 kg and 54 hours**, far less than the
single-tile figure because most tiles are short. At 193.2 mm of full-range
relief only the West Hills tile is actually 203 mm tall; a Columbia bottomland
tile is ~15 mm.

---

## 2026-08-24 — A RIB_BOX ceiling must never have support above it

**DECIDED.** Hard geometric constraint.

The flat ceiling that makes `RIB_BOX` support-free also seals the void above it.
Perimeter walls close the sides and the terrain shell closes the top, so any
support printed in that upper void is entombed permanently.

*How to apply:* if a hybrid is ever wanted, the ceiling needs deliberate access
ports and the void must be verified connected through them. Simpler to use
`RIB_SHELL`, which has no ceiling and stays open to the plate.

---

## 2026-08-20 — Project phase model

**DECIDED.** Two phases: a small complete pilot, then the full-size final.

*Why:* At the owner's estimate of up to 20 h per full-size tile, a 20-tile
final build is ~400 machine-hours. Discovering a pipeline error at that point
is expensive. The pilot validates every stage end-to-end for roughly 25 hours
and under half a kilogram of filament.

---

## 2026-08-20 — Tile size cap of 200 mm

**DECIDED.** Longest tile edge ≤ 200 mm, with 230 mm available as a documented
exception.

*Why:* The X1C's advertised 256 mm envelope is an outer limit, not a reliable
working size. Large flat-bottomed parts lift at the corners, and prime lines,
exclusion zones and brims consume the edges. 200 mm prints unattended without
tuning; the project prefers reliability over squeezing out the last 20%.

---

## 2026-08-20 — Base slab at 10 mm

**DECIDED.** The lowest elevation (0.19 m, Columbia River) sits 10 mm above the
build plate.

*Why:* Owner requirement. Provides rigidity for a wall-mounted plate and a
substrate for registration and mounting features.

---

## 2026-08-20 — Road treatment: engrave, with paint-fill as the colour path

**PROVISIONAL** — to be confirmed on the pilot.

Engraved grooves as the primary geometry treatment. Colour delivered by
paint-filling grooves rather than by AMS filament changes.

*Why:* On a heightfield, roads span the full Z range of a tile, so colouring
them by filament forces a tool change on nearly every layer. Measured with
`scripts/color_cost.py`: a four-colour bike palette at 2" relief wastes ~283 g
per tile in purge — more than the tile itself — rising to ~1.1 kg per tile at
the 8" relief ceiling. Across 20 tiles that is ~23 kg of waste. Engraving costs
nothing in purge, prints more reliably than raised features, and paint-filling
removes the four-colour AMS limit entirely.

*To confirm:* print one showcase tile with AMS road colour on the pilot and
compare it directly against a paint-filled tile before finalising.

---

## 2026-08-20 — AMS reserved for elevation banding

**PROVISIONAL.**

Use the AMS for Z-height elevation bands, not XY road colour.

*Why:* Banding costs one tool change per band per tile — roughly 2 g of purge
for six bands, about 150× cheaper than XY colour. Band edges must be set once
in a shared profile so they align across tiles.

---

## 2026-08-20 — Working CRS

**DECIDED.** EPSG:6559 (NAD83(2011) / Oregon North, metres) or EPSG:32610
(UTM 10N). Never EPSG:4326 for any distance, buffer or slope operation.

*Why:* PortlandMaps vectors arrive in Web Mercator (EPSG:3857), which
overestimates distances by ~35% at Portland's latitude. Buffering road
centrelines in Web Mercator would produce roads a third too wide.

---

## OPEN — Final wall dimensions

Owner is measuring candidate wall locations. Blocks: scale, tile count,
exaggeration, filament budget, backer panel size.

Once measured, run:
```
python3 scripts/topo_params.py grid --max-tile-mm 200
python3 scripts/topo_params.py plan --wall-width-mm <measured> --cols C --rows R
# 7x6 is now the squarest grid at a 200mm cap (aspect 0.994, 42 tiles)
```

---

## OPEN — Vertical exaggeration

Owner has stated a tolerance ceiling of ~8" (203 mm) of projection off the
wall. **This is a limit, not a target.**

At a 5×4 / 200 mm final grid, 8" requires **16.7× exaggeration**, ~11.0 kg of
filament and ~636 hours. Conventional relief maps use 1.5–3×; dramatic display
pieces 3–6×. (Regenerated 2026-08-24 for the resized bbox.)

Note that buying relief with *wall area* rather than *exaggeration* produces a
more natural result: at a 7×6 grid the same 8" of projection needs **11.1×**,
and 6" needs 8.2×.

**Corrected 2026-08-24:** an earlier revision of this entry claimed 7×6 at 8"
needed "only ~8×". That was the 6" row misread as the 8" row. The mistake had
propagated into `docs/01` and into the project memory note.

To be decided from the physical exaggeration ladder in `docs/09-pilot-run.md`.

---

## OPEN — Mounting system

Backer panel with embedded magnets is the current recommendation (doc 08).
Blocked on final dimensions and on measured tile mass.

---

## 2026-08-25 — Measured slicer cost across layer heights and both nozzles

**MEASUREMENT, not yet a decision.** Bambu Studio, stock profiles, no per-print
overrides. One plate = 2 tiles (a full-coverage flat tile and a West Hills
tile). Contour interval = layer / 0.02211 mm-per-metre at relief 8.0 mm.

```
profile            noz  contour  per plate   grams  solid infill  x0.20 time
0.20mm Standard    0.4    9.05m       1h41   43.09    16.03g  37%       1.00x
0.16mm Optimal     0.4    7.24m       1h57   46.31    20.38g  44%       1.16x
0.12mm Fine        0.4    5.43m       2h09   39.98    13.47g  34%       1.28x
0.08mm HighQual    0.4    3.62m       4h39   43.09    17.73g  41%       2.76x
0.10mm Standard    0.2    4.52m       6h14   38.15    16.44g  43%       3.70x
0.08mm Standard    0.2    3.62m       6h51   37.43    15.84g  42%       4.07x
0.06mm Standard    0.2    2.71m       8h17   37.30    15.82g  42%       4.92x
```

### Three findings

**1. The 0.2 mm nozzle is dominated on this geometry.** At the same 0.08 mm
layer — therefore the same contour interval and the same vertical detail — the
0.4 nozzle finishes in 4h39 and the 0.2 nozzle in 6h51. The 0.2 nozzle buys
only XY resolution, at +2h12 per plate. **This corrects the 2026-08-24
estimate of "6-10x" for the 0.2 nozzle.** The real penalty is ~1.5x against
the same layer height, because these tiles are shell-dominated rather than
volume-dominated, and the volume-based estimator does not model that. If fine
layers are wanted, get them on the 0.4 nozzle.

**2. `0.12mm Fine @ 0.4` is the value pick.** 28 minutes more than 0.20
Standard per plate, contour interval 9.05 m -> 5.43 m, and it uses the *least*
filament of any 0.4-nozzle profile (39.98 g). `0.16mm Optimal` is strictly
worse than it: more time, the most filament of any profile tested (46.31 g),
and a coarser contour interval.

**3. Internal solid infill is 34-44% of the mass in every profile tested** —
13-20 g per plate, against only 8-10 g of sparse infill. This is the
heightfield's conformal top shell: the top surface slopes continuously, so the
solid shell under it is a thick slab following the terrain rather than a few
flat layers. Top-shell layers / thickness is therefore a bigger material lever
than either layer height or sparse infill density, and it has not been touched.
Reduce cautiously — on a slope the shell's perpendicular thickness is less than
its layer count implies, so pinholes appear sooner than on a flat top.

### Also observed

- Plates are currently ganged 2 tiles x 6 plates. Prepare time is 7-11 min per
  plate, so that arrangement spends ~45-65 min on fixed overhead. 6+4 across
  two plates recovers about 40 min.
- The 0.4-nozzle profiles add a brim (2m4s, 0.85 g); the 0.2-nozzle ones do not.
  The comparison is not perfectly like-for-like on that line.

---

## 2026-08-25 — 0.12mm Fine vs 0.12mm High Quality, settings diff

Same plate (r02c02 + r02c03), same nozzle, same layer height, same filament.
`Fine` 2h00m / 40.68 g. `High Quality` 3h04m / 40.65 g.

**The two profiles differ in exactly two places.**

Speed (mm/s), "other layers":

```
                        High Quality     Fine
Outer wall                        60      200
Inner wall                       150      350
Sparse infill                    180      430
Internal solid infill            180      350
Top surface                      150      200
Gap infill                       230      350
```

Acceleration (mm/s^2): normal printing 4000 -> 10000, outer wall 2000 -> 5000.
Everything else in the accel and jerk tables is identical.

Strength: sparse infill pattern **Gyroid** (HQ) vs **Cross Hatch** (Fine).
Every other Strength value matches — 2 wall loops, 5/5 top/bottom shell layers,
0.6 mm top shell thickness, 100% surface density, Monotonic surfaces, 25%
overlap, 15% sparse density.

Quality (layer height, all nine line widths, seam) and the whole Other tab
(skirt, brim, special mode, G-code) are identical.

### The finding that matters for this project

**The visible surface prints identically in both profiles.**

```
                 High Quality     Fine
Top surface           10m58s    10m57s
Bottom surface         6m16s     6m16s
Travel                17m18s    17m10s
```

Top surface is nominally 33% faster in Fine (150 -> 200 mm/s) and comes out one
second slower. The terrain top is tens of thousands of short monotonic
segments; the toolhead is acceleration-bound and never reaches either commanded
speed. The same is true of travel. All 64 minutes of the difference come out of
walls and infill:

```
                 High Quality     Fine    saved
Sparse infill         51m53s    20m15s   31m38s
Internal solid        38m58s    24m08s   14m50s
Outer wall            24m38s    15m50s    8m48s
Inner wall            13m44s     9m10s    4m34s
Internal bridge       12m19s     9m49s    2m30s
```

Material is a wash: 40.65 g vs 40.68 g. Cross Hatch uses 0.15 g more sparse
infill than Gyroid and prints it in 31 fewer minutes, so the pattern change is
not what saves the time — the 180 -> 430 mm/s speed is.

**Conclusion: `Fine` is the correct profile for these tiles.** The only quality
HQ actually buys is on the outer wall (60 vs 200 mm/s, 2000 vs 5000 accel) —
crisper corners and less ringing on the *vertical* faces. On a wall-mounted map
viewed face-on that is the least-seen surface, though it is also the
boundary-cut silhouette, so judge it on the test print rather than from here.

Not captured in the screenshots, so not compared: Fine's Precision / Ironing
panel and its Overhang-speed and Travel-speed values.
