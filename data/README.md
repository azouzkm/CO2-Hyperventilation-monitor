# Data

Evidence for the verification report (D7). Everything here is committed, including the raw
Terminal logs, so every number in the report can be traced back to the readings it came from.

| Folder | What goes in it |
| --- | --- |
| `data/` (this folder) | Labelled datasets, one CSV per session, named `YYYY-MM-DD_what.csv` |
| `raw/` | Terminal logs from `tools/live_co2.sh` and `tools/scripted_run.sh`, exactly as recorded |
| `runs/` | `results.csv`: one row per scripted CR-1 run, scored against ER-1 and ER-2 by `tools/score_run.sh` |
| `calibration/` | Readings taken against the reference, and the fit from `tools/calibration.py` |

## 2026-10-22_session2_readings.csv

One reading per second from the MH-Z19C, 00:25:35 to 01:45:09 on 22 Oct 2026 (Mac clock),
open-air bench (no cap or sampling line yet). Source: `data/raw/co2_2026-10-22_002533.log`
(`co2_2026-10-22_002533_snapshot_0146.log` is an identical copy taken at 01:46).

| Column | Meaning |
| --- | --- |
| `mac_time` | Mac clock time the line arrived |
| `seconds_since_power_up` | Board time since the sensor was powered (it was replugged at about 00:20) |
| `co2_ppm` | Sensor reading |
| `label` | What was happening (below). Boundaries are approximate, set from the operator's notes |
| `firmware_note` | What the board printed beside the reading (`event`, `STUCK AT FLOOR`, ...) |

| Label | When | What |
| --- | --- | --- |
| `room_air` | everything else | Nobody breathing at the sensor on purpose |
| `operator_nearby` | 00:25:48-00:25:58, 00:29:20-00:33:59, 01:00:00-01:05:59, 01:16:30-01:19:59 | Operator typing or handling wires within arm's reach: raised the reading by up to about 900 ppm |
| `fault_stuck_at_400_hd_wire_suspected` | 00:25:59-00:29:19 | Reading held at exactly 400 ppm while the sensor's brown HD (zero-calibration) wire lay under the laptop's grounded case |
| `fault_stuck_at_400_cause_unconfirmed` | 01:31:46-01:34:26 | Reading jumped 846 → 400 → 5,000 → 400 and stayed at 400; HD tip already insulated. Wiring or sensor glitch, cause not confirmed |
| `recovery_after_fault` | 01:34:27-01:37:36 | Reading climbing back, overshooting to 2,265 ppm, then settling near 910 |
| `breath_test_1` | 00:40:10-00:42:59 | One breath toward the sensor from about 15 cm |
| `breath_test_2` | 00:55:00-00:57:29 | Same, second time |
| `rhythmic_run_1_breathing` | 01:10:04-01:11:04 | 15 to 16 breaths in 60 s toward the sensor from about 15 cm |
| `rhythmic_run_1_recovery` | 01:11:05-01:13:59 | Operator 1 m back, hands off |

The firmware was reloaded six times during the session (00:39:45 to 00:57:56) while it was being
updated; readings continue across those restarts, but on-board event summaries near them are partial.

## Session 3 raw logs (25 Oct 2026)

First readings through the printed flow-cell (sealed, no airflow through it), and the alarm test.
No labelled CSV: these were set-up and exploratory runs, not counted ones. What happened when is in
the lab notebook (`docs/lab-notebook.md`, session 3).

| Log | Mac clock | Firmware | What |
| --- | --- | --- | --- |
| `raw/co2_2026-10-25_000608.log` | 00:06-00:30 | v0.3 | First breaths through the tube (00:15:00) and flushes (00:16:02) |
| `raw/co2_2026-10-25_003225.log` | 00:32-00:47 | v0.3, light ring | Breath at 00:32:58 (fastest real rise, 654 ppm/s); false PRESENT from trapped gas at 00:38:35 |
| `raw/co2_2026-10-25_011421.log` | 01:14-02:04 | Speaker and button, then v0.4 from 01:39:43 | Button checks; the alarm test from 01:46 (breath, flush, button, pulled data wire, re-warm, hold) |
