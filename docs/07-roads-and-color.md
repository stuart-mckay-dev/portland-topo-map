# 07 — Roads, Bike Network and Colour

Two treatments are in scope, per the owner's decision: **engraved road geometry**
and **AMS colour**. This document covers both, plus the bike-network colour
extensions, and it starts with the constraint that governs the whole choice.

## The governing constraint: colour by Z is cheap, colour by XY is not

This is the single most important thing to understand before designing the
colour scheme.

On a relief map the terrain is a **heightfield** — one Z per XY position. A
road drawn on that surface follows the terrain, so it appears at almost every
Z height in the tile. If the road is a different filament, the printer must
change tools on almost **every layer**, and every tool change purges filament.

An elevation band, by contrast, occupies a contiguous slab of Z. Colouring by
elevation costs one tool change **per band, per tile.**

```
$ python3 scripts/color_cost.py --tile-height-mm 50.8 --colors 4 --part-g 210

======================================================================
  Tile height 50.8mm | layer 0.2mm | 4 colours | flush 300 mm3/change
======================================================================

  STRATEGY A -- colour roads/bike routes by XY position
    layers in tile                   254
    tool changes                     762
    purge waste                      229 cm3   (283 g)
    waste / part mass                1.3 x

  STRATEGY B -- colour by elevation band (Z only), 6 bands
    tool changes                       5
    purge waste                     1.50 cm3   (1.9 g)

  Strategy A costs 152x more filament in purge alone.

```

At a 2"-tall tile with a four-colour bike palette, the purge waste **exceeds
the mass of the tile itself**. Scaling up makes it worse:

```
$ python3 scripts/color_cost.py --sweep

Purge waste per tile, STRATEGY A (XY road colour), 0.2mm layers
grams of wasted filament, by tile height and palette size

    tile H      2 col      3 col      4 col      6 col
------------------------------------------------------
   25.4mm        47        94       142       236
   50.8mm        94       189       283       472
   76.2mm       142       283       425       709
  101.6mm       189       378       567       945
  152.4mm       283       567       850     1,417
  203.2mm       378       756     1,134     1,890

(at 300 mm3/change; a tuned-down matrix at 130 cuts these by 57%)


Purge waste per tile, STRATEGY B (elevation bands)

     bands      grams
----------------------
         3        0.7
         4        1.1
         6        1.9
         8        2.6
        12        4.1
        16        5.6

```

Read the bottom-left of the first table: at the owner's 8" relief ceiling with
a four-colour bike palette, that is **1.1 kg of wasted filament per tile.**
Across a 20-tile build, ~23 kg of purge — several times the mass of the
artwork, and the purge tower for a 1000-layer print is itself a large object
competing for plate space.

Mitigations exist but do not change the order of magnitude:

- **Tune the flush matrix.** Bambu's stock volumes are conservative. Choosing
  colours close in lightness and hand-tuning the matrix can roughly halve it.
- **Purge into infill / sparse regions.** Bambu Studio can redirect transition
  extrusions into the object's own infill. Helps meaningfully on a solid tile
  like this one. Do not use with translucent filament.
- **Purge into a useful object.** Print the next tile's registration keys as
  the purge object.

None of these make XY road colour cheap. Plan accordingly.

---

## Treatment 1 — Engraved roads (recommended primary)

Roads cut as shallow grooves into the terrain surface. Single filament.

**Why it works here:** grooves are geometry, not colour, so they cost nothing
in purge. They print reliably — a groove is just a gap in the top solid layers,
with no thin fragile features to break and no minimum-extrusion-width dropout.
They catch shadow under raking light, which is how relief maps have always
communicated line work. And they survive handling and dusting.

**Implementation:** a second Displace modifier in Blender driven by a road
mask, not a boolean. See `docs/04-blender-workflow.md` step "Engraving roads".

**Parameters to test on the pilot:**

| Parameter | Start at | Notes |
|---|---|---|
| Groove depth | 0.35 mm | Under 0.25 mm tends to vanish; over 0.6 mm starts to read as a canyon |
| Groove width | 0.8–1.2 mm | Must exceed one extrusion width (0.42 mm) or the slicer drops it |
| Mask blur | 1–2 px | Gives groove walls a slight chamfer; a hard mask prints ragged |
| Layer height | 0.12–0.16 mm | Finer layers resolve grooves noticeably better |

**Width in ground terms:** `ground_width_m = printed_mm × scale_denom / 1000`.
At 1:31,250 a 1.0 mm groove is a 31 m ground corridor. That is roughly a real
arterial right-of-way — so at this scale, engraving *every* street produces a
surface that is more groove than terrain. **Filter by street classification.**
Arterials and collectors only, for the base map.

