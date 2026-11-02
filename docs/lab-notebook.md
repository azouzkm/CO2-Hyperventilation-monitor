# Lab notebook

Dated record of what we did and found. Findings here feed the design rationale (D2) and
the failure-mode table (D8). Newest entries at the top.

## 2026-11-01 · Session 4: everything in the printed case, safety clip (CR-3), firmware v0.6

Log: `data/raw/co2_2026-11-01_185318.log`.

- **Build:** all parts now in the printed Option A case; the sampling line pushes onto the SAMPLE
  barb from outside.
- **Safety clip (break-wire loop), CR-3:** first tried inside the case: when the tube came off,
  nothing inside moved and the pins stayed in. Rebuilt outside: two male-to-female jumpers (orange
  to **GP21**, grey-black to **GND**) come out through a small hole beside SAMPLE; a purple
  male-to-male jumper taped along the tube plugs into both sockets. Meter: tube on = beep. Design
  lesson for D2: the pins only come out if they are pulled along their length, the way the tube
  comes off. Pictures: `hardware/cr3_safety_clip_plug_and_socket.png`, `hardware/cr3_step1_safety_clip.png`.
- **Firmware v0.6 loaded (19:11:27):** v0.5 (dashboard link) + CR-4 (breathing rate, advisory) +
  the safety clip (`lib/lineclip.py`) + the CR-1 "no new rise" rule. One rate estimate takes
  **83 ms** on the Pico.
- **Clip test (19:19, monitoring stopped with a 3 s hold):** tube off at 19:19:17 → `SAMPLING LINE
  OFF`, TECHNICAL "LINE OFF" (cyan); tube on at 19:19:36 → connected, back to STANDBY. Repeated at
  19:19:41 / 19:19:45. **Works.**
- **Clip test while monitoring (green):** tube off at 19:23:27 for 16 s, and at 19:25:37 for 2 min 25 s:
  TECHNICAL "LINE OFF" (cyan) within a second each time, back to NORMAL when reconnected, never
  CRITICAL. But the CO2 never fell while the line was off: the sealed cell kept the last breath (pinned
  at 5,000 ppm the whole 2.5 min). So "line off while the CO2 falls" (the case CR-3 is about) is shown
  by the laptop tests (`tests/test_lineclip.py`) but not yet at the bench; it needs air moving through
  the cell (pump, or a room-air bag squeezed through SAMPLE while the tube is off).
- **Finding: breathing into the mask does not reliably reach the sensor.** From 19:16:52 the reading
  fell steadily (about 30 ppm/s, 3,141 → 1,584 ppm in a minute) while Abdelaziz said he was still
  breathing, and the monitor rightly called CO2 lost (CRITICAL). With no pump nothing draws gas
  down the 2 m line: breath arrives only when pushed, and breathing in may draw room air back in
  through VENT. Evidence for the pump request; until then the CO2-alarm tests use deliberate puffs
  into the line.
- **Saturated cell read green for 6 minutes (19:25:32-19:31:21):** firm breaths pinned the reading
  at 5,000 ppm; with the tube on the table nothing flushed the cell, so CR-1 kept PRESENT and the ring
  stayed green. The gas finally leaked out through VENT and the alarm went CRITICAL at 19:31:31,
  about 3.5 min after breathing stopped: **ER-2 (absent within 30 s) failed, cause: sealed cell
  without airflow plus the sensor's 5,000 ppm ceiling.** Mitigation implemented (v0.6, 19:42): 30 s at
  the top of the scale is TECHNICAL ("the sensor cannot see breaths; flush or dilute the sample"),
  and a fall from there is CRITICAL at once. Test: `test_code_py_a_cell_stuck_at_the_top_is_cyan_not_green`.
- **Alarm clearing changed to match the card (19:42):** Abdelaziz noticed that after acknowledging and
  breathing again the ring flashed red and green and needed a second press. The card's Figure 3 says
  Critical returns to Normal when "acknowledged and back in range", so an acknowledged alarm now
  clears by itself when CO2 is back; red and green in turn remain for an alarm nobody has acknowledged.
- **Phone alerts:** CallMeBot's WhatsApp bot is full, so Telegram (@CallMeBot_txtbot). Abdelaziz
  signed up at 19:03 and received the alarm messages within about 0.5 s of each alarm (18 sent). Two
  teammates signed up at 19:32; their test messages were accepted by CallMeBot but not received:
  each person must press Start on the bot themselves, and the usernames must match exactly. A
  person who signs up during an alarm is told from the next alarm on.
