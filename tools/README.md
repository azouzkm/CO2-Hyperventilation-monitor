# Laptop tools

The shell tools run in the macOS Terminal with nothing to install; each finds the Pico's serial
port by itself. Only one of them (or Thonny/Mu) can hold the port at a time. Commands below run
from the repository folder.

| Tool | What it does |
| --- | --- |
| `live_co2.sh` | Live view of the board's output, one line per second, saved to `data/raw/co2_<date>.log`. Stop with Ctrl-C |
| `scripted_run.sh` | One verification run for CR-1 with spoken cues, scored at the end |
| `score_run.sh` | Scores a run log again (for example with different acceptance numbers) |
| `calibration.py` | Calibration fit (slope, intercept, RMS residual) and 10–90 % response time, for D7. Python with numpy and matplotlib (`python3 -m pip install -r requirements.txt`); placeholder data until the reference sessions |

## A scripted run, step by step

```
bash tools/scripted_run.sh --rate 15 --breaths 15 --label lung15-run01 --cue squeeze
```

1. **Quiet (20 s):** "Scripted run. Stand back and stay still." The tool checks the board shows
   ABSENT; if not (still warming up, a fault, or CO2 left over from the last run) it stops and says so.
2. **Countdown:** "Get ready. Three. Two. One."
3. **Breaths:** the Mac says "breathe" (or "squeeze") on every beat, 15 times at 15 per minute.
   Breathe out, or squeeze the test-lung bag, on each word.
4. **Stop:** "Stop. Step back." Then 120 s of recovery, with "90 seconds", "60 seconds", "30 seconds".
5. **Score:** printed and appended to `data/runs/results.csv`:
   - **ER-1:** breaths until the board showed CO2 PRESENT (pass at 3 or fewer)
   - **ER-2:** seconds from "Stop" until it showed CO2 ABSENT (pass at 30 s or fewer)
   - peak reading, drop-outs (ABSENT while still breathing), and whether a sensor fault made the run invalid

Options: `--rate` breaths per minute (15), `--breaths` cues (15), `--rest` recovery seconds (120),
`--settle` quiet seconds (20), `--cue` the spoken word (breathe), `--label` a name for the run,
`--er1` / `--er2` acceptance numbers (3 breaths / 30 s), `--force` to start even if the board is not ABSENT.

Re-score any run: `bash tools/score_run.sh data/raw/run_<date>_<label>.log 3 30`.

The scoring was checked on a run rebuilt from the real 22 Oct rhythmic test: PRESENT during
breath 3 (11 s), ABSENT 17 s after the stop: both pass. The spoken cues and serial handling use
macOS commands (`say`, `stty -f`) and still need a first try on the Mac.
