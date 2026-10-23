# Firmware (Raspberry Pi Pico 2 W, CircuitPython 9.2.9)

This folder is an exact copy of what belongs on the Pico's `CIRCUITPY` drive.

> **22 Oct, 02:00:** v0.3 is written and tested on the laptop against the 22 Oct readings, but is
> **not on the board yet** (the board was unplugged). Load it at the start of the next session.
> The board still runs v0.2, which is kept in `archive/bench-monitor-v0.2/`.

| File | Purpose |
| --- | --- |
| `boot.py` | Runs once at power-up: asks the sensor for one CO2 reading and writes the result to `boot_out.txt` on the drive |
| `code.py` | Main program, **monitor v0.3**: shows whether exhaled CO2 is PRESENT or ABSENT (CR-1), one reading per second with a bar and the state, a `>>>` banner at every state change, and the response timing of each CO2 event |
| `lib/cr1.py` | The CR-1 logic: WARMING UP → ABSENT ⇄ PRESENT, plus FAULT. Present = a fresh rise of 100 ppm; absent = a fast fall from the recent peak, or back near where the rise started |
| `lib/indicator.py` | Shows the state on the Pico's LED now, and on the light ring once it is soldered |
| `lib/co2events.py` | Event detection and timing (room level, peak, 10-90 % rise, 90-10 % fall) |
| `lib/mhz19c.py` | Driver for the Winsen MH-Z19C CO2 sensor; works with the two data wires either way round |

Earlier versions: `archive/wiring-test-2026-10-21/` (LED wiring test), `archive/bench-monitor-v0.2/`,
and the team's first outline in `archive/team-skeleton-firmware/`.
Laptop tests: `tests/test_cr1.py` replays the real 22 Oct readings (present by breath 3 and absent
17 s after the last breath in the rhythmic run; both stuck-at-400 faults caught), and
`tests/test_co2events.py` dry-runs `code.py` with a simulated sensor.

## What the board shows

| State | Meaning | Pico LED | Light ring (after soldering) |
| --- | --- | --- | --- |
| WARMING UP | First 75 s after power-on; readings are placeholders | Slow even blink | Amber |
| ABSENT | No exhaled CO2 reaching the sensor | Short blink every 2 s | Red |
| PRESENT | Exhaled CO2 detected | Steady on | Green |
| FAULT | No answer from the sensor, or stuck at 400 ppm (check the brown calibration wire) | Fast blink | Cyan, blinking |

To switch the light ring on once it is wired to the D16 socket, set `RING_PIN = board.GP16` at the
top of `code.py`. Brightness is capped at 8 % (`lib/indicator.py`); for an RGBW ring set `RING_BPP = 4`.

## Deploying

1. Plug the Pico into the laptop; the `CIRCUITPY` drive appears.
2. Copy the `lib/` folder first, then `boot.py` and `code.py` (replace existing files).
3. **Eject the drive** in Finder before unplugging. Unplugging during a copy has corrupted
   the drive before. If Finder says the disk is in use, Force Eject is safe once nothing is
   being copied (the Claude app keeps the folder open while it is connected).
4. `code.py` restarts by itself after every file written to the drive, so copy `lib/` before
   `code.py`, and don't update the board in the middle of a test run. `boot.py` only runs after
   unplugging and replugging the board.

## Reading results

- **Live view on the Mac:** `bash tools/live_co2.sh` in Terminal, from the repository folder.
  One line per second, also saved to `data/raw/`. Stop with Ctrl-C. Close Thonny/Mu first: only
  one program can hold the serial port.
- **Verification runs:** `bash tools/scripted_run.sh`; see `tools/README.md`.
- **`boot_out.txt`:** after a replug, its last line reads `CO2 OK: <ppm> ppm, wires <normal|swapped>`
  or `CO2: NO REPLY either way`. The ppm there is a warm-up placeholder (the sensor needs about
  75 s); it only proves the connection.
- **Before any test:** wait for the ABSENT state (or `room level: ... ready for a test`), and keep
  people at least 1 m from the sensor (their breathing shows up).

## Next

- Print one JSON line per sample for the laptop service (the format planned in the team's outline).
- Read the alarm thresholds from `config.json`, the file the service uses too.
- The four card alarm states (Normal, Advisory, Critical, Technical) with the speaker and the
  acknowledge button, once they are soldered.
