# Archive

Earlier programs, kept for reference. None of them belongs on the board now; the current firmware
is in [`firmware/`](../firmware/).

| Folder | What it was |
| --- | --- |
| `team-skeleton-firmware/` | The team's first firmware outline (21 Oct): one JSON line per sample and the four alarm states, with the sensor parts still to fill in. The plan to print JSON lines for the laptop service comes from here |
| `team-skeleton-service/` | The team's first laptop service and dashboard page, from the team's first commit: a FastAPI app, a serial logger into SQLite (WAL) and a four-state rules engine on percent thresholds, with an alarm-banner page. Replaced on 26 Oct by [`service/`](../service/) and [`dashboard/`](../dashboard/); the REST contract (`/api/latest`, `/api/ack`), the SQLite file in WAL mode and the table plan come from here |
| `wiring-test-2026-10-21/` | Live wiring test: the Pico's LED stays on while the CO₂ sensor answers |
| `bench-monitor-v0.2/` | Firmware v0.2 (22 Oct): one reading per second, breath-event timing, stuck-at-400 fault |
| `pico-lab-ring-demo/` | First-week demo: the Pico makes its own Wi-Fi network and a web page drives the light ring. Its demo Wi-Fi password is written in the code; that network only exists while this demo runs on the board |
