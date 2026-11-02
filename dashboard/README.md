# Dashboard (browser)

Two pages served by the laptop service: the monitor, `index.html`, at <http://localhost:8000>, and
the sign-up page for phone alerts, `register.html`, at <http://localhost:8000/register>. Start them
with `bash tools/dashboard.sh` from the repository folder; the browser opens by itself. The monitor
page shows what the box decided, live, with the same colours and sounds, so the screen and the box
speak one language. The box keeps its own light and sound: the dashboard adds a second place to see
and hear the alarm, an acknowledge with initials, the trend, the record and the phone messages.

Click **Turn on alarm sound** once after opening the page: browsers only play sound after a click.

## What is on the screen

| Part | What it shows |
| --- | --- |
| Light ring | The box's 16-light ring, drawn from `firmware/lib/indicator.py`: same colour and pattern for every state |
| State word and line | Breathing, CO₂ lost, CO₂ back, Sensor problem, Standby, No data, and one line of what to do |
| Alarm band | The alarm and the board's reason for it, initials and **Acknowledge** while it sounds, and who acknowledged it, how and when |
| CO₂ at the sensor | The reading in ppm, with a warning at the bottom (400) or top (5,000) of the sensor's scale |
| Exhaled CO₂ | CR-1: Present or Absent, and since when |
| Trend | CO₂ over the last 10 minutes, with a strip of colour underneath for the state at each moment |
| Alarms | The log: start, how long it lasted, the reason, each acknowledgement (dashboard or bedside button), and who was messaged |
| This screen | Firmware version, the serial port, the raw log being written, whether sound is on, a test sound, how many people get phone messages, and any message that could not be sent |

The tab title follows the state, so the alarm shows even when the window is behind others.

## Sounds

The same patterns as the box, after IEC 60601-1-8 (the more pulses, the higher the priority):

| State | Light | Sound |
| --- | --- | --- |
| Critical | Red, fast flash | 10 pulses (3+2+3+2), every 10 s, until acknowledged |
| Critical, acknowledged | Red, steady | None for 2 minutes |
| CO₂ back, not acknowledged | Red and green in turn | 10 pulses, every 10 s: the alarm stays until someone acknowledges it |
| Advisory | Amber, slow flash | 3 pulses, every 20 s (waits for CR-4 on the board) |
| Technical | Cyan | Two-tone chirp, every 30 s |
| Normal, Standby | Green, or one white light circling | None |

## Two alarms only the screen can raise

- **No data** (*LINK LOST*): nothing from the board for 5 s, for example the USB cable pulled or
  the board restarting after a file copy. Cyan, breathing, with the technical chirp. On the bench
  the cable also powers the box, so with the cable out the box is dark and silent and this screen
  is the only alarm left.
- **No service**: the page cannot reach the laptop service for 4 s (the service stopped or the
  laptop is struggling). Same look, and the page says how to start the service again.

In both cases a critical alarm that was on and not acknowledged stays red on screen, with a note
that it is the last one received: a fault never hides a patient alarm. The numbers fade and show
the time of the last reading.

## Acknowledge

Type your initials once (the page remembers them) and press **Acknowledge**. The service sends the
acknowledgement to the box, which handles it like a press of its own button: sound off for
2 minutes, light steady red. The page then says either *The monitor confirmed: its sound is off
too*, or, if the box did not confirm (older firmware or no cable), that only this screen is quiet
and the box keeps sounding until someone presses its button. Every acknowledgement is recorded
with who, how and when.

## Phone alerts: the sign-up page

`register.html`, at <http://localhost:8000/register> (the **Manage** or **Sign up** link under
*This screen*). Each person:

1. Picks WhatsApp, Signal or Telegram. The page shows how to get a key from CallMeBot's bot for
   that app: send it *I allow callmebot to send me messages* (WhatsApp, Signal), or `/start`
   (Telegram, no key needed).
2. Gives a name, the number with its country code and the key (or the Telegram username), and
   chooses every alarm message or backup only (a critical alarm nobody acknowledged in 2 minutes).
3. Ticks the consent box and signs up. A test message goes at once; the list below shows whether it
   went, with CallMeBot's answer when it did not.

The list shows everyone signed up, with only the end of each number and never the key, and lets
anyone send a test, stop someone's messages or start them again. When the messages come is set out
in [service/README.md](../service/README.md#messages-to-phones).

## Other screens

`bash tools/dashboard.sh --lan` lets a phone or tablet on the same Wi-Fi open the pages at the
address the service prints, so people can also sign up from their own phone. It is off by default
because anyone on that network could open them.

## Built without outside libraries

Plain HTML, CSS and JavaScript, one file per page, with no downloads from the internet: the monitor
works at a bench with no connection (only the phone messages need one), and nothing can change
under it before the demonstration. The trend is drawn on a canvas for that reason, instead of
Chart.js or Plotly.

## Still to do

- Breathing-rate trend, once CR-4 exists on the board.
