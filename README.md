#  Project 6: Is the Patient Ventilating?

Exhaled CO₂ and hypoventilation monitor (bench prototype).

## In one sentence
Sample airway gas → confirm exhaled CO₂ → derive breathing rate from the signal → four-state alarm,
while **measuring and honestly reporting its own response time**, rather than pretending to be a
breath-by-breath capnograph.

## Members 
- Member 1: Abdelaziz Mourad
- Member 2: Nyah Woller-li
- Member 3: Szirina Ismail
- Member 4: Alice She
- Member 5: Michele Frederike 
- Member 6: Yuhan Zhang

## Directory structure
```
Group_6_Project_6_CO2Monitor/
├── Design_Dossier/          ← skeleton of the final PDF design dossier (fill in the content)
├── Source_Code/
│   ├── firmware/            ← CircuitPython running on the Pico 2 W
│   ├── service/             ← Python on the laptop (FastAPI + rules engine + ingest)
│   ├── dashboard/           ← web dashboard
│   ├── calibration.py       ← calibration fit + response-time measurement
│   ├── config.json          ← threshold config shared by firmware and service (important! see below)
│   └── requirements.txt     ← Python dependencies
└── Evidence/                ← calibration data / test results / system photos and video
```

## Key design stance (the most important idea behind the whole dossier)
Honest response-time declaration:
1. Measure the 10–90% response time;
2. Measure how the response time degrades with **sampling-line length**;
3. State plainly whether this hardware supports a "breath-by-breath waveform" or only a "breath-averaged trend".
   — Claiming the former while delivering the latter is the most dangerous outcome here (project card, verbatim).

## Alarm state machine (project card Figure 3)
| State | Light | Sound | Trigger |
|-------|-------|-------|---------|
| normal | green | silent | concentration / rate in range |
| advisory | amber | 3-pulse | concentration or breathing rate falls past threshold; clears after 30 s back in range |
| critical | red | 10-pulse, latched | CO₂ absent while the circuit reads connected |
| technical | cyan | short chirp | blocked / disconnected line, sensor fault, zero drift |

**Golden rule (CR-3)**: a blocked line / fault must be `technical`, never presented as apnoea (`critical`).

## How to run
1. **Firmware** (Pico): run `Source_Code/firmware/code.py` under CircuitPython.
2. **Service** (laptop):
   ```
   cd Source_Code
   pip install -r requirements.txt
   uvicorn service.main:app --reload
   ```
3. **Dashboard**: open `http://localhost:8000` in a browser.
