# Service (laptop)

The laptop half of the monitor. It reads the board over USB, saves every line it sends, keeps the
readings and the alarms in a SQLite database, sends alarm messages to phones, and serves the
dashboard on <http://localhost:8000>. Start it from the repository folder with:

```bash
bash tools/dashboard.sh
```

The first run installs Flask, pyserial and certifi into `.venv/` (it needs the internet once). The
script opens the dashboard in the browser, and starts the service again if it ever stops on an
error.

## The board decides, the service mirrors

The board raises every patient and sensor alarm itself, so a crashed laptop or a stopped service
can never silence it (failure mode FM-5 in the worked example). On the bench the USB cable also
powers the board, so a pulled cable turns the box off as well; the dashboard's link alarm, and the
phone message a minute later, are then the only alarms, and a power source of the box's own would
close that gap. The service never works out a CO₂ alarm of its own: it shows, records and messages
what the board decided. That keeps one alarm path, so the box, the screen and the phones cannot
disagree.

The service adds only what the board cannot do:

- **No data from the board.** After 5 s without a line (`technical_timeout_s` in
  [config.json](../config.json)) it raises a Technical alarm, *LINK LOST*. It clears by itself when
  readings return. A critical alarm that was on and not acknowledged stays on screen during the
  outage: a fault never hides a patient alarm.
- **The dashboard's acknowledge.** The dashboard asks for initials, the service sends `ACK` to the
  board, and the board acknowledges exactly as if its button had been pressed. Its next reading
  says so (`"dash_ack": 1`), and only then is the acknowledgement recorded as confirmed. If the
  board does not confirm within 5 s (older firmware, or the cable is out), that screen goes quiet
  for 2 minutes and says plainly that the box keeps sounding until someone presses its button.
- **Messages to phones** (below).

Stopping monitoring (holding the button for 3 s) stays at the bedside only, on purpose.

## Messages to phones

Course participants sign up on the dashboard's **Phone alerts** page (<http://localhost:8000/register>),
with WhatsApp, Signal or Telegram through CallMeBot, the free service listed on the project card.
CallMeBot only lets people message themselves, so each person gets their own key from its bot (for
Telegram, they start its bot instead). Ticking the consent box is required, and the time is stored.

| Alarm | Message (workshop slide 11; numbers in `config.json`, `notify`) |
| --- | --- |
| Critical | At once to everyone on the first list. Again at 120 s if nobody has acknowledged it, then to the backups too |
| Advisory | If it lasts 60 s |
| Technical | If it lasts 60 s: a sensor or link fault means the patient is not being watched. Not for "no data yet" at start-up, before the monitor was ever plugged in |
| Ended | One short follow-up to whoever really received a message about that alarm |

An acknowledgement (bedside button or dashboard) stops the escalation and any message still
waiting. Each message is one HTTPS request to CallMeBot. When CallMeBot cannot be reached it is
tried again after 10 s and 30 s; a refused key or sign-up fails at once, since trying again would
not help. Every message and its outcome is recorded, and a failed one shows on the dashboard.
CallMeBot sends no delivery receipt, so *sent* means CallMeBot accepted it. At most 10 messages per
person in 10 minutes, so a fault that comes and goes cannot flood a phone. No patient identifiers
in any message: it names the alarm, the time and the board's reason.

A replay sends no alarm messages (they would be old news), but a sign-up test message still goes.
`--no-messages` sends nothing at all, for bench tests that pull wires on purpose.

## Files

| File | What it does |
| --- | --- |
| `__main__.py` | `python3 -m service`: starts everything. Options below |
| `logger.py` | The USB link (IF-6): finds the Pico, reads it line by line, finds it again after the cable is pulled, sends `ACK`. Writes the raw log. Also plays recorded logs for demos (`--replay`) |
| `parse.py` | Turns each line into a reading: the JSON line from firmware v0.5, or the text line from older firmware |
| `rules_engine.py` | Mirrors the board's alarm, adds the link alarm, handles acknowledgements and the 2-minute silence. Pure Python with explicit times, so the tests can drive it second by second |
| `notifier.py` | Messages to phones (IF-9): who is told what and when, sending through CallMeBot with retries, and the sign-up checks |
| `store.py` | The SQLite database (IF-7) |
| `core.py` | Ties the parts together and reads [config.json](../config.json) |
| `main.py` | The REST layer (IF-8), the dashboard and the sign-up page, with Flask |

## Interfaces

**IF-6, board ↔ service:** USB serial, 115200 baud. Firmware v0.5 prints two lines per reading:
the text line for people, and one JSON object for the service:

```json
{"v": "0.5", "t": 312, "ppm": 1814, "cr1": "PRESENT", "cr1_why": "...", "alarm": "NORMAL",
 "show": "NORMAL", "why": "...", "acked": false, "latched": false, "press": 0, "hold": 0, "dash_ack": 0}
```

`t` is seconds since the board started; `ppm` is `null` when the sensor did not answer; `show` is
what the light ring shows (`CRITICAL ACK` after an acknowledgement, `CRITICAL BACK` while CO₂ has
returned but nobody has acknowledged); `press`, `hold` and `dash_ack` count button presses, 3-second
holds and dashboard acknowledgements in that second. The other way, the service sends one command
per line: `ACK`. Older firmware (text lines only) still works, without the dashboard's acknowledge.

