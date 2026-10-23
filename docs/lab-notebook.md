# Lab notebook

Dated record of what we did and found. Findings here feed the design rationale (D2) and
the failure-mode table (D8). Newest entries at the top.

## 2026-10-22 · Session 2: power-on, first readings, first breath tests

**Bring-up**

- **Sensor answers.** LED steady at power-on; `boot_out.txt` read `CO2 OK: 500 ppm, wires normal`
  (twice, after two power-ups). The 500 ppm is the sensor's warm-up placeholder (read 2 s after
  power-on), not a measurement.
- **Data wires follow the datasheet after all:** blue = sensor RXD on GP0 (Pico TX), green =
  sensor TXD on GP1 (Pico RX). The 21 Oct failures were the unstripped wire ends, not the colours.
- **Supply:** 5.18 V at the Pico's VBUS pad (pass 4.75-5.25) and 3.31 V at its 3V3 pad (pass
  3.20-3.40). 5.18 V is above the sensor's nominal 5.0 ± 0.1 V but inside the 4.5-5.5 V its
  manual allows.

**Failure modes seen (for D8)**

- **USB data link dropped** mid-session ("Disk Not Ejected Properly") while the board stayed
  powered, LED on. Replugging fixed it. Second time (first: 21 Oct). Mitigation ideas: short
  known-good cable, a printed strain-relief clip, the laptop service treating "no data for N s" as
  a technical fault.
- **Calibration wire to ground:** the sensor's brown HD wire lay under the MacBook, whose metal
  case is at USB ground. While it touched (00:25:59 to 00:29:19) the reading sat at exactly
  400 ppm, the bottom of the scale. Freed, the reading came back to about 840 ppm, close to the
  850 before, so no lasting zero shift was seen (to confirm with a fresh-air check). Done: tip
  insulated and taped back; firmware v0.2 now flags 30 s at 400 ppm as a sensor fault (Terminal
  warning, slow LED blink). Open: remove or seal the HD wire for good (team decision).
- **Stuck at 400 a second time, cause unconfirmed:** at 01:31:46, after the HD tip was already
  insulated, the reading jumped 846 → 400 → 5,000 (12 s, top of the range) → 400, sat there until
  01:34:27, then climbed to 2,265 ppm and settled near 910. Jumps that big in 1 s are not real CO2:
  this is the sensor or its wiring, not the air. Candidates: the HD wire touching ground again, or a
  brief loss of sensor power through the thin breadboard leads while the bench was handled. After
  both episodes the reading overshot before settling, so treat the first 3 minutes after one as
  untrustworthy. The FAULT check caught both. Next session: check the HD tape, and wiggle red and
  black one at a time while watching for FAULT.
- **Operator breath is a confounder:** breathing while typing within arm's reach raised the
  reading by 800 to 900 ppm, more than a deliberate breath. Rule for test runs: operator at least
  1 m back; the flow-through cap must shield the sensor from room air.

**Tools added:** firmware v0.2 (one reading per second with a bar, breath-event timing, stuck-at-400
fault) and `tools/live_co2.sh` (live view in Terminal, saved to `data/raw/`). Two detection bugs
found on real data and fixed with tests: a restart mid-breath took the top of the breath as the room
level, and a slow rise lost its 10 % point ("rise n/a").

**After the session (until about 02:15):** firmware v0.3 with the CR-1 present/absent logic
(`lib/cr1.py`), LED and light-ring display (`lib/indicator.py`), and `tools/scripted_run.sh`
(spoken cues, scored for ER-1/ER-2). Replayed on tonight's readings: PRESENT during breath 3 and
ABSENT 17 s after the last breath in the rhythmic run; both stuck-at-400 episodes flagged as FAULT.
Not on the board yet. Draft CR-1 verification plan in `docs/D6-verification-plan.md`.

**Measurements** (open air, about 15 cm from the sensor, one reading per second)

| Run | Room air | Peak above room | First rise | Rise 10-90 % | Fall 90-10 % | Back near room air |
| --- | --- | --- | --- | --- | --- | --- |
| Breath 1, 00:40:10 | 843 ppm | +598 ppm at 20 s | 1 s | 12.7 s | 51 s | 81 s |
| Breath 2, 00:55 | 812 ppm | +309 ppm | 6 s after the stated time | 10.6 s | 66 s | 93 s after first rise |
| Rhythmic, 01:10:04, 15-16 breaths in 60 s | 802 ± 2.5 ppm | +1,014 ppm at 52 s (levelling off) | 7 s (breath 2) | 31 s (whole run) | 71 s | 89 s after stopping |

Rhythmic run in breaths (15/min): +100 ppm at breath 3, +300 ppm (the board's event threshold) at
breath 6, +500 ppm at breath 8. After stopping: falling after 17 s, half-way at 41 s, within
+50 ppm of room air at 113 s. Each breath left only about 2 ppm of ripple on the 1,000 ppm rise,
though the slope still shows the rhythm at about 15/min.

**What it means**

- CR-1 presence looks feasible within about 3 breaths with a +100 ppm threshold, once the cap keeps
  room air (and the operator) out.
- Absence called from the level takes about 22 breaths: far too slow. It has to come from the trend.
- This hardware supports a breath-averaged trend, not breath-by-breath capnography.

Data: `data/2026-10-22_session2_readings.csv` (labelled). Figures: `docs/figures/2026-10-22_*.png`.
Next: fresh-air zero check, self-calibration off (team decision), caliper measurements, print the
v1 parts in `hardware/cad/`, then repeat the runs through the cap and sampling line.

## 2026-10-21 · Sensor identification and first wiring

- **Sensor identified** from its label: Winsen MH-Z19C, 400–5000 ppm, 7-wire terminal
  cable. It talks UART, not I2C, so the Grove-to-Qwiic cables are not needed for it.
- **Board drive had no name** (left over from last week's interrupted copy); renamed to
  `CIRCUITPY`. Label change only, nothing erased.
- **USB data link is intermittent:** the board powered up (its Wi-Fi network was visible)
  while the Mac saw no drive. Replugging firmly fixed it. Candidate failure mode for D8.
- **Wiring attempt 1:** black wire one hole too high (GP1 instead of GND). Pin check found
  no signal on any pin: sensor unpowered.
- **Wiring attempt 2:** black moved to a GND hole. The sensor's output showed on **GP0**
  with blue in GP0 and green in GP1, the opposite of what the datasheet pin order implies.
- **Wiring attempt 3:** blue and green swapped; no signal on any pin again, suggesting
  loose header contacts.
- **Change:** driver rewritten to work with the data wires either way round, and a live
  LED test put on the board (steady = answering, blinking = no answer) so contacts can be
  checked without replugging.
- **Open:** confirm a reading, record the wire orientation in `hardware/wiring.md`.
  (Closed 22 Oct: reading confirmed, orientation `normal`.)
