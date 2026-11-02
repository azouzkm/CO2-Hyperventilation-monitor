# Deliverables map (Project Card 06)

Where each deliverable lives in this repository. Traceability decides most of the marks:
every engineering requirement (ER) names the clinical requirement (CR) it serves, and every
verification result names the ER it closes.

| ID | Deliverable | Marks | Format | Location | Status |
| --- | --- | --- | --- | --- | --- |
| D1 | Engineering requirements | 10 | 3–4 pages | `docs/D1-engineering-requirements.md` | Draft ER-1/ER-2 from the 22 Oct bench data |
| D2 | System design | 5 | 4–6 pages | `docs/D2-system-design.md` | Not started |
| D3 | Component, module and system chart | 10 | Chart + interface table | `docs/D3-components-interfaces.md` | Not started |
| D4 | System diagram set | 5 | 4 diagrams | `docs/diagrams/` | Not started; a first measurement-chain sketch is in the README |
| D5 | Working system and documentation | 35 | Repo + live demo | `firmware/`, `service/`, `dashboard/`, `hardware/`, `tools/`, README | Firmware v0.4 on the board (CR-1 and the four alarm states; v0.5 adds the link to the laptop); service, database and dashboard built 26 Oct (live state, sound, acknowledge, link watchdog, SQLite); messages to phones through CallMeBot built 27 Oct (sign-up page, escalation, retries); live viewer, scripted-run tool; flow-cell v1 printed and assembled |
| D6 | Verification plan | 5 | Table + protocol | `docs/D6-verification-plan.md` | Draft for CR-1 (ER-1, ER-2) |
| D7 | Verification report | 10 | 6–10 pages | `docs/D7-verification-report.md`, `data/` | Not started |
| D8 | Failure modes and mitigation | 10 | Table + narrative | `docs/D8-failure-modes.md` | Candidates in lab notebook (USB link drop, calibration wire to ground, operator breath, sensor glitches); laptop service stops (box alarms on its own, dashboard shows No service, start script restarts the service); USB cable pulled also powers off the box (dashboard alarm, phone message after 1 min); messaging provider refuses or is unreachable (3 tries, failures shown on the dashboard, local alarm unaffected) |
| D9 | Design dossier | 10 | Single PDF | `docs/D9-dossier/` | Outline in `docs/D9-dossier/Design_Dossier_Skeleton.md` |

## Clinical requirements (as issued)

| ID | Requirement |
| --- | --- |
| CR-1 | Presence or absence of exhaled CO2 confirmed within a stated number of breaths and displayed unambiguously |
| CR-2 | Loss of CO2 while the circuit reads connected raises an immediate alarm |
| CR-3 | A blocked or disconnected sampling line is reported as a fault and never presents as apnoea |
| CR-4 | Breathing rate from the CO2 signal recorded through the procedure, with alarms on a sustained fall |

## Order of work

1. Setup: kit check **done**; GitHub repository **done 23 Oct**; team roles and software installs **to do**.
2. First contact with the sensor; record its specs. **Done 22 Oct** (readings, supply, first breath tests)
3. Draft D1 and the D3 module tree; bring to the one-on-one. **ER-1/ER-2 drafted**
4. Build the bench rig: printed sensor cap, sampling line, water-trap probe, break-wire loop.
   **v1 flow-cell printed, assembled and leak-tested 25 Oct** (`hardware/cad/`)
5. Characterise the sensor: step response, delay vs line length, drift. Finalise ERs.
6. Build firmware alarm rules and annunciation (**v0.4, 25 Oct**); service, database, dashboard
   (**26 Oct**), messaging.
7. Write D2 and draw D4 from what was built.
8. Write D6, run every test, write D7 (including the fault-injection dataset).
9. Update D8 with what testing found.
10. Assemble D9 and rehearse the live demo.
