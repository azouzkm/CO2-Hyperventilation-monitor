# Laptop tools

The tools run in the macOS Terminal, from the repository folder, and each finds the Pico's serial
port by itself. The shell tools need nothing installed; `dashboard.sh` sets up its Python packages
on its first run. Only one program can hold the serial port at a time: the dashboard,
`live_co2.sh`, `scripted_run.sh`, Thonny or Mu.

| Tool | What it does |
| --- | --- |
| `dashboard.sh` | Starts the laptop service and opens the dashboard at <http://localhost:8000>: the box's state live, alarm sounds, acknowledge, the CO₂ trend, the alarm log and messages to phones (sign up at <http://localhost:8000/register>). Every line from the board is saved to `data/raw/`. The first run installs Flask, pyserial and certifi into `.venv/` (needs the internet once). Stop with Ctrl-C. See [dashboard/README.md](../dashboard/README.md) |
| `live_co2.sh` | Live view of the board's output in Terminal, one line per second, saved to `data/raw/co2_<date>.log`. With firmware v0.5 the log also holds one JSON line per reading for the service; the screen hides them. Stop with Ctrl-C |
| `scripted_run.sh` | One verification run for CR-1 with spoken cues, scored at the end |
| `score_run.sh` | Scores a run log again (for example with different acceptance numbers) |
| `rate_run.sh` | One paced-breathing run for CR-4 with spoken cues, in phases (default 15 → 6 → 15 breaths/min, `--plan 15:150,6:150,15:120`), scored at the end by `score_rate_run.py` for ER-7 (rate shown) and ER-8 (advisory on slowing), into `data/runs/rate_results.csv`. Needs air moving through the cell |
| `score_rate_run.py` | Scores a paced run log again: `python3 tools/score_rate_run.py data/raw/rate_<date>.log` |
| `calibration.py` | Calibration fit (slope, intercept, RMS residual) and 10–90 % response time, for D7. Python with numpy and matplotlib (`python3 -m pip install -r requirements.txt`); placeholder data until the reference sessions |

## The dashboard

```
bash tools/dashboard.sh
bash tools/dashboard.sh --replay data/raw/co2_2026-10-25_011421.log --speed 5
bash tools/dashboard.sh --lan
bash tools/dashboard.sh --no-messages
```

The first form reads the board. The second plays the 25 Oct alarm test five times faster, with no
board needed: handy for showing the dashboard or trying a change (it sends no alarm messages to
phones). The third also lets a phone or tablet on the same Wi-Fi open it. The fourth sends no
messages to phones at all: use it for bench tests that pull wires on purpose. Click **Turn on alarm
sound** once in the browser.

If the service stops on an error, the script starts it again after 2 s; it gives up after three
quick failures in a row and says why. Ctrl-C or closing the window stops it for good. To check
that the box does not depend on the laptop (failure mode FM-5), stop the service mid-run: the box
keeps its light and sound, and the dashboard shows *No service* until it is back.

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
macOS commands (`say`, `stty -f`) and still need a first try on the Mac. The JSON lines of firmware
v0.5 do not affect the scoring, which reads the text lines and the banners.