**IF-7, service → database:** `data/co2monitor.sqlite`, write-ahead logging, one writer. It stays on
this laptop and git ignores it: it holds phone numbers and CallMeBot keys. The raw logs in
`data/raw/` stay the evidence for the verification report.

| Table | One row per |
| --- | --- |
| `readings` | reading: time, ppm, CR-1 state, alarm state, what the ring showed, data quality |
| `alarm_events` | alarm, from the board or the link watchdog: priority, start, end, reason, ppm at the start |
| `acks` | acknowledgement: which alarm, who (initials), how (bedside button or dashboard), confirmed by the board or not |
| `device_events` | banner line from the board (state changes, button presses) |
| `users` | person signed up for messages: name, app, number or Telegram name, key, first list or backup, when they agreed (and stopped) |
| `notifications` | message: which alarm, to whom, its text, how many tries, sent or failed and why |
| `calibrations` | calibration fit against the reference capnograph |

No patient identifiers go into any table.

**IF-8, service → dashboard:** HTTP on localhost, JSON, polled once a second.

| Request | Answer |
| --- | --- |
| `GET /api/latest` | What to show and sound now: state, CO₂, link, the last acknowledgement. Keeps the starter contract's `co2_pct` and `state` |
| `GET /api/readings?seconds=600` | The trend: `[time, ppm, state]` per reading |
| `GET /api/alarms?limit=20` | The alarm log, newest first, with its acknowledgements and messages, and a summary of phone alerts |
| `POST /api/ack` with `{"who": "AM"}` | Acknowledge from the dashboard. `409` with a message when it cannot (no initials, or nothing to acknowledge) |
| `GET /api/users` | The people signed up, without their keys and with only the end of their number |
| `POST /api/users` | Sign up: `name`, `role`, `channel` (`whatsapp`, `signal` or `telegram`), `phone` and `apikey`, or `telegram`, `level` (1 first list, 2 backup), `consent: true`. Sends a test message. `400` with what to fix |
| `POST /api/users/<id>/test`, `/stop`, `/start` | A test message; stop someone's messages (their consent record stays); start them again |
| `GET /api/notifications?limit=20` | The latest messages and how they went |
| `GET /api/health` | `{"ok": true}` while the service runs |

**IF-9, service → messaging provider:** HTTPS GET to CallMeBot (`api.callmebot.com` for WhatsApp
and Telegram, `signal.callmebot.com` for Signal), with retries and the failed messages shown on
the dashboard.

## Options

`bash tools/dashboard.sh` passes these on to `python3 -m service`:

| Option | Effect |
| --- | --- |
| `--replay data/raw/<log>` | Play a recorded session instead of reading the board. `--speed 5` plays it 5 times faster, `--loop` starts again at the end |
| `--no-messages` | Send nothing to phones, not even a test (for bench tests that pull wires) |
| `--port /dev/cu.usbmodem1101` | Use this serial port instead of finding the Pico by itself |
| `--http-port 8001` | If port 8000 is taken |
| `--lan` | Let a phone or tablet on the same Wi-Fi open the dashboard and the sign-up page. Off by default: anyone on that network could open them. Campus Wi-Fi often blocks this; a phone hotspot works |
| `--db <file>` | Another database file |

A replay is not new evidence: it writes no raw log, and it keeps its own database,
`data/replay.sqlite`, so it never mixes with the real readings in `data/co2monitor.sqlite`. The
people signed up for messages are shared, so nobody signs up twice.

## Tests

`tests/test_service.py` (19 tests): reading the board's lines, the rules engine second by second
(alarm records, link lost, acknowledgements, the 2-minute silence), the database, the REST layer,
the serial link through a pseudo-terminal standing in for the Pico, and the real 25 Oct alarm test
replayed through the whole service. The replay finds the critical alarm at 01:46:46 with the
bedside acknowledgement at 01:47:35, the pulled data wire as Technical at 01:58:22, and link alarms
only during the two firmware reloads.

`tests/test_notifier.py` (23 tests): the CallMeBot addresses for each app, who is told what and
when (at once, after a minute, escalation at 120 s, the follow-up, nothing after an
acknowledgement), the three tries, a refused key, replays and `--no-messages`, the flood limit,
the sign-up checks, and that a browser never sees a key. No test touches the network: a fake
CallMeBot stands in.

## Why Flask and not FastAPI

The team's first skeleton used FastAPI; the project card lists both. Flask serves the page and the
API with its own built-in server (FastAPI needs uvicorn as well), it is plain synchronous code like
the serial thread beside it, and one laptop with one browser needs nothing more. What FastAPI adds
(asynchronous requests, automatic API pages) matters little here. The starter REST contract
(`/api/latest` with `co2_pct` and `state`, `/api/ack`) is kept.

## Why CallMeBot

It is free and listed on the project card, and needs no account for the team: each person
activates their own key in a minute. The limits are stated where they matter: it is meant for
personal use, it only messages the person who activated the key, it sends no delivery receipt,
and its WhatsApp page said the bot was full when checked on 27 Oct 2026, which is why Signal and
Telegram work too.
The Twilio WhatsApp sandbox (with delivery receipts) is the fallback if CallMeBot proves
unreliable during verification.

## Still to do

- Breathing rate and its trend, once CR-4 exists on the board.
