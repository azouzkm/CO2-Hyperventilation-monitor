# D1 · Engineering requirements (DRAFT)

Status: first draft, 22 Oct 2026, from the open-air bench session in `docs/lab-notebook.md`;
ER-7 and ER-8 (CR-4) added 27 Oct 2026, from the 22 Oct paced run and simulation.
Every number below is to be confirmed on the bench rig (test lung, sampling line, flow-cell)
before it is final. Up to eight ERs in total; each states a range, rate, latency or accuracy,
has a pass/fail acceptance criterion, and names the CR it serves.

## The plain statement the card asks for

On 22 Oct the MH-Z19C took 11–13 s to rise and about a minute to settle after a breath, and
breathing at 15/min left only about 2 ppm of ripple per breath on a 1,000 ppm rise. **This
hardware supports a breath-averaged trend, not breath-by-breath capnography.** The ERs below
are written for a trend instrument and must not be presented as capnography.

## Drafted

| ID | Traces to | Requirement | Acceptance | Evidence so far (22 Oct, open air) |
| --- | --- | --- | --- | --- |
| ER-1 | CR-1 | The device shall display "CO2 present" within **3 breaths** after exhaled gas first reaches the sampling inlet, at 10 to 20 breaths/min. | 10 of 10 scripted runs on the bench rig at 10 and at 20 breaths/min | Rhythmic run: +100 ppm above room air at breath 3 (11 s at 15/min). Firmware v0.3 uses that +100 ppm rise; replayed on the 22 Oct readings it shows PRESENT during breath 3. In open air an operator breathing nearby also triggers it, so the flow-cell is part of meeting ER-1 |
| ER-2 | CR-1, CR-2 | The device shall display "CO2 absent" within **30 s** (about 7 breaths at 15/min) after exhaled gas stops reaching the sampling inlet. | 10 of 10 scripted runs | The fall was visible 17 s after stopping, but the reading only got back near room air after 89 s (about 22 breaths). Firmware v0.3 calls absence from the trend (a fall of 10 % of the rise within 20 s); replayed on the 22 Oct readings it shows ABSENT 17 s after the last breath |

| ER-7 | CR-4 | The device shall show the breathing rate derived from the CO2 signal, updated every **2 s**, from **5 to 20 breaths/min**, within **±1 breath/min** (or ±10 %, the larger) of the true rate. When the rhythm is not clear it shall show "not resolved" instead of a number, and it shall **never show a rate below 80 %** of the true one. | Paced runs with `tools/rate_run.sh` at 6, 10, 15 and 20 breaths/min, 5 runs each. In every phase, from 50 s in: a rate shown at least 80 % of the time, its median within tolerance, no value below 80 % of the paced rate | 22 Oct paced run (open air, 15/min): 15.0–15.7/min from 31 s into the run until it ended, then "not resolved". No rate at all in the other 2.8 h of bench readings (22 and 25 Oct). Simulation: within 0.6/min whenever shown, from 6 to 20/min. The upper limit (20) is a placeholder: the slower the sensor and cell, the lower the fastest countable rate, so it is set from the bench runs |
| ER-8 | CR-4 | The device shall raise the **ADVISORY** alarm (amber, 3 pulses) on a sustained fall: (a) within **90 s** of breathing slowing below 8/min or to 60 % of the patient's own rate; (b) within **60 s** of the breath-averaged CO2 above room air falling 30 % below its own level. It shall return to NORMAL after **30 s** back in range, and raise **no** advisory during steady breathing. | (a) Paced runs 15 → 6 → 15/min (the `tools/rate_run.sh` default plan), 10 runs: advisory within 90 s in 10 of 10, back to NORMAL in each. Specificity: 5 runs of 10 min steady breathing at 12/min, no advisory in 5 of 5. (b) No controlled CO2 fall on the bench yet: replayed recordings or simulation, reported as a design check | Simulation: a rate below 8/min shown 30–48 s after slowing from 15 to 6/min, advisory 60–78 s after; CO2 falling by half over 2 min: advisory 45–52 s after the fall reached 30 % (117–124 s after it began); no false advisory in 135 ten-minute runs of steady breathing |

Both CR-4 requirements need air moving through the flow-cell. In the sealed cell of 25 Oct, the
breaths piled up (the reading held up to 5,000 ppm for minutes), so there was no rise and fall to
count, and the rate was never shown.

## Still to draft (suggested)

| ID | Traces to | Topic |
| --- | --- | --- |
| ER-3 | CR-1, CR-4 | 10–90 % response time of the full gas path, measured and published, with its delay versus sampling-line length (0.5, 1, 2 m) |
| ER-4 | CR-2 | Alarm latency when CO2 is lost while the circuit reads connected |
| ER-5 | CR-3 | Blocked or disconnected line (break-wire loop) reported as a technical fault within N s, never as apnoea |
| ER-6 | CR-3 | Wet water trap (probe) reported as a technical fault |

## Open questions for the team and the instructor

- **5,000 ppm ceiling:** exhaled air is about 50,000 ppm. Dilute the sample (for example a printed
  Venturi) or substitute a higher-range sensor? Undiluted, a hypoventilation fall (ER-8) is invisible.
- **Presence threshold:** +100 ppm is fast but was exceeded by an operator breathing nearby; the
  flow-cell should remove that, to be confirmed.
- **Self-calibration:** switch it off for bench runs so the baseline cannot move during the term.
- **Airflow and dilution for CR-4:** the rate needs air moving through the cell (pump or flushes)
  and readings below the 5,000 ppm top of the scale (dilution). Undiluted breath would pin the
  sensor at the top, where the rhythm is cut off: the firmware then shows "not resolved".