- **The box's own speaker** plays every alarm independently of the dashboard (a muted or closed
  dashboard does not silence it); it is still on its resistor (quiet) until the amplifier is soldered.
- **USB "disk not ejected properly"** appeared at random (third episode; also 22 and 25 Oct): the
  data link drops while the board keeps power. For D8; plug straight into the Mac, no strain on the
  cable at the case.

## 2026-10-26/27 · CR-3 plan, CR-4 written (laptop only, no bench readings)

No new bench readings: the case parts were being fitted. Work on the laptop, tested on the
22 and 25 Oct recordings and on simulated breathing.

- **CR-3, the safety clip (break-wire loop), planned:** two sockets taped on the flow-cell lid
  next to the IN barb, a male-to-male jumper bent into a U plugged into them and taped to the tube
  about 2 cm above the barb, wired to **GP21** and **GND** (the two holes above the button). Tube
  pulled off = loop open = TECHNICAL "LINE OFF", never CRITICAL. Picture:
  `hardware/cr3_step1_safety_clip.png`. Not built yet; the code follows once it is.
- **CR-3, blocked line:** without air moving through the cell, a pinched tube and a patient who
  stopped breathing look the same on the CO2 reading. With a pump, a block freezes the reading
  while no breathing lets it fall. A water-trap probe would catch the commonest block (water).
- **CR-4, breathing rate (`firmware/lib/cr4.py`):** the sensor is too slow to draw each breath,
  but breaths leave a regular wobble on the slope of the reading. Every 2 s, over the last 64 s,
  the rhythm is found in the slope's spectrum and believed only if it swings back and forth like
  breathing (half a period out of step with itself, in step one and two periods later), stands
  15 times above the rest of the spectrum and is bigger than 2.5 times the room-air noise.
  Otherwise "RR --", with the reason. Replayed: the 22 Oct paced run reads 15.0–15.7/min from 31 s
  into the run; nothing else in the 2.8 h of 22 and 25 Oct readings shows a rate.
- **CR-4, advisory:** breathing below 8/min or 40 % below its own baseline, or the breath-averaged
  CO2 30 % below its baseline, for 30 s: ADVISORY (amber, 3 pulses). Back to NORMAL after 30 s in
  range; a press silences it for 2 minutes; CO2 lost during it is still CRITICAL. Simulated
  15 → 6/min: rate below 8 shown after 30–48 s, advisory after 60–78 s; no false advisory in 135
  ten-minute runs of steady breathing.
- **Found and fixed in CR-1:** once air moves through the cell, each breath swings the reading up
  and down. Simulated with swings of ±50 ppm or more (6–10 breaths/min), CR-1 read the down-swing
  between two breaths as "CO2 lost" and the alarm went CRITICAL at every breath. ABSENT is now
  called only after 12 s with no new rise of 25 ppm. On every bench reading so far this changes
  nothing (one ABSENT on 25 Oct 1 s later; ER-1 and ER-2 replays unchanged).
- **Measured on the board at its first estimate:** how long one rate estimate takes (banner
  `--- CR-4: one breathing-rate estimate took N ms ---`). The light, sound and button keep
  running during it.
- **Tools:** `tools/rate_run.sh` (paced phases with spoken cues, e.g. 15 → 6 → 15/min) and
  `tools/score_rate_run.py` (ER-7 and ER-8 per phase, to `data/runs/rate_results.csv`). Checked
  against a simulated board on a pseudo-terminal; first real try on the Mac to come.
- **For the pump question:** the rate also needs the sample diluted below 5,000 ppm. Undiluted
  breath pins the sensor at the top of its scale, where the wobble is cut off.

## 2026-10-26/27 · Dashboard and phone alerts (laptop side, no bench work)

- **Design decision: the course's three tiers, one alarm path** (workshop slides 10 and 13). The
  board keeps deciding every alarm and keeps its own light ring and speaker; the laptop adds a
  browser dashboard with sound, the database and messages to phones. Abdelaziz first proposed
  moving everything except the light into the interface; the box keeps its speaker (decided 27 Oct)
  because the course expects a tone at the device and the box must keep sounding if the laptop dies
  (worked example, FM-5). It stays on its resistor (quiet) until the amplifier is soldered.
