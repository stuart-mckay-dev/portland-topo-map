# 08 — Assembly and Mounting

## Mass is a structural question

Run `topo_params.py` for the active configuration and read the total kilograms.
A 6×5 final build at 6" of relief is over 13 kg. That is not a picture-hook
load — it needs studs or proper anchors.

Weigh the first few tiles and update `PRINT_RATE_CM3_PER_HR` and
`SOLID_FRACTION` in the script so the total estimate converges on reality.

## Recommended: backer panel

Mount a rigid backer (plywood, MDF, or aluminium composite) to the wall studs,
then attach tiles to the backer.

**Why this and not tile-to-tile registration alone:** alignment tolerance
accumulates. Across a 5-tile row, five joints each off by 0.2 mm produce a 1 mm
error at the far end, and the last tile will not sit flush. Anchoring every
tile to one flat reference plane stops the accumulation. It also lets you build
the piece on a table, hang it in sections, and take it down without
disassembling the map.

Sizing: cut the backer to the exact finished wall dimension from
`topo_params.py`. Check the number twice — this is the one irreversible cut.

Attachment options, tiles to backer:

| Method | Pros | Cons |
|---|---|---|
| VHB tape | Trivial, strong, thin | Permanent |
| Magnets (6×3 mm, embedded) | Removable individual tiles | Cost across 20+ tiles, must be embedded during printing |
| Screws through backer into tile bosses | Fully serviceable | Requires access behind |
| Hook-and-loop | Cheap, removable | Thick, allows tiles to shift |

**Magnets** are the best fit for a piece you may want to repair or extend.
Model the pockets in Fusion (doc 05), and pause the print to drop them in — or
design blind pockets accessible from the back face.

## Alternative: French cleat per row

Each tile row gets a cleat. Good if the wall is uneven or the piece is very
large. Rows are independently removable. Weaker on cross-row alignment than a
backer, so combine with tile-to-tile registration keys.

## Assembly order

1. **Dry-fit the whole grid on a flat table before mounting anything.**
   Cumulative error shows up here, cheaply.
2. Mark the backer with the tile grid — snap lines, do not eyeball it.
3. Start from the centre and work outward, so any accumulated error ends up
   distributed at the perimeter rather than concentrated in one corner.
4. Fit registration keys as you go.
5. Mount the backer to the wall **last**, unless the piece is too heavy to lift
   assembled — in which case mount the backer first and build in place, working
   centre-outward.

## Seam management

Seams are the visible failure mode. Ranked by effectiveness:

1. **Shared-edge DEM sampling** (doc 03) — fixes the cause, not the symptom.
   Nothing else matters if this is wrong.
2. **Deliberate seams.** A small chamfer on each tile's top edge turns a ragged
   butt joint into a crisp intentional grid line. Counterintuitive but it looks
   far better than a seam that is *trying* to be invisible and failing.
3. **Fill and blend.** Wood filler or UV resin, sanded and painted. Highest
   effort, best result, and it makes the piece non-disassemblable.

**Recommendation: option 2.** A visible, even, intentional grid reads as a
design choice. An almost-invisible seam reads as a defect.

## Finishing

- **Bare PLA.** Fine, especially with elevation banding doing the visual work.
- **Paint-filled grooves.** See doc 07. Highest visual return for the effort.
- **Dry-brushing.** Light grey or white dry-brushed over dark filament catches
  the ridges and dramatically enhances perceived relief. Cheap, fast, very
  effective on terrain.
- **Matte clear coat.** Kills FDM's plastic sheen and unifies tiles printed
  from different spool batches. Worth doing if the tiles came from more than
  one spool — colour drift between batches is real and shows across a seam.

## Lighting

Relief maps live or die on raking light. Plan for a light source **above and to
one side**, not straight on. A picture light or an angled track head will make
the West Hills read from across the room; flat frontal lighting will flatten
the whole piece. Consider this before choosing the wall.
