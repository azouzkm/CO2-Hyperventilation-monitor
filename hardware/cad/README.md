# Printed parts

## Version 1 (22 Oct 2026): sized from the datasheet, before caliper measurements

| File | What it is | Size (mm) | Prints |
| --- | --- | --- | --- |
| `barb_fit_coupon_v1.stl` | Five test barbs, 4.8 to 6.4 mm, marked with 1 to 5 dots. Push the oxygen tubing onto each and keep the one that grips best. | 60 × 14 × 9 | First, ~10 min |
| `flowcell_tray_v1.stl` | Open tray the MH-Z19C lies in; its cable leaves through the notch in the end wall | 51.3 × 27.5 × 15.6 | Open side up, ~45 min |
| `flowcell_lid_v1.stl` | Flat lid that drops into a ledge in the tray. Inlet barb (next to the raised dot) sits over the sensor's gas window; outlet barb at the far end | 48.5 × 24.7 × 10.1 | Barbs up, ~20 min |

`PRINT_SHEET_v1.pdf` (and `.png`) is the one-page request for whoever prints. `preview_v1_3d.png` and
`preview_v1_section.png` show the parts and a cut through the middle with the sensor in place.

All parts print in PLA without supports. Times are rough; the slicer gives the real ones.

### STEP files

For print services and CAD programs that want STEP rather than STL, the same three parts are in
`barb_fit_coupon_v1.step`, `flowcell_tray_v1.step` and `flowcell_lid_v1.step` (AP214, millimetres).
`PRINT_SHEET_v1_step.pdf` (and `.png`) is the print request that lists them, and `preview_v1_step.png`
is rendered from them. They are exact solids (flat faces, cylinders and cones, not triangles), so a CAD
program can measure and edit them.

`make_step.py` writes them from the same numbers as `make_parts.py`, and checks at 40,000 points that
its solids match `make_parts.py`'s shapes before writing. Checked on 22 Oct by reading the files back
with OpenCascade (the CAD kernel FreeCAD, PrusaSlicer and Bambu Studio use to open STEP): each opens
as one closed solid of the design's size, with the same volume as the STL to within 0.2 %.

## Putting it together

1. Stick a pad of double-sided foam tape (about 1.5 mm) on the tray floor.
2. Plug the cable into the sensor. Lay the sensor on the pad with the **gold chamber up**, the
   connector toward the notch, and the cable out through the notch.
3. Drop the lid into the ledge, **dot end over the notch end**: the inlet barb then sits over the
   white filter, which is the sensor's gas window.
4. Seal: one turn of electrical tape around the top edge covers the lid seam; press tape or
   reusable putty around the cable in the notch.
5. Push the sampling line onto the **inlet** barb. Leave the outlet open, pointing away from the bench.

**Checks:** pinch the outlet and squeeze the test-lung bag: the bag should stay full (no leak). Then
squeeze it with the outlet open: the reading should start rising within a few seconds.

## Design notes

- Nothing touches the gold chamber. The Winsen manual says not to press on it from any direction,
  so the sensor rests on its board and foam, with 1.5 mm of air on every side and above.
- Free gas volume inside is about 6.5 mL. At about 3 mL/s of sample flow that flushes in roughly 2 s,
  small next to the sensor's own rise of 11 to 13 s measured on 22 Oct. Version 2 can shrink it once
  the parts are measured.
- Breath is about 50,000 ppm CO2 and the sensor tops out at 5,000 ppm. Whether to dilute the sample
  (for example with a printed Venturi that mixes in a fixed share of room air) is a team decision;
  this tray and lid work either way.

## Version 1 as printed (25 Oct 2026)

- All three parts printed and used. Photos: `docs/photos/2026-10-25_*.jpg`; how the lid closes:
  `flowcell_closing_steps.png`.
- **Barbs:** the oxygen tubing was not a good fit on any of the coupon's five barbs, but sits firmly
  and correctly on the lid's 5.6 mm barbs, so `BARB_RIDGE` stays 5.6.
- **Lid** drops into the ledge as designed. Sealed with electrical tape on the seam and the notch;
  the leak test passed.
- **For version 2:** move the inlet barb about 3.5 mm across the width so it sits squarely over the
  white filter. Decide on airflow first: a sealed cell holds the last breath, which read as CO2
  present with nobody breathing (lab notebook, 25 Oct). A pump, or a flush port, changes the lid.

## Measurements for version 2

Change these numbers at the top of `make_parts.py`, then run `python3 hardware/cad/make_parts.py`
(it needs numpy and scikit-image) to rebuild every STL, and `python3 hardware/cad/make_step.py`
(numpy only) to rebuild every STEP file.

| Parameter | Measure | v1 estimate |
| --- | --- | --- |
| `BOARD_LEN` | Green board, end to end, including the connector tab | 37.5 |
| `HOUSING_W` | Gold housing width | 19.7 |
| `SENSOR_H` | Underside of the board to the top of the gold housing | 8.6 |
| `BOARD_TO_HOUSING` | Connector end of the board to the start of the gold housing | 9.7 |
| `WINDOW_LEN` | White filter, along the board's length | 8.3 |
| `PLUG_OUT` | How far the plugged-in cable plug sticks out past the board end | 6.0 |
| `BARB_RIDGE` | Coupon barb that grips the tubing best: 1 dot = 4.8, 2 = 5.2, 3 = 5.6, 4 = 6.0, 5 = 6.4 | 5.6 |

Also note for the record: the tubing's inside and outside diameter, the gold housing's length, and
the three board holes (diameter and position), which version 2 can use to hold the sensor in place.

## Next parts

Smaller cup straight over the gas window (version 2), dilution Venturi (if the team chooses it), a
water trap (if the kit one does not arrive), the indicator panel (light ring, frosted dome, button,
speaker), and the board enclosure.