- **Firmware v0.5** (only `code.py` changed): one JSON line per reading for the laptop (IF-6) next
  to the text line, and the dashboard's acknowledge arrives over USB as `ACK`, handled like a
  short press of the button. Stopping monitoring stays at the box only. **Not on the board yet.**
- **Service and dashboard** (`bash tools/dashboard.sh`): the box's state live in the browser with
  the same ring patterns and IEC-style sounds, acknowledge with initials (confirmed by the board),
  a Technical alarm when no data arrives for 5 s, the 10-minute trend, the alarm log, SQLite.
  Replaces the team's FastAPI skeleton (kept in `archive/team-skeleton-service/`). Replayed on the
  real 25 Oct alarm test: critical at 01:46:46, bedside acknowledgement at 01:47:35, the pulled
  wire as Technical at 01:58:22, and link alarms only during the two firmware reloads (01:39:39,
  01:55:45). That evidence set `technical_timeout_s` to 5 s (it was a 10 s placeholder).
- **Phone alerts** (27 Oct): sign-up page with consent time, messages through CallMeBot by WhatsApp,
  Signal or Telegram, timed as on workshop slide 11 (Critical at once and again at 2 minutes if
  nobody acknowledges, then to the backups too; Advisory and Technical after a minute; one
  follow-up when an alarm ends). Up to 3 tries, failures shown on the dashboard, at most 10
  messages per person in 10 minutes. Provider chosen by Abdelaziz from the card's list. CallMeBot's
  WhatsApp page said *"The bot is currently full"* when checked on 27 Oct, so Signal and Telegram
  work too. Not yet tried with a real phone.
- **Finding for D8: the USB cable also powers the box.** Pulling it turns the box dark and silent,
  so the dashboard's *No data* alarm (and the phone message a minute later) is then the only alarm.
  The box only keeps alarming without the laptop while it has power. A power source of its own
  would close the gap.
- **Laptop tests: 91** (49 firmware, 19 service, 23 phone alerts), also run on Python 3.11, and on
  3.9 apart from 4 tests that need Flask's test client or pyserial (the dashboard needs 3.9 or newer).
- **Next, at the bench:** load v0.5 onto the board, start the dashboard, breathe, flush,
  acknowledge from the screen, stop the service mid-run (FM-5), and send a first real test message.

## 2026-10-25, afternoon · Amplifier tried without solder

Log: `data/raw/co2_2026-10-25_135228.log` (13:52 onwards, firmware v0.4).

- **Set-up:** the PAM8302A sat on its header strip in the breadboard, pins not soldered (rows 24-28:
  A+, A−, SD, Vin, Gnd); jumpers A+ → GP18, A− and Gnd → ground, Vin → 5 V; speaker wires
  twisted through the amplifier's + and − holes; resistor removed. **No sound.**
- **Diagnosis, step by step:** the board ran normally and sent every sound (button presses and alarm
  bursts in the log). With the meter: speaker across the amplifier's outputs **about 4 Ω** (speaker
  and its wires fine; a 4 Ω speaker); **5 V** on the amplifier's Vin ring (power fine); A+ and Gnd
  rings to their rows **about 0 Ω**; **A− ring to ground: open**. The A− pin did not touch its plated
  hole, and leaning the board did not fix it. Unsoldered header pins sit loose in holes made for
  solder (about 1 mm holes for 0.6 mm pins), so each one touches only by chance.
- **Decision:** solder on Monday 26 Oct: the 5 header pins, and the screw terminal that came with
  the amplifier in place of soldering the speaker wires (the speaker then clamps in and can be
  swapped). Until then the speaker goes back on the resistor.
- **Sensor lost power twice (14:14:45 and 14:15:11)** while jumpers were moved on the shared + and −
  columns: it came back reading 500 ppm (its start-up value) and real readings returned at 14:16:12.
  The board reported SENSOR FAULT, kept the alarm that was already on, and re-warmed for 3 minutes,
  as designed. For D8: power leads shared on breadboard rails are disturbed by any rewiring.
- **Firmware wording fixed (laptop, 47 tests):** at 14:04:51 the board said "still no CO2" although
  CO2 had come back (the alarm was rightly still latched). Now, while CO2 is back and nobody has
  pressed the button, the ring shows red and green in turn and the message says the alarm is
  waiting for the button. Also no more "room level: 5000 ppm" when the cell is pinned at the top.

## 2026-10-24/25 · Session 3: printed flow-cell, light ring, speaker and button, test alarm

