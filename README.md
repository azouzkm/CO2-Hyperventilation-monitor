# Project 6: Is the Patient Ventilating?

**Exhaled CO₂ and hypoventilation monitor (bench prototype)**  
EXSU 620 Surgical Innovation · Digital Prototyping · McGill University · Fall 2026

[![tests](https://github.com/azouzkm/CO2-Hypoventilation-Monitor/actions/workflows/tests.yml/badge.svg)](https://github.com/azouzkm/CO2-Hypoventilation-Monitor/actions/workflows/tests.yml)

Sample airway gas → confirm exhaled CO₂ → derive breathing rate from the signal → four-state alarm,
while **measuring and honestly reporting its own response time**, rather than pretending to be a
breath-by-breath capnograph.

> [!IMPORTANT]
> **What the bench shows so far:** this sensor supports a **breath-averaged trend, not
> breath-by-breath capnography**. On 22 Oct 2026 it took 11–13 s to rise and about a minute to fall
> after a breath, and breathing at 15 breaths/min left only about 2 ppm of ripple per breath on a
> 1,000 ppm rise. Everything here is designed, tested and reported on that basis.

> [!WARNING]
> **Bench only.** Nothing built here goes near a patient or clinical equipment in service. No
> patient-identifiable information goes into the database, this repository or any message. The
> simulation-lab capnograph is a calibration and validation reference only, never a live channel
> during a logging run.

## Members

- Abdelaziz Mourad
- Nyah Woller-li
- Szirina Ismail
- Alice She
- Michele Frederike
- Yuhan Zhang

## Where things stand (23 Oct 2026)

| Part | State |
| --- | --- |
| CO₂ sensor | Winsen MH-Z19C (NDIR, 400–5,000 ppm, UART) reading reliably since 22 Oct; wiring and supply checked |
| Firmware | v0.3 calls CR-1 (CO₂ PRESENT or ABSENT, plus WARMING UP and FAULT) and shows it on the Pico's LED. Tested on the laptop against the 22 Oct readings; loading it onto the board is next |
| Light ring, speaker, button | Soldering under way; the light ring is already supported in the code |
| Bench tools | Live view, and scripted CR-1 runs with spoken cues, scored against ER-1 and ER-2 |
| Printed parts | v1 sensor flow-cell and tubing-fit coupon ready to print (STL and STEP) |
| Service, database, dashboard, messaging | Skeletons in place, not yet connected to the board |
| Tests | 25 automated tests, run by GitHub on every pull request |

## Requirements and deliverables

Traceability decides most of the marks: every engineering requirement (ER) names the clinical
requirement (CR) it serves, and every verification result names the ER it closes.

| CR | Clinical requirement (project card) | Progress |
| --- | --- | --- |
| CR&#8209;1 | Presence or absence of exhaled CO₂ confirmed within a stated number of breaths and displayed unambiguously | ER-1 (present within 3 breaths) and ER-2 (absent within 30 s) drafted and built into firmware v0.3; the counted verification runs need the printed flow-cell |
| CR&#8209;2 | Loss of CO₂ while the circuit reads connected raises an immediate alarm | ERs to draft |
| CR&#8209;3 | A blocked or disconnected sampling line is reported as a fault and never presents as apnoea | ERs to draft |
| CR&#8209;4 | Breathing rate from the CO₂ signal recorded through the procedure, with alarms on a sustained fall | ERs to draft |

| | Deliverable | Marks | Where it lives |
| --- | --- | --- | --- |
| D1 | Engineering requirements | 10 | [docs/D1-engineering-requirements.md](docs/D1-engineering-requirements.md) (draft) |
| D2 | System design | 5 | `docs/D2-system-design.md` (to write) |
| D3 | Component, module and system chart | 10 | `docs/D3-components-interfaces.md` (to write) |
| D4 | System diagram set | 5 | `docs/diagrams/` (to draw) |
| D5 | Working system and documentation | 35 | [firmware/](firmware/), [service/](service/), [dashboard/](dashboard/), [hardware/](hardware/), [tools/](tools/) and this README |
| D6 | Verification plan | 5 | [docs/D6-verification-plan.md](docs/D6-verification-plan.md) (draft, CR-1 first) |
| D7 | Verification report | 10 | `docs/D7-verification-report.md` (to write), with the evidence in [data/](data/) |
| D8 | Failure modes and mitigation | 10 | `docs/D8-failure-modes.md` (to write); candidates in the [lab notebook](docs/lab-notebook.md) |
| D9 | Design dossier (one PDF) | 10 | [docs/D9-dossier/](docs/D9-dossier/) (outline) |

Progress and the order of work: [docs/deliverables.md](docs/deliverables.md).

## Response time, measured

The project card asks the device to measure and publish its own response time. First numbers, in
open air about 15 cm from the sensor, before the flow-cell and sampling line exist:

| Test (22 Oct 2026) | Rise 10–90 % | Fall 90–10 % | Back near room air |
| --- | --- | --- | --- |
| Single breath 1 | 12.7 s | 51 s | 81 s |
| Single breath 2 | 10.6 s | 66 s | 93 s |
| 15 breaths/min for 1 min | 31 s (whole run) | 71 s | 89 s after the last breath |

![Rhythmic breathing run: one smooth rise of about 1,000 ppm and no breath-by-breath waveform](docs/figures/2026-10-22_rhythmic-run-1.png)

Next: repeat the runs through the printed flow-cell and sampling line, and measure how the delay
grows with line length (0.5, 1 and 2 m). Data in [data/](data/); method and notes in the
[lab notebook](docs/lab-notebook.md).

## How it works

```mermaid
flowchart TB
    subgraph rig["Bench gas path"]
        direction LR
        lung["Test lung<br/>or mask"] --> line["Sampling line<br/>and water trap"]
        line --> cell["Printed<br/>flow-cell"]
        cell --> sensor["MH-Z19C<br/>NDIR CO₂ sensor"]
        ref["Sim-lab capnograph<br/>(reference)"] -.->|calibration only| line
    end
    rig -->|"UART, 1 reading/s"| pico["Pico 2 W<br/>light, speaker, button"]
    pico -->|USB serial| laptop
    subgraph laptop["Laptop"]
        direction LR
        svc["Service<br/>SQLite database"] -->|HTTP| dash["Browser dashboard<br/>audible alert"]
        svc -->|HTTP alert| phone["Registered phone"]
    end
    classDef planned stroke-dasharray: 5 4
    class lung,line,cell,svc,dash,phone,ref planned
```

Solid boxes work on the bench today; dashed boxes are designed, on order or exist as skeletons.
By design the board raises its alarms by itself, so a crashed laptop can never silence it; the
laptop adds the database, the dashboard and the messages.

### Alarm behaviour

The four states required by the project card (Figure 3):

| State | Light | Sound | Trigger |
| --- | --- | --- | --- |
| Normal | Green | Silent | Concentration and breathing rate in range |
| Advisory | Amber | 3 pulses | Concentration or breathing rate falls past its threshold; clears after 30 s back in range |
| Critical | Red | 10 pulses, latched | CO₂ absent while the circuit reads connected |
| Technical | Cyan | Chirp | Blocked or disconnected sampling line, sensor fault, or zero drift |

**Golden rule (CR-3):** a blocked line or a fault is *Technical*, never presented as apnoea
(*Critical*).

Today the board shows the CR-1 states (WARMING UP, ABSENT, PRESENT, FAULT) on the Pico's LED; see
[firmware/README.md](firmware/README.md). The thresholds for the board and the service are meant to
live in one file, [config.json](config.json), so the two can never disagree about what counts as an
alarm. Its values are placeholders until calibration, and the CR-1 numbers still sit in
[firmware/lib/cr1.py](firmware/lib/cr1.py).

## What's in this repository

```text
firmware/          Pico 2 W code: everything inside goes onto the CIRCUITPY drive
  code.py            main program, monitor v0.3 (CR-1: CO2 present or absent)
  boot.py            power-up sensor check, result written to boot_out.txt
  lib/               sensor driver, CR-1 logic, event timing, LED and light-ring display
service/           laptop service: serial ingest to SQLite, rules engine, REST API (skeleton)
dashboard/         browser dashboard: alarm banner, latest reading (skeleton)
tools/             live view, scripted CR-1 runs and their scoring, calibration fit
tests/             pytest tests; several replay the real 22 Oct readings
hardware/          wiring and bill of materials
  cad/               printed flow-cell and tubing coupon: STL, STEP, print sheets, generator scripts
data/              evidence for D7: labelled readings, raw logs, run results, calibration
docs/              D1–D9 write-ups, lab notebook, sensor notes, figures, photos
  D9-dossier/        outline of the final PDF
archive/           earlier programs, kept for reference
config.json        alarm thresholds shared by the firmware and the service
requirements.txt   Python packages for the laptop side
```

## Getting started

You need the kit (Pico 2 W on the Grove shield, MH-Z19C sensor), the 2 m data-capable USB cable,
and a laptop with Python 3.11 or newer. Commands run in Terminal from this folder.

1. **Wire it:** [hardware/wiring.md](hardware/wiring.md). The sensor needs 5 V, and its brown
   calibration wire stays insulated and away from metal.
2. **Load the firmware:** with CircuitPython 9.2.9 on the Pico 2 W, copy the `lib/` folder from
   [firmware/](firmware/) onto the `CIRCUITPY` drive first, then `boot.py` and `code.py`. Eject the
   drive before unplugging. Details: [firmware/README.md](firmware/README.md).
3. **Watch the readings (macOS):**

   ```bash
   bash tools/live_co2.sh
   ```

   One line per second, also saved in `data/raw/`. The sensor needs about 75 s to warm up.
4. **Run a scripted CR-1 run:** `bash tools/scripted_run.sh --label test01` gives spoken cues and
   scores the run against ER-1 and ER-2. See [tools/README.md](tools/README.md).
5. **Run the tests:**

   ```bash
   python3 -m pip install -r requirements.txt
   python3 -m pytest tests/
   ```

6. **Start the service (skeleton):**

   ```bash
   python3 -m uvicorn service.main:app --reload
   ```

   then open <http://localhost:8000/docs> to see and try its REST endpoints.

## If something goes wrong

The messages a new user is most likely to see:

| You see | What it means | What to do |
| --- | --- | --- |
| `No Pico found. Is the USB cable plugged in?` | The laptop can't see the board's serial port | Replug the USB cable firmly, using the data-capable cable from the kit. The link has dropped mid-session before (Finder says "Disk Not Ejected Properly"); replugging fixes it |
| `Could not open /dev/cu.usbmodem… Is another program (Thonny, Mu, screen) using it?` | Another program holds the serial port | Close Thonny, Mu, `screen` or the other live view; only one program can read the board at a time |
| `>>> SENSOR FAULT: reading stuck at 400 ppm: check the brown calibration wire <<<` | The sensor's brown calibration (HD) wire touched ground, which re-zeroes it | Insulate the brown wire's tip and keep it off metal, including the laptop's case. Treat the first 3 minutes of readings after a fault as untrustworthy |
| `CO2: NO REPLY either way` in `boot_out.txt` | The sensor didn't answer at power-up | Check red to 5V and black to GND first (no power, no reply), then the blue and green data wires; reseat the leads |

## Working together

Changes go in through a branch and a pull request, never straight onto `main`. How to do that from
the browser or a laptop, and where each kind of file goes, is in [CONTRIBUTING.md](CONTRIBUTING.md).
GitHub runs the tests on every pull request and on `main`; the badge at the top shows the latest
result.
