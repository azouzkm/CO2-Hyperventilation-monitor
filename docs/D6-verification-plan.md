# D6 · Verification plan (DRAFT, CR-1 first)

Status: draft, 22 Oct 2026; CR-4 (ER-7, ER-8) added 27 Oct. CR-2 and CR-3 follow the same pattern
once their ERs are drafted (`docs/D1-engineering-requirements.md`). For each ER: method,
apparatus, sample size, acceptance criterion and who signs it off.

## Apparatus: the bench rig

| Part | What we use | Status |
| --- | --- | --- |
| Test lung | Reservoir bag from the mask kit, filled with one exhalation (about 4–5 % CO2) | CO2 source to confirm with the instructor |
| Mask / T-piece | Kit item | Asked for; only the mask set has arrived |
| Sampling line | Mask kit oxygen tubing, 1.0 m (0.5 and 2.0 m for the delay-versus-length ER) | Ready to cut |
| Water trap | Kit item, or a printed one | Asked for |
| Flow-cell | `hardware/cad/` v1 tray and lid on the MH-Z19C, seams taped | Ready to print |
| Monitor | Pico 2 W, firmware v0.3 (`lib/cr1.py`) | Laptop-tested; load next session |
| Run control | Mac running `tools/scripted_run.sh` (CR-1) and `tools/rate_run.sh` (CR-4): spoken cues, log, scoring | Written; first try on the Mac next session (`rate_run.sh` checked against a simulated board) |
| Airflow | A pump on the flow-cell outlet, or room-air flushes, with the sample diluted below 5,000 ppm | Needed for CR-4: asked the instructor about the pump |
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

## CR-4 · ER-7 (breathing rate) and ER-8 (advisory on a sustained fall)

Both are measured in the same paced runs. `tools/rate_run.sh` speaks one cue per breath through a
plan of phases ("rate:seconds") and scores the run with `tools/score_rate_run.py`.

| | ER-7 | ER-8 (a), slow breathing | ER-8, specificity |
| --- | --- | --- | --- |
| Method | Paced phases; the rate the board shows (the "RR" column) is compared with the paced rate from 50 s into each phase to its end | Plan 15 → 6 → 15/min: seconds from the start of the slow phase to the ADVISORY banner, and to NORMAL after it | Steady breathing at 12/min for 10 min: count the advisories |
| Sample size | 5 runs at each of 6, 10, 15 and 20/min (plans `6:180`, `10:180`, `15:180`, `20:180`) | 10 runs of the default plan (`15:150,6:150,15:120`) | 5 runs (plan `12:600`) |
| Acceptance | In every phase: a rate shown at least 80 % of the scored time, median within ±1/min (or ±10 %), no value below 80 % of the paced rate | Advisory within 90 s in 10 of 10, back to NORMAL within the last phase | No advisory in 5 of 5 |
| Evidence | `data/runs/rate_results.csv` and the run logs `data/raw/rate_*.log` | Same | Same |
| Signed off by | Requirements and verification lead | Same | Same |

**Procedure**

1. Rig as for CR-1, with air moving through the flow-cell (pump or flushes) and the sample diluted
   below 5,000 ppm: in the sealed cell of 25 Oct no rhythm reached the sensor.
2. Wait for ABSENT. Nobody else within 1 m.
3. Run, for example, `bash tools/rate_run.sh --plan 15:150,6:150,15:120 --cue squeeze --label slow-runNN`.
   Squeeze the bag (or breathe out) on every cue; the first cue of a phase says "slower" or "faster".
4. The tool records 60 s after the stop and prints, for each phase, the rate shown, ER-7, and the
   advisory or the return to NORMAL (ER-8).
5. Note any deviation (a missed or doubled breath, a bag refill) in the lab notebook against the label.

**ER-8 (b), a slow fall of CO2:** no way yet to make a controlled fall of the CO2 level on the
bench. Until there is one (for example a known dilution step), it is checked by replaying recorded
readings and by simulation (`tests/test_cr4.py`), and reported as a design check, not verification.

**Before the rig has airflow:** the 22 Oct open-air paced run reads 15.0–15.7/min, and nothing in
2.8 h of other readings shows a rate or an advisory (`tests/test_cr4.py`). A dry run of the board
program on simulated breathing passes all three phases of the default plan (`tests/test_rate_run.py`).
Design checks, not verification.

## Open items

- CO2 source and the T-piece, sampling line and water trap (instructor).
- Dilution or a higher-range sensor: undiluted breath pins the sensor at 5,000 ppm, which makes
  "present" easy and may slow "absent". The thresholds (+100 ppm rise; fall of 10 % of the rise)
  are re-checked on the first rig runs before the 20 counted runs.