Evening of 24 Oct, 23:28, to 02:03 on 25 Oct (Mac clock). Photos: `docs/photos/2026-10-25_*.jpg`.
Live logs: `data/raw/co2_2026-10-25_000608.log`, `_003225.log` and `_011421.log`.

**Printed parts (v1)**

- All three printed: tray, lid and the tubing-fit coupon (photos `..._coupon`, `..._flowcell_*`).
- **Coupon:** the oxygen tubing was not a good fit on any of its five barbs. On the **lid's barbs
  (5.6 mm, the same size as the coupon's 3-dot barb) it sits firmly and correctly**, so v1 keeps
  5.6 mm. Why the same size behaves differently on the coupon is not known yet (print orientation
  or barb length are candidates).
- **Lid fit:** drops into the tray's ledge, dot end over the cable notch.
- **v2 note:** move the inlet barb about 3.5 mm along the width, so it sits squarely over the
  sensor's white filter.

**Assembly and leak test**

- Sensor in the tray, cable out through the notch, lid on. One turn of electrical tape around the
  lid seam; the notch sealed with electrical tape pressed between and around the wires (no putty).
- **Leak test passed:** blowing into IN with OUT covered pushes back with no hiss; with OUT open,
  air comes out of OUT.

**Bring-up**

- Firmware v0.3 (with the 3-minute re-warm after a fault) loaded at 00:00; every file checked
  against the original by checksum.
- `boot_out.txt` said the sensor did not answer. Cause: a breadboard wire pulled loose while the
  sensor was moved into the box. Pushed back in and the board replugged: readings normal from 00:06.
- Exploratory breaths through the tube from 00:15 (first breath out 00:15:00, four gentle flushes
  at 00:16:02). Not counted runs: no results are drawn from them except the speed limits below.

**Light ring, speaker, button**

- **Light ring** (NeoPixel Ring 16, already soldered to a Grove lead) on the shield's **D16** socket
  (GP16), shield power switch on 5 V. Worked first time. Wiring: `hardware/wiring.md`.
- **Speaker and button, no soldering** (no iron tonight): both on the breadboard. Button between
  GP20 and ground; speaker driven from GP18 through a 220-470 Ω resistor, so it is quiet. Start-up
  chirp heard; button presses logged at 01:20:20 and 01:20:37. Diagram:
  `hardware/button_speaker_wiring_no_solder.png`.
- **The PAM8302A amplifier needs soldering** (bare holes only). Instructions with pictures for
  Monday 26 Oct: `hardware/soldering-speaker-button.pdf`.

**Finding: the sealed flow-cell holds its gas (for D2 and D8)**

- With nobody breathing into it, the board called **CO2 PRESENT at 00:38:35**: the reading had
  crept from about 1,280 to 1,990 ppm over 5 minutes. Breath from earlier stayed trapped, and the
  operator's breath could drift in through the open OUT barb. With no flow through the cell, the
  reading falls only slowly, so it never switched back to ABSENT on its own.
- Same effect at 02:01:53: when the sensor was trusted again after a fault, the cell still held
  about 5,000 ppm, so the board read PRESENT without a new breath.
- **Open decision:** keep air moving through the cell, with a small pump (needs the professor's
  OK; no 5 V mini pump in the kit) or by flushing room air through it after each test. Until then,
  the counted CR-1 runs (D6) wait, since a test of "absent" needs the cell to empty.

**Real CO2 speed through the cell (sets the sensor-glitch limits)**

- Fastest real rise: **654 ppm/s** (a breath straight into the cell, 00:32:58, log `_003225`);
  491 ppm/s in another breath (01:23:07). Fastest real fall: **163 ppm/s**.
- The 22 Oct glitches were 1,006 to 4,600 ppm in one second. So firmware v0.4 treats a fall of
  more than 400 ppm or a rise of more than 1,200 ppm in one second as a **sensor fault**. Before
  this rule, the first 22 Oct glitch (1,784 to 778 ppm) read as "CO2 lost", a false CRITICAL alarm.

**Firmware v0.4, the test alarm (loaded 01:39, fixed 01:55)**

The project card's alarm states on the ring and speaker: STANDBY (white, circling), NORMAL (green),
CRITICAL (red, fast flash, 10 pulses every 10 s, latched until the button), TECHNICAL (cyan, chirp
every 30 s). ADVISORY (amber, 3 pulses) is built in but waits for CR-4. Button: press = acknowledge
(sound off 2 min), hold 3 s = stop monitoring. Design rules: a sensor problem is TECHNICAL, never
CRITICAL (CR-3); a CRITICAL already on stays CRITICAL through a sensor problem; after a fault, 3
minutes of re-warm, then 30 s for a breath before CRITICAL. 44 laptop tests, 9 of them on the
real 22 Oct readings. Details: `firmware/README.md`.

| Time | Done | Board showed |
| --- | --- | --- |
| 01:46:12 | Breaths into the tube | NORMAL, green |
| 01:46:46 | Cell flushed | CRITICAL, red flashing, 10-pulse bursts |
| 01:47:16 | Breathing again | CO2 present, alarm still red (latched): as designed |
| 01:47:35 | Button pressed | Acknowledged, cleared to NORMAL |
| 01:48:26 | No breathing (operator reading) | CRITICAL |
| 01:51:19 | Green data wire pulled during the alarm | Stayed CRITICAL (as designed), but the ring froze on steady red: **bug** |
| 01:55:45 | Fix loaded | STANDBY, white circling |
| 01:57:57 | Breaths into the tube | NORMAL |
| 01:58:22 | Green data wire pulled | TECHNICAL, cyan, chirp |
| 01:58:53 | Wire pushed back | Still cyan: 3-minute re-warm |
| 02:01:53 | Re-warm over | NORMAL (the gas trapped in the cell, see above) |
| 02:03:26 | Button held 3 s | STANDBY, falling two-tone |

**Failure modes seen (for D8)**

- **Display and sound froze while the sensor was silent** (01:51). With no answer, each reading
  waited 0.5 s per try on both wire orientations, about 1.5 s per second, so the ring never got
  its turn: it stuck on steady red, the bursts stopped and the button was not read. Fixed: the
  sensor driver now keeps the light, sound and button running while it waits. A laptop test
  reproduces the bug and passes with the fix.
- **Loose breadboard lead after moving the sensor** (00:00): the sensor did not answer at power-up.
  Mitigation: the keyed Grove leads, and the TECHNICAL alarm, which now catches it within 1-2 s.
- **Trapped gas in a sealed cell** reads as CO2 present (above). Mitigation: airflow through the
  cell (open decision).

## 2026-10-22 · Session 2: power-on, first readings, first breath tests

**Bring-up**

- **Sensor answers.** LED steady at power-on; `boot_out.txt` read `CO2 OK: 500 ppm, wires normal`
  (twice, after two power-ups). The 500 ppm is the sensor's warm-up placeholder (read 2 s after
  power-on), not a measurement.
