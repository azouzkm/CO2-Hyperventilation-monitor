# Firmware (Raspberry Pi Pico 2 W, CircuitPython 9.2.9)

This folder is an exact copy of what belongs on the Pico's `CIRCUITPY` drive.

> **25 Oct:** **v0.4, the test alarm.** The four alarm states of the project card (Figure 3) now
> drive the light ring and the speaker, and the button acknowledges or stops them. CR-1 also
> catches the 22 Oct sensor glitches at their first impossible reading, so a failing sensor can
> no longer look like a patient who stopped breathing. Speaker still straight off the pin through a
> resistor (quiet) until the PAM8302 amplifier is soldered (`hardware/soldering-speaker-button.pdf`).
> v0.3 (CR-1 colours on the ring, no alarm states) stays in the git history.

| File | Purpose |
| --- | --- |
| `boot.py` | Runs once at power-up: asks the sensor for one CO2 reading and writes the result to `boot_out.txt` on the drive |
| `code.py` | Main program, **monitor v0.4**: one reading per second with a bar, the CR-1 state and the alarm state, a `>>>` banner at every change, and the response timing of each CO2 event |
| `lib/cr1.py` | CR-1: WARMING UP → ABSENT ⇄ PRESENT, plus FAULT. Present = a fresh rise of 100 ppm; absent = a fast fall from the recent peak, or back near where the rise started |
| `lib/alarm.py` | The alarm states on top of CR-1: STANDBY, NORMAL, ADVISORY, CRITICAL, TECHNICAL, and the button rules |
| `lib/indicator.py` | Light ring (D16 / GP16) and the Pico's LED: colour and flash pattern for each state |
| `lib/annunciator.py` | Speaker (PWM on GP18) and button (GP20): the alarm sounds, played in the background, and press / hold detection |
| `lib/co2events.py` | Event detection and timing (room level, peak, 10-90 % rise, 90-10 % fall) |
| `lib/mhz19c.py` | Driver for the Winsen MH-Z19C CO2 sensor; works with the two data wires either way round |

Laptop tests (`python -m pytest tests/`, 44 tests): `tests/test_cr1.py` and `tests/test_alarm.py`
replay the real 22 Oct readings (present by breath 3, absent and CRITICAL 17 s after the last
breath of the rhythmic run; both sensor faults TECHNICAL, never CRITICAL), and
`tests/test_co2events.py` dry-runs `code.py` with a simulated sensor, light ring, speaker and button.

## What the board shows

| Alarm state | When | Light ring | Sound |
| --- | --- | --- | --- |
| STANDBY | Warming up, or no breath seen yet: not monitoring | One white light circling | None |
| NORMAL | Exhaled CO2 present | Green, steady | None |
| ADVISORY | A sustained fall in CO2 (CR-4). **Not triggered yet** | Amber, slow flash | 3 pulses, every 20 s |
| CRITICAL | CO2 lost after it was present. Latched: stays until the button, even if CO2 comes back | Red, fast flash (steady once acknowledged) | 10 pulses (3+2+3+2), every 10 s |
| TECHNICAL | Any sensor problem, and the 3-minute re-warm after it | Cyan, steady | Chirp, every 30 s |

At power-up: green, amber, red, cyan for 0.4 s each (lamp test), then a rising two-tone chirp
(speaker test). The sounds follow the pattern of medical alarms (IEC 60601-1-8): 10 pulses for high
priority, 3 for medium, and the light flashes faster the higher the priority.

**Button:** a short press acknowledges a critical alarm: sound off for 2 minutes, light steady red.
If CO2 is back, the press clears the alarm to NORMAL; if not, the alarm sounds again after the
2 minutes. Holding the button for 3 s stops monitoring (falling two-tone, back to STANDBY); it starts
again at the next breath.

**Golden rule (CR-3): an equipment problem is TECHNICAL, never CRITICAL.**
- A sensor FAULT in CR-1 is: no answer; a reading stuck at 400 ppm (the bottom of the scale, which
  room air never reaches) for 30 s; or a reading that jumps more than real CO2 can move through
  this sensor in one second, a fall of over 400 ppm or a rise of over 1,200 ppm. The fastest real
  changes in all the bench runs were 163 ppm/s down and 654 ppm/s up (a breath straight into the
  flow cell, 25 Oct). The 22 Oct glitches were 1,006 to 4,600 ppm in one second: before this rule,
  the first one (1,784 to 778 ppm) read as "CO2 lost".
- A single reading of 400 ppm is a suspected fault at once (TECHNICAL), not data.
- After a fault the sensor is trusted again only after a 3-minute re-warm: on 22 Oct the reading
  overshot to 2,265 ppm while it recovered, which read as CO2 PRESENT for 90 s.
- Once trusted again, if CO2 is absent the monitor waits 30 s for a breath (still TECHNICAL), then
  calls CRITICAL ("no CO2 in the 30 s since the sensor came back"). The patient is still protected,
  but the end of a re-warm cannot raise a false alarm.
- The other way round, a fault never hides a patient alarm: a CRITICAL already latched stays
  CRITICAL through a fault, with a banner saying there is a sensor problem too. To see the cyan
  state, pull a data wire while the ring is green or white.
- While the sensor does not answer, each reading waits for it (0.5 s per try, both wire
  orientations), and the light, sound and button keep running during that wait. Found on the bench
  25 Oct: before this, a pulled data wire froze the ring on steady red and stopped the bursts.

Brightness is capped at 8 % (`lib/indicator.py`); for an RGBW ring set `RING_BPP = 4`. Pins are at
the top of `code.py` (`RING_PIN`, `SPEAKER_PIN`, `BUTTON_PIN`).

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
  one program can hold the serial port. Each line reads, for example,
  `t= 312 s  CO2  1814 ppm  |##########....|  PRESENT    NORMAL`: the CR-1 state, then the alarm.
- **Verification runs:** `bash tools/scripted_run.sh`; see `tools/README.md`.
- **`boot_out.txt`:** after a replug, its last line reads `CO2 OK: <ppm> ppm, wires <normal|swapped>`
  or `CO2: NO REPLY either way`. The ppm there is a warm-up placeholder (the sensor needs about
  75 s); it only proves the connection.
- **Before any test:** wait for the ring to circle white (STANDBY) and the line to show ABSENT,
  and keep people at least 1 m from the sensor (their breathing shows up).

## Next

- CR-4 (hypoventilation, the ADVISORY state), from the slow fall of the CO2 peaks.
- The break-wire loop, so a disconnected sampling line is a TECHNICAL alarm too (CR-2 / CR-3).
- Print one JSON line per sample for the laptop service (the format planned in the team's outline).
- Read the alarm thresholds from `config.json`, the file the service uses too.
