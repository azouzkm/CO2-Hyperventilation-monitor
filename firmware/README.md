# Firmware (Raspberry Pi Pico 2 W, CircuitPython 9.2.9)

This folder is an exact copy of what belongs on the Pico's `CIRCUITPY` drive.

> **1 Nov:** **v0.6, breathing rate (CR-4) and the safety clip (CR-3).** Each line now ends in the
> breathing rate ("RR 15.2", or "RR --" when it cannot be resolved, with the reason in a banner), and
> the ADVISORY state works: breathing below 8/min (or 40 % below the patient's own rate), or the
> breath-averaged CO2 30 % below its own level, for 30 s. The safety clip on the sampling line
> (GP21 to GND) makes a disconnected tube TECHNICAL "LINE OFF" within about a second, never CRITICAL
> (tested at the bench 1 Nov). A reading stuck at the top of the scale (5,000 ppm) for 30 s is
> TECHNICAL, since the sensor can then not see breaths (1 Nov: a sealed cell full of breath showed
> green for 6 minutes with nobody breathing). A CRITICAL alarm now ends once it is acknowledged and
> CO2 is back, in either order (the card's Figure 3). CR-1 waits 12 s without a new rise before
> calling CO2 absent, so the swing of each breath through a ventilated cell is not an absence. The
> JSON line adds `rr`, `rr_why`, `advisory` and `line`.
>
> **26 Oct:** **v0.5, the link to the dashboard.** Each reading now also goes out as one JSON line
> (interface IF-6) for the laptop service, next to the text line, and the board accepts the
> dashboard's acknowledge over USB (`ACK`), handled exactly like a short press of its button. The
> light, the sound, the button and every alarm rule are unchanged, and the board still decides
> every alarm itself. Only `code.py` changed.
>
> **25 Oct:** **v0.4, the test alarm.** The four alarm states of the project card (Figure 3) now
> drive the light ring and the speaker, and the button acknowledges or stops them. CR-1 also
> catches the 22 Oct sensor glitches at their first impossible reading, so a failing sensor can
> no longer look like a patient who stopped breathing. Speaker still straight off the pin through a
> resistor (quiet) until the PAM8302 amplifier is soldered (`hardware/soldering-speaker-button.pdf`).
> v0.3 (CR-1 colours on the ring, no alarm states) stays in the git history.

| File | Purpose |
| --- | --- |
| `boot.py` | Runs once at power-up: asks the sensor for one CO2 reading and writes the result to `boot_out.txt` on the drive |
| `code.py` | Main program, **monitor v0.6**: one reading per second with a bar, the CR-1 state, the alarm state and the breathing rate, a `>>>` banner at every change, and the response timing of each CO2 event; the same reading as one JSON line for the laptop service, and the dashboard's `ACK` |
| `lib/cr1.py` | CR-1: WARMING UP → ABSENT ⇄ PRESENT, plus FAULT. Present = a fresh rise of 100 ppm; absent = a fast fall from the recent peak, or back near where the rise started |
| `lib/alarm.py` | The alarm states on top of CR-1: STANDBY, NORMAL, ADVISORY, CRITICAL, TECHNICAL, and the button rules |
| `lib/cr4.py` | CR-4: the breathing rate from the rhythm of the CO2 signal (every 2 s over 64 s; shown only when it can be backed, never a falsely low rate) and the ADVISORY on a sustained fall |
| `lib/lineclip.py` | CR-3: the safety clip on the sampling line (GP21, pull-up; loop open = tube off), debounced 0.3 s |
| `lib/indicator.py` | Light ring (D16 / GP16) and the Pico's LED: colour and flash pattern for each state |
| `lib/annunciator.py` | Speaker (PWM on GP18) and button (GP20): the alarm sounds, played in the background, and press / hold detection |
| `lib/co2events.py` | Event detection and timing (room level, peak, 10-90 % rise, 90-10 % fall) |
| `lib/mhz19c.py` | Driver for the Winsen MH-Z19C CO2 sensor; works with the two data wires either way round |

Laptop tests for the firmware (88, with `tests/test_cr4.py`, `tests/test_lineclip.py` and
`tests/test_rate_run.py` added on 1 Nov; earlier note: 49 of the 68 in `python -m pytest tests/`): `tests/test_cr1.py` and
`tests/test_alarm.py` replay the real 22 Oct readings (present by breath 3, absent and CRITICAL 17 s
after the last breath of the rhythmic run; both sensor faults TECHNICAL, never CRITICAL), and
`tests/test_co2events.py` dry-runs `code.py` with a simulated sensor, light ring, speaker, button
and USB link (the JSON line for every reading; `ACK` from the dashboard acknowledges like the button).

## What the board shows

| Alarm state | When | Light ring | Sound |
| --- | --- | --- | --- |
| STANDBY | Warming up, or no breath seen yet: not monitoring | One white light circling | None |
| NORMAL | Exhaled CO2 present | Green, steady | None |
| ADVISORY | A sustained fall of the breathing rate or of the CO2 (CR-4), for 30 s; back to NORMAL after 30 s in range | Amber, slow flash | 3 pulses, every 20 s |
| CRITICAL | CO2 lost after it was present. Latched: ends once it is acknowledged and CO2 is back, in either order | Red, fast flash (steady once acknowledged). While CO2 is back but nobody has pressed yet: red and green in turn, 1 s each | 10 pulses (3+2+3+2), every 10 s |
| TECHNICAL | Any sensor problem, and the 3-minute re-warm after it; the sampling line off (safety clip open); a reading stuck at the top of the scale for 30 s | Cyan, steady | Chirp, every 30 s |

At power-up: green, amber, red, cyan for 0.4 s each (lamp test), then a rising two-tone chirp
(speaker test). The sounds follow the pattern of medical alarms (IEC 60601-1-8): 10 pulses for high
priority, 3 for medium, and the light flashes faster the higher the priority.

**Button:** a short press acknowledges a critical alarm: sound off for 2 minutes, light steady red.
If CO2 is back, the press clears the alarm to NORMAL; if not, the alarm sounds again after the
2 minutes, and it clears by itself to NORMAL as soon as CO2 is back (acknowledged and back in range).
An advisory is acknowledged the same way (sound off 2 minutes, light still amber). Holding the button for 3 s stops monitoring (falling two-tone, back to STANDBY); it starts
again at the next breath. The dashboard's **Acknowledge** does exactly what a short press does;
stopping monitoring is only possible at the box.

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

- **Dashboard on the Mac:** `bash tools/dashboard.sh` in Terminal, from the repository folder. The
  board's state live in the browser, with sound, acknowledge, the trend and the alarm log; every
  line is also saved to `data/raw/`. See [dashboard/README.md](../dashboard/README.md).
- **Live view in Terminal:** `bash tools/live_co2.sh`. One line per second, also saved to
  `data/raw/` (with the JSON lines, which it does not show). Stop with Ctrl-C. Only one program can
  hold the serial port: close the dashboard, Thonny or Mu first. Each line reads, for example,
  `t= 312 s  CO2  1814 ppm  |##########....|  PRESENT    NORMAL`: the CR-1 state, then the alarm.
- **Verification runs:** `bash tools/scripted_run.sh`; see `tools/README.md`.
- **`boot_out.txt`:** after a replug, its last line reads `CO2 OK: <ppm> ppm, wires <normal|swapped>`
  or `CO2: NO REPLY either way`. The ppm there is a warm-up placeholder (the sensor needs about
  75 s); it only proves the connection.
- **Before any test:** wait for the ring to circle white (STANDBY) and the line to show ABSENT,
  and keep people at least 1 m from the sensor (their breathing shows up).

## Next

- Air through the cell (pump or flushes) and a diluted sample: without them breath does not reliably
  reach the sensor, the rate cannot be read, and a cell full of old breath reads 5,000 ppm (1 Nov).
- A blocked line (CR-3): needs the airflow above, or a water-trap probe.
- Read the alarm thresholds from `config.json`, the file the service uses too.
- Possibly: a slow "breathing" cyan for TECHNICAL, the signature on workshop slide 11 (steady now).
