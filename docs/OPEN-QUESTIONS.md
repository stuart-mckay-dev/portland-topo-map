# Open Questions

Read this at the start of any session. Anything resolved moves to
`docs/DECISIONS.md` with a date.

## Blocking Phase 2 (the final build)

### 1. Final wall dimensions
**Owner action.** Measuring candidate locations at home.

Needed: available width and height, in inches, for each candidate spot; and
whether the piece must fit a specific gap or can be sized freely.

Everything downstream depends on this. Once known:
```
python3 scripts/topo_params.py grid --max-tile-mm 200
python3 scripts/topo_params.py plan --wall-width-mm <W> --cols C --rows R
```

### 2. Vertical exaggeration
**Empirical.** To be chosen from printed coupons, not from a screen.

The ladder is specified in `docs/09-pilot-run.md`. Ceiling of 8" is a tolerance,
not a goal — see `docs/DECISIONS.md` for what 8" actually costs.

## Blocking the pilot

### 3. DEM source: 3DEP vs DOGAMI
Both are viable. 3DEP is easier (already a bare-earth raster, bbox subsetting,
guaranteed metres). DOGAMI is sometimes crisper in the West Hills but ships by
quadrangle and may be in international feet.

*Suggested:* start with 3DEP. Compare a West Hills crop against DOGAMI before
the final, not before the pilot.

### 4. Which streets to engrave
At 1:31,250 a 1 mm groove is a 31 m ground corridor. Engraving every street
would leave more groove than terrain.

Needs a decision on classification filter — arterials only, or arterials plus
collectors. Best judged from a pilot tile with three test filters side by side.

### 5. Registration method
Dovetail keys, alignment pins, or rabbet edges (doc 05). Depends on whether the
piece must be disassemblable.

*Question for the owner:* is this permanent, or might it move house?

### 5b. Hollow strategy confirmation
**Empirical.** `docs/10` recommends per-tile RIB_BOX / RIB_SHELL, 6 mm shell,
25–30 mm ribs. Two coupons can invalidate the whole approach and should be run
first:

- **HOLLOW-4** — does 5% support with no interface actually pull out through
  the open bottom, or does it shear off and stay in?
- **HOLLOW-6** — does a perimeter-only first layer survive a 20-hour print with
  an 8 mm brim, or does it detach?

If either fails, fall back to `RIB_BOX` everywhere (support-free) and accept
~10% instead of ~21%.

*Question for the owner:* is tearing support out of the tall tiles worth ~150 g
per tile, versus `RIB_SHELL` which needs no removal at all but saves slightly
less? Three tiles' worth of picking at 5% support is a real evening.

## Non-blocking, decide later

### 5c. Recessed mounting, and its collision with hollowing
**Owner direction, 2026-08-24:** mounting will be **recessed into the print** so
the plinth stays minimal, invisible, and adds no height — pockets under the
terrain where depth allows, rather than a raised boss or a thick tray.

Two things settled already:

- **Depth IS the constraint now.** *Revised 2026-08-24, after the base slab
  went 10 mm -> 4 mm.* The old note here said depth was a non-issue because
  every tile carried at least 10 mm everywhere; a 6 x 3 mm magnet left 7 mm
  above it anywhere on the map. At 4 mm that is no longer true — a 3 mm-deep
  pocket leaves 1 mm of floor over it at the river, which is two 0.4 mm walls
  and will telegraph or blow out. Consequences:
  - Mounts can no longer go *anywhere*. They must sit under terrain that
    carries enough local relief: at relief 8.0 mm full-range, 3 mm of extra
    material means ground above roughly 135 m elevation.
  - Or use thinner hardware: a 1.5 mm magnet or a steel washer + adhesive
    leaves 2.5 mm of floor at the river, which is printable.
  - Or reinstate a local thickening under each mount point rather than a
    global base increase — the plinth stays invisible and adds no height,
    which is what the owner asked for.
  This needs deciding before tiles are re-exported for the final wall; it does
  **not** block the pilot, which is not being mounted.
- **Hollowing is the constraint.** `docs/10` puts ribs and a void in exactly the
  space a recessed pocket wants, and a `RIB_BOX` ceiling **seals** that void
  (see the 2026-08-24 entry in `DECISIONS.md`). A pocket above a sealed ceiling
  is unreachable and unprintable. Pockets must sit in the open-bottom region, or
  the tile must use `RIB_SHELL`, which stays open to the plate.

*Resolve alongside the HOLLOW-* coupons, not before.* Deciding pocket positions
before knowing which hollowing strategy each tile uses would fix them in the
wrong place.



### 6. Do the rivers get their own treatment?
Options: flat plane at true elevation, recessed below the floodplain, or a
separate AMS colour. A recessed channel reads well but is not topographically
honest.

### 7. Border / frame
A 3–5 mm raised perimeter makes the piece read as finished, but makes perimeter
tiles non-interchangeable.

### 8. Bike facility palette depth
Extension 1 (greenway vs. other) or Extension 2 (eight facility classes,
collapsed to four for AMS or kept at eight for paint-fill). See doc 07.

*Suggested:* build Extension 1 into the pilot, decide on Extension 2 after
seeing how much line work the map can carry before it gets busy.

### 9. Finish
Bare PLA, dry-brushed, paint-filled grooves, matte clear coat, or a combination.
Test on pilot tiles.
