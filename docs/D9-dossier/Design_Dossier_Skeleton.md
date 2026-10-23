# Design Dossier — Skeleton Template

> This is the table of contents and table templates for the final PDF design dossier.
> Fill it in using Google Docs/Word, then export to PDF. The grey `<!-- -->` hints
> are for your team — delete them before exporting.
> Reference: the worked example report (the 13-page bed-wetness PDF) + the project
> card deliverables D1–D9.

---

## Cover page
- Project number + title: **Project 06 — Is the patient ventilating**
- Full names of all group members
- Device identifier (your own choice, e.g. CO2M-1 bench prototype rev A)

---

## Section 1 — Clinical requirements (copy CR-1–CR-4 from the project card)

| ID | Requirement |
|----|-------------|
| CR-1 | Confirm the presence/absence of exhaled CO₂ within a stated number of breaths, displayed unambiguously |
| CR-2 | Loss of CO₂ while the circuit reports connected → immediate alarm (signature of a misplaced tube / disconnection) |
| CR-3 | A blocked/disconnected sampling line is reported as a fault, and never presents as apnoea |
| CR-4 | Breathing rate derived from the CO₂ signal is recorded throughout; a sustained fall alarms |

---

## Section 2 — Engineering requirements (D1, 3–4 pages)

> Up to 8 requirements. Each must have: a number (range/rate/latency/accuracy) + an
> acceptance criterion that can fail + the CR it serves.
> Example format (copy this structure):

| ER | Serves | Requirement (with numbers) | Acceptance criterion |
|----|--------|----------------------------|----------------------|
| ER-1 | CR-1 | Confirm CO₂ present/absent within N breaths | Pass: … |
| ER-2 | CR-1 | … | Pass: … |
| ER-3 | CR-2 | When the circuit is connected and CO₂ disappears, raise critical within T s | Pass: 10/10 scripted runs |
| ER-4 | CR-3 | A blocked/disconnected line raises technical within T s and never raises apnoea | Pass: 10/10 fault injections |
| ER-5 | CR-3 | … | Pass: … |
| ER-6 | CR-4 | Breathing-rate accuracy ±X bpm, sample rate X Hz | Pass: … |
| ER-7 | CR-4 | Alarm on a sustained fall in breathing rate | Pass: … |
| ER-8 | CR-1 | **10–90% response time ≤ X s** (the core of this project) | Pass: measured value |

<!-- Hint: ER-8, "measure your own response time", is a scoring point for this project and must be its own requirement -->
<!-- Hint: like the worked example's ER-7, turn a problem you found during prototyping (e.g. drift / delay) into a requirement that bounds it -->

---

## Section 3 — System design (D2, 4–6 pages)
- Sensing approach (NDIR principle + sampling line + water trap)
- Alarm rules (four states; point to rules_engine.py)
- Data model (table structure; point to logger.py)
- **Rejected-alternatives table** (required):

| Option considered | Decision | Reason |
|-------------------|----------|--------|
| … | Rejected | … |
| … | Selected | … |

<!-- Hint: at least one row must say "our own first choice was rejected by measured data" (the worked example earns marks on this) -->

---

## Section 4 — Component–module–system hierarchy (D3)
Group components into modules: M1 sensing / M2 firmware / M3 service / M4 interface.
Each component has one owner and one entry in the interface table.

---

## Section 5 — Interface table (each interface: id / from→to / signal / direction / range)

| IF | From → To | Signal and protocol | Type |
|----|-----------|---------------------|------|
| IF-1 | NDIR sensor → Pico | UART/I2C, CO₂ concentration | Digital |
| IF-2 | Pico → indicator ring | Single-wire addressable | Digital |
| IF-3 | Pico → service | USB CDC serial, 115200, one JSON line per sample | Serial |
| IF-4 | Service → database | SQLite file | File |
| IF-5 | Service → dashboard | HTTP localhost JSON | Network |
| IF-6 | Service → phone | HTTPS POST | Network |

---

## Section 6 — Four diagrams (D4)
1. Block diagram (matching the interface-table IDs)
2. Wiring diagram (Fritzing/KiCad)
3. **Alarm state chart** (four states + transition conditions; copy project card Figure 3)
4. Sample → notification sequence diagram

---

## Section 7 — Implementation (D5, the 35-mark big item)
- Key code excerpts (firmware / rules_engine / service)
- Database table structure
- Printed-part notes (Onshape/Tinkercad)
- **Deployment notes**: what the README says (including the 3 errors a new user is most likely to hit)

---

## Section 8 — Verification plan (D6, table)

| Requirement | Method | Apparatus | Sample size | Criterion | Sign-off |
|-------------|--------|-----------|-------------|-----------|----------|
| ER-1 | … | … | … | … | … |

---

## Section 9 — Verification report (D7, 6–10 pages)
- 9.1 Calibration curve + residuals (generate the plot with calibration.py)
- 9.2 Drift
- 9.3 **Response time vs. sampling-line length** (the core evidence of this project)
- 9.4 Alarm latency, sensitivity/specificity
- 9.5 Pass/fail per requirement:

| ER | Result | Verdict |
|----|--------|---------|
| ER-1 | … | PASS/FAIL |

<!-- Hint: report failures honestly — do not quietly reword a requirement to fit what the device did (the worked example's Marker's note stresses this) -->

---

## Section 10 — Failure modes and mitigation (D8, FMEA table)

| ID | Failure mode | Effect | S | O | D | RPN | Mitigation | Status |
|----|--------------|--------|---|---|---|-----|------------|--------|
| FM-1 | Kinked sampling line | Trace looks steady, no alarm | 4 | 3 | 2 | 24 | Flat signal → technical | Verified |
| FM-2 | Laptop service dies | Alarms go silent | 5 | 2 | 3 | 30 | Board alarms locally | Verified |
| … | … | … | | | | | … | … |

<!-- Hint: RPN > 25 must have a mitigation that was implemented and verified -->

---

## Section 11 — Traceability matrix + limitations + technical memorandum (D9)
**Traceability matrix (decides most of the marks):**

| Clinical requirement | Engineering requirements | Evidence | Status |
|----------------------|--------------------------|----------|--------|
| CR-1 | ER-1, ER-2, ER-8 | Section 9 | Met / Not met |
| CR-2 | ER-3 | Section 9 | … |
| CR-3 | ER-4, ER-5 | Section 9 | … |
| CR-4 | ER-6, ER-7 | Section 9 | … |

**Declared limitations** (required — do not hide them):
- e.g. the response time only supports a breath-averaged trend, not a breath-by-breath waveform.
- e.g. tested only on a bench rig, never on a person / not for clinical use.

**Technical memorandum** (a plain-language paragraph for a non-specialist, written last, ~150 words summarising what the device is, what it can do, and what it cannot do).