- **Data wires follow the datasheet after all:** blue = sensor RXD on GP0 (Pico TX), green =
  sensor TXD on GP1 (Pico RX). The 21 Oct failures were the unstripped wire ends, not the colours.
- **Supply:** 5.18 V at the Pico's VBUS pad (pass 4.75-5.25) and 3.31 V at its 3V3 pad (pass
  3.20-3.40). 5.18 V is above the sensor's nominal 5.0 ± 0.1 V but inside the 4.5-5.5 V its
  manual allows.

**Failure modes seen (for D8)**

- **USB data link dropped** mid-session ("Disk Not Ejected Properly") while the board stayed
  powered, LED on. Replugging fixed it. Second time (first: 21 Oct). Mitigation ideas: short
  known-good cable, a printed strain-relief clip, the laptop service treating "no data for N s" as
  a technical fault.
- **Calibration wire to ground:** the sensor's brown HD wire lay under the MacBook, whose metal
  case is at USB ground. While it touched (00:25:59 to 00:29:19) the reading sat at exactly
  400 ppm, the bottom of the scale. Freed, the reading came back to about 840 ppm, close to the
  850 before, so no lasting zero shift was seen (to confirm with a fresh-air check). Done: tip
  insulated and taped back; firmware v0.2 now flags 30 s at 400 ppm as a sensor fault (Terminal
  warning, slow LED blink). Open: remove or seal the HD wire for good (team decision).
- **Stuck at 400 a second time, cause unconfirmed:** at 01:31:46, after the HD tip was already
  insulated, the reading jumped 846 → 400 → 5,000 (12 s, top of the range) → 400, sat there until
  01:34:27, then climbed to 2,265 ppm and settled near 910. Jumps that big in 1 s are not real CO2:
  this is the sensor or its wiring, not the air. Candidates: the HD wire touching ground again, or a
  brief loss of sensor power through the thin breadboard leads while the bench was handled. After
  both episodes the reading overshot before settling, so treat the first 3 minutes after one as
  untrustworthy. The FAULT check caught both. Next session: check the HD tape, and wiggle red and
  black one at a time while watching for FAULT.