**The upgrade path:** engraved grooves can be **paint-filled**. Flood the
surface with a thinned acrylic wash, then squeegee or wipe the high surfaces
clean — pigment stays in the grooves. This is the panel-lining technique from
scale modelling. It gives you sharp, saturated, multi-colour line work for
**zero purge cost**, and it is the honest answer to "I want coloured bike
routes on a 20-tile build". Different classes can be filled with different
colours using paint pens or masking. Test it on a pilot tile.

---

## Treatment 2 — AMS colour

### 2a. Elevation banding (cheap, recommended)

Change filament at fixed Z heights so the map reads as a coloured contour
diagram. Costs one change per band per tile — single-digit grams.

Band edges should be chosen in **real elevation**, then converted to model Z:

```
model_z_mm = 10 + (elevation_m - 0.19) × Z_factor
```

Get `Z_factor` from `topo_params.py`. A natural Portland set:

| Band | Elevation | Reads as |
|---|---|---|
| 1 | 0–15 m | Rivers, floodplain, Columbia bottomland |
| 2 | 15–45 m | Inner eastside, most of the flat grid |
| 3 | 45–90 m | Lower slopes, Alameda Ridge |
| 4 | 90–150 m | Mt Tabor, Rocky Butte, lower West Hills |
| 5 | 150–250 m | West Hills body, Powell Butte summit |
| 6 | 250–362 m | Council Crest, the high ridge |

Note the bands are **not** equal-width. Portland's elevation distribution is
heavily bottom-weighted; equal bands would put most of the city in one colour.

> Caveat: banding is applied at slicing time by Z height, so a band boundary is
> a perfectly horizontal contour across the whole tile. That is the intended
> look. It also means band edges must be identical across every tile or they
> will not line up on the wall — set them once, in the project profile.

### 2b. Roads by colour (expensive)

Requires roads as separate mesh bodies assigned to a different filament, not a
groove. See the cost analysis above before proposing this for more than a
single showcase tile.

If you do it: model the road solids as thin bodies that sit *in* the engraved
grooves (an inlay), so the colour occupies the groove volume. Import terrain
and inlay as parts of one object in Bambu Studio and assign filaments per part.

---

## Bike network colour extensions

Both extensions use the **Bicycle Network** layer (ID 75) from PortlandMaps.
Filter to `Status = 'ACTIVE'` first. Field domains are documented in
`docs/02-data-sources.md`.

### Extension 1 — Greenways vs. everything else

Two road classes, two colours.

| Class | Filter | Suggested colour |
|---|---|---|
| Bike greenway | `Facility = 'NG'` or `SCS = 'GREENWAY'` | Green |
| All other roads | everything else | Default road colour |

Cost: a 3-colour tile (terrain + road + greenway). At 2" relief, ~189 g of
purge per tile — already significant across 20 tiles.

**Recommended implementation:** engrave both classes, paint-fill the greenways
green and leave the others unfilled (or fill grey). Purge cost: zero.

### Extension 2 — Differentiate by bike infrastructure type

The `Facility` field carries the full classification. A sensible palette that
maps colour to *protection level*, which is the thing a viewer actually cares
about:

| Code | Facility type | Suggested colour | Rationale |
|---|---|---|---|
| `TRL` | Off-Street Path / Trail | Dark green | Fully separated from traffic |
| `PBL` | Protected Bike Lane | Bright green | Physical protection |
| `NG` | Neighborhood Greenway | Light green | Low-traffic shared street |
| `BBL` | Buffered Bike Lane | Yellow-green | Painted buffer only |
| `BL` | Bike Lane | Yellow | Paint only |
| `SIR` | Separated in-Roadway | Orange | |
| `ESR` | Enhanced Shared Roadway | Orange-red | Shared with traffic |
| `ABL` | Advisory Bike Lane | Red | Least protection |

That is eight classes — more than the AMS's four slots, and far more than the
purge budget allows. **Two ways to make it work:**

1. **Collapse to four classes.** Separated (`TRL`,`PBL`) / Greenway (`NG`) /
   Painted (`BBL`,`BL`,`SIR`) / Shared (`ESR`,`ABL`). Four colours fits the AMS
   exactly, and the collapsed grouping is arguably more legible anyway.
2. **Engrave all eight, paint-fill by class.** No AMS limit, no purge, full
   palette. Fiddlier by hand, but this is a wall piece you build once.

**Recommendation:** engrave + paint-fill for the final. Use AMS elevation
banding for the terrain body, since that is nearly free, and reserve AMS road
colour for one showcase pilot tile so you can see it before committing.

---

## Decision summary

| Goal | Method | Purge cost |
|---|---|---|
| Streets legible at close range | Engraved grooves, arterials/collectors only | none |
| Terrain reads as topographic | AMS elevation banding, 6 bands | ~2 g/tile |
| Greenways distinguished | Engrave + green paint fill | none |
| Full bike facility palette | Engrave + paint fill by class | none |
| Bike routes in true filament colour | AMS by XY, 4 colours | 280 g–1.1 kg/tile |

Test all of it on the pilot before the final commits 400 machine-hours.
