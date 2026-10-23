# D1 · Engineering requirements (DRAFT)

Status: first draft, 22 Oct 2026, from the open-air bench session in `docs/lab-notebook.md`.
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

## Still to draft (suggested)

| ID | Traces to | Topic |
| --- | --- | --- |
| ER-3 | CR-1, CR-4 | 10–90 % response time of the full gas path, measured and published, with its delay versus sampling-line length (0.5, 1, 2 m) |
| ER-4 | CR-2 | Alarm latency when CO2 is lost while the circuit reads connected |
| ER-5 | CR-3 | Blocked or disconnected line (break-wire loop) reported as a technical fault within N s, never as apnoea |
| ER-6 | CR-3 | Wet water trap (probe) reported as a technical fault |
| ER-7 | CR-4 | Breathing rate from the CO2 signal: range and accuracy (the 22 Oct slope showed the 15/min rhythm faintly; test with the cap) |
| ER-8 | CR-4 | Alarm on a sustained fall in CO2 (hypoventilation), with the fall size and duration stated |

## Open questions for the team and the instructor

- **5,000 ppm ceiling:** exhaled air is about 50,000 ppm. Dilute the sample (for example a printed
  Venturi) or substitute a higher-range sensor? Undiluted, a hypoventilation fall (ER-8) is invisible.
- **Presence threshold:** +100 ppm is fast but was exceeded by an operator breathing nearby; the
  flow-cell should remove that, to be confirmed.
- **Self-calibration:** switch it off for bench runs so the baseline cannot move during the term.