- **Operator breath is a confounder:** breathing while typing within arm's reach raised the
  reading by 800 to 900 ppm, more than a deliberate breath. Rule for test runs: operator at least
  1 m back; the flow-through cap must shield the sensor from room air.

**Tools added:** firmware v0.2 (one reading per second with a bar, breath-event timing, stuck-at-400
fault) and `tools/live_co2.sh` (live view in Terminal, saved to `data/raw/`). Two detection bugs
found on real data and fixed with tests: a restart mid-breath took the top of the breath as the room
level, and a slow rise lost its 10 % point ("rise n/a").

**After the session (until about 02:15):** firmware v0.3 with the CR-1 present/absent logic
(`lib/cr1.py`), LED and light-ring display (`lib/indicator.py`), and `tools/scripted_run.sh`
(spoken cues, scored for ER-1/ER-2). Replayed on tonight's readings: PRESENT during breath 3 and
ABSENT 17 s after the last breath in the rhythmic run; both stuck-at-400 episodes flagged as FAULT.
Not on the board yet. Draft CR-1 verification plan in `docs/D6-verification-plan.md`.

**Measurements** (open air, about 15 cm from the sensor, one reading per second)

| Run | Room air | Peak above room | First rise | Rise 10-90 % | Fall 90-10 % | Back near room air |
| --- | --- | --- | --- | --- | --- | --- |
| Breath 1, 00:40:10 | 843 ppm | +598 ppm at 20 s | 1 s | 12.7 s | 51 s | 81 s |
| Breath 2, 00:55 | 812 ppm | +309 ppm | 6 s after the stated time | 10.6 s | 66 s | 93 s after first rise |
| Rhythmic, 01:10:04, 15-16 breaths in 60 s | 802 ± 2.5 ppm | +1,014 ppm at 52 s (levelling off) | 7 s (breath 2) | 31 s (whole run) | 71 s | 89 s after stopping |

Rhythmic run in breaths (15/min): +100 ppm at breath 3, +300 ppm (the board's event threshold) at
breath 6, +500 ppm at breath 8. After stopping: falling after 17 s, half-way at 41 s, within
+50 ppm of room air at 113 s. Each breath left only about 2 ppm of ripple on the 1,000 ppm rise,
though the slope still shows the rhythm at about 15/min.

**What it means**

- CR-1 presence looks feasible within about 3 breaths with a +100 ppm threshold, once the cap keeps
  room air (and the operator) out.
- Absence called from the level takes about 22 breaths: far too slow. It has to come from the trend.
- This hardware supports a breath-averaged trend, not breath-by-breath capnography.

Data: `data/2026-10-22_session2_readings.csv` (labelled). Figures: `docs/figures/2026-10-22_*.png`.
Next: fresh-air zero check, self-calibration off (team decision), caliper measurements, print the
v1 parts in `hardware/cad/`, then repeat the runs through the cap and sampling line.

## 2026-10-21 · Sensor identification and first wiring

- **Sensor identified** from its label: Winsen MH-Z19C, 400–5000 ppm, 7-wire terminal
  cable. It talks UART, not I2C, so the Grove-to-Qwiic cables are not needed for it.
- **Board drive had no name** (left over from last week's interrupted copy); renamed to
  `CIRCUITPY`. Label change only, nothing erased.
- **USB data link is intermittent:** the board powered up (its Wi-Fi network was visible)
  while the Mac saw no drive. Replugging firmly fixed it. Candidate failure mode for D8.
- **Wiring attempt 1:** black wire one hole too high (GP1 instead of GND). Pin check found
  no signal on any pin: sensor unpowered.
- **Wiring attempt 2:** black moved to a GND hole. The sensor's output showed on **GP0**
  with blue in GP0 and green in GP1, the opposite of what the datasheet pin order implies.
- **Wiring attempt 3:** blue and green swapped; no signal on any pin again, suggesting
  loose header contacts.
- **Change:** driver rewritten to work with the data wires either way round, and a live
  LED test put on the board (steady = answering, blinking = no answer) so contacts can be
  checked without replugging.
- **Open:** confirm a reading, record the wire orientation in `hardware/wiring.md`.
  (Closed 22 Oct: reading confirmed, orientation `normal`.)
