# D6 · Verification plan (DRAFT, CR-1 first)

Status: draft, 22 Oct 2026. CR-1 is written out first; CR-2 to CR-4 follow the same pattern once
their ERs are drafted (`docs/D1-engineering-requirements.md`). For each ER: method, apparatus,
sample size, acceptance criterion and who signs it off.

## Apparatus: the bench rig

| Part | What we use | Status |
| --- | --- | --- |
| Test lung | Reservoir bag from the mask kit, filled with one exhalation (about 4–5 % CO2) | CO2 source to confirm with the instructor |
| Mask / T-piece | Kit item | Asked for; only the mask set has arrived |
| Sampling line | Mask kit oxygen tubing, 1.0 m (0.5 and 2.0 m for the delay-versus-length ER) | Ready to cut |
| Water trap | Kit item, or a printed one | Asked for |
| Flow-cell | `hardware/cad/` v1 tray and lid on the MH-Z19C, seams taped | Ready to print |
| Monitor | Pico 2 W, firmware v0.3 (`lib/cr1.py`) | Laptop-tested; load next session |
| Run control | Mac running `tools/scripted_run.sh` (spoken cues, log, scoring) | Written; first try on the Mac next session |
| Reference | Sim-lab capnograph: calibration and validation only, never a live channel | To book |

## CR-1 · ER-1 (present within 3 breaths) and ER-2 (absent within 30 s)

Both ERs are measured in the same scripted run.

| | ER-1 | ER-2 |
| --- | --- | --- |
| Method | Scripted run: spoken cue on every beat; count the cues up to the moment the board shows CO2 PRESENT | Same run: seconds from the "Stop" cue to the moment the board shows CO2 ABSENT |
| Sample size | 10 runs at 10 breaths/min and 10 runs at 20 breaths/min | The same 20 runs |
| Acceptance | 3 breaths or fewer in 10 of 10 runs at each rate | 30 s or less in 10 of 10 runs at each rate |
| Evidence | `data/runs/results.csv` and the run logs in `data/raw/` | Same |
| Signed off by | Requirements and verification lead | Same |

**Procedure**

1. Assemble the rig. Leak test: pinch the flow-cell outlet and squeeze the bag; it must stay full.
2. Power the board; wait for ABSENT (warm-up takes 75 s). Nobody breathes toward the flow-cell.
3. Fill the bag with one exhalation; refill before every run.
4. Run `bash tools/scripted_run.sh --rate 10 --breaths 10 --cue squeeze --label r10-runNN`
   (60 s of cues), or `--rate 20 --breaths 20 --label r20-runNN`. Squeeze once on every "squeeze".
5. The tool records 120 s of recovery and scores the run. It refuses to start the next run until
   the board shows ABSENT again.
6. Note any deviation (missed squeeze, bag leak, fault) in the lab notebook against the run label.

**Specificity controls** (for the D7 sensitivity and specificity figures)

- 5 runs with the sampling line connected to a bag of room air (no CO2): must stay ABSENT in 5 of 5.
- 5 runs with the bag disconnected while a person breathes normally at the bench: must stay ABSENT
  in 5 of 5. On 22 Oct, in open air, this case read PRESENT. The flow-cell exists to fix it.

**Before the rig exists:** replaying the 22 Oct open-air readings through the v0.3 logic gives
PRESENT during breath 3 (11 s) and ABSENT 17 s after the last breath (`tests/test_cr1.py`). That is
a design check, not verification.

## Open items

- CO2 source and the T-piece, sampling line and water trap (instructor).
- Dilution or a higher-range sensor: undiluted breath pins the sensor at 5,000 ppm, which makes
  "present" easy and may slow "absent". The thresholds (+100 ppm rise; fall of 10 % of the rise)
  are re-checked on the first rig runs before the 20 counted runs.
