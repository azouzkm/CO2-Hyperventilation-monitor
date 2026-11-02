# Team 6 - CO2 monitor v0.6: CR-1 present/absent, the project card's four alarm states, the breathing
# rate (CR-4), the safety clip on the sampling line (CR-3), and the link to the laptop service and dashboard
#
# Serial console (USB), two lines per second:
#     t= 312 s  CO2  1814 ppm  |##########....................|  PRESENT    NORMAL       RR 15.2
#     {"v": "0.6", "t": 312, "ppm": 1814, "cr1": "PRESENT", "alarm": "NORMAL", "rr": 15.2, "line": true, ...}
#   The first is for people (CR-1 state, then the alarm state); the second is for the laptop service
#   (service/), one JSON object per line. A banner marks every change, e.g.
#     >>> CO2 ABSENT: fell 108 ppm from 1814 in under 20 s <<<
#     >>> ALARM CRITICAL: CO2 lost: fell 108 ppm from 1814 in under 20 s <<<
# Commands from the laptop, one per line: ACK (the dashboard's acknowledge button, same as a short
#   press of the bedside button). The board decides every alarm itself, and keeps alarming if the
#   laptop or the service stops or the USB data link drops, as long as it has power.
# CR-1 (lib/cr1.py): WARMING UP -> ABSENT <-> PRESENT, and FAULT (no answer, stuck at 400, or a jump
#   no real CO2 change can make), then a 3-minute re-warm.
# Alarm (lib/alarm.py): STANDBY until the first breath, then NORMAL (green), CRITICAL (red, 10 pulses,
#   latched) when CO2 is lost, TECHNICAL (cyan, chirp) for any sensor problem, never CRITICAL.
#   After a fault, 30 s for a breath once the sensor is trusted again, then CRITICAL if still no CO2.
#   ADVISORY (amber, 3 pulses): CR-4 sees a sustained fall of the breathing rate or of the CO2.
#   A reading stuck at the top of the scale (5,000 ppm) for 30 s is TECHNICAL: breaths cannot be seen.
#   A CRITICAL alarm ends once it is acknowledged and CO2 is back, in either order.
# CR-4 (lib/cr4.py): the breathing rate from the rhythm of the CO2 signal, "RR" on each line
#   ("RR --" when it cannot be resolved; the banner says why), worked out every 2 s.
# Safety clip on the sampling line (GP21 to GND, lib/lineclip.py): tube off = TECHNICAL "LINE OFF" (CR-3).
# Button (GP20): press = acknowledge (sound off 2 min); hold 3 s = stop monitoring (STANDBY).
# Display: Pico LED and the light ring on D16 (lib/indicator.py). Sound: speaker on GP18 (lib/annunciator.py).
# At power-up: every alarm colour for 0.4 s (lamp test), then a rising chirp (speaker test).
# Response timing for each CO2 event is still printed for the characterisation runs (lib/co2events.py).
#
# On the Mac:  bash tools/dashboard.sh      dashboard in the browser, readings saved to data/raw/
#              bash tools/live_co2.sh       live view in Terminal only, saved to data/raw/
#              bash tools/scripted_run.sh   spoken cues for verification runs, scored for ER-1/ER-2
import json
import sys
import time
import board
import digitalio
from mhz19c import read_co2, probe
from co2events import EventDetector, TOP_PPM, describe
from cr1 import PresenceMonitor, WARMING_UP, FAULT
from alarm import AlarmManager, SATURATED_S
from cr4 import RateMonitor
from lineclip import LineClip
from indicator import Indicator
from annunciator import Annunciator, HOLD_S

try:
    import supervisor                     # CircuitPython: tells whether the laptop sent anything
except ImportError:                       # laptop dry runs
    supervisor = None

VERSION = "0.6"

RING_PIN = board.GP16     # light ring on the Grove shield's D16 socket (None = Pico LED only)
SPEAKER_PIN = board.GP18  # speaker (through a resistor, or the PAM8302 amplifier's A+ input)
BUTTON_PIN = board.GP20   # acknowledge button, other side to GND
LINE_PIN = board.GP21     # safety clip on the sampling line, other side to GND
BAR_LO, BAR_HI, BAR_W = 400, TOP_PPM, 30

BANNER = {
    "PRESENT": "CO2 PRESENT",
    "ABSENT": "CO2 ABSENT",
    "WARMING UP": "WARMING UP",
    "FAULT": "SENSOR FAULT",
}


def bar(ppm):
    f = (min(max(ppm, BAR_LO), BAR_HI) - BAR_LO) / (BAR_HI - BAR_LO)
    n = int(f * BAR_W + 0.5)
    return "|" + "#" * n + "." * (BAR_W - n) + "|"


monitor = PresenceMonitor()
breathing = RateMonitor()
alarm = AlarmManager()
events = EventDetector(max_event_s=300)
show = Indicator(board.LED, RING_PIN)
sound = Annunciator(SPEAKER_PIN, BUTTON_PIN)
line_pin = digitalio.DigitalInOut(LINE_PIN)
line_pin.direction = digitalio.Direction.INPUT
line_pin.pull = digitalio.Pull.UP
line = LineClip()
orientation = "normal"
room_shown = None


def idle(now):
    """Keep the light flashing, the sound playing, the button and the safety clip read while waiting."""
    sound.service(now)
    line.sample(now, line_pin.value)
    show.tick(now)


def keep_alive():
    """The same, called by CR-4 while it works out the breathing rate."""
    idle(time.monotonic())


timing_shown = False
top_run = 0                               # readings in a row at the top of the scale


_typed = ""


def commands():
    """Whole lines the laptop has sent since the last call (e.g. "ACK"). Never waits."""
    global _typed
    out = []
    if supervisor is None:
        return out
    while supervisor.runtime.serial_bytes_available:
        c = sys.stdin.read(1)
        if c in ("\n", "\r"):
            if _typed.strip():
                out.append(_typed.strip().upper())
            _typed = ""
        elif len(_typed) < 40:
            _typed += c
    return out


print()
print("Team 6 CO2 monitor v%s - CR-1 present/absent, the four alarm states, breathing rate, line clip, "
      "one reading per second, scale %d-%d ppm" % (VERSION, BAR_LO, BAR_HI))

for lamp in ("LAMP GREEN", "LAMP AMBER", "LAMP RED", "LAMP CYAN"):   # lamp test
    show.show(lamp)
    show.wait(0.4, sound.service)
sound.play(time.monotonic(), "start")                             # speaker test
show.show(alarm.display())

next_t = time.monotonic()
while True:
    ppm = read_co2(orientation, idle)
    if ppm is None:                       # wires moved? try both orientations
        found, ppm = probe(idle)
        if found:
            orientation = found
    t = time.monotonic()
    changed = monitor.update(t, ppm)
    short, held = sound.take_presses()
    line.sample(t, line_pin.value)
    remote = sum(1 for c in commands() if c == "ACK")   # the dashboard's acknowledge button

    messages = []
    if short:
        messages.append(">>> BUTTON pressed <<<")
    if held:
        messages.append(">>> BUTTON held %d s <<<" % HOLD_S)
    if remote:
        messages.append(">>> ACK from the dashboard <<<")
    if line.take_change():
        messages.append(">>> SAMPLING LINE %s <<<" % ("CONNECTED (safety clip closed)" if line.connected
                                                      else "OFF (safety clip open)"))
    if changed:
        messages.append(">>> %s: %s <<<" % (BANNER[monitor.state], monitor.reason))
        if monitor.state == FAULT:
            events.reset()
            room_shown = None
    if held:
        breathing.restart()                 # monitoring stopped: forget the patient's baselines
    started = time.monotonic()
    rate_banner = breathing.update(t, ppm, monitor.state, keep_alive)
    top_run = top_run + 1 if ppm is not None and ppm >= TOP_PPM else 0
    if breathing.breathing.evaluated and not timing_shown:
        timing_shown = True
        messages.append("--- CR-4: one breathing-rate estimate took %d ms ---"
                        % int(1000 * (time.monotonic() - started)))
    if rate_banner:
        messages.append(">>> %s <<<" % rate_banner)
    for action in alarm.update(t, monitor.state, monitor.reason, ppm, short + remote, held,
                               breathing.advisory, line.connected, top_run >= SATURATED_S):
        if action[0] == "banner":
            messages.append(">>> %s <<<" % action[1])
        elif action[0] == "cancel":
            sound.cancel()
        else:
            sound.play(t, action[1])
    show.show(alarm.display())

    if ppm is None:
        print("t=%5d s  no answer from sensor  %-10s %s" % (int(t), monitor.state, alarm.display()))
    else:
        notes = []
        if monitor.state not in (WARMING_UP, FAULT):
            result = events.update(t, ppm)
            if result == "start":
                messages.append("--- CO2 event %d: %d ppm above the room level of %d ppm ---"
                                % (events.count, ppm - events.room, events.room))
            elif result is not None:
                messages.extend(describe(result))
                room_shown = None
            if events.event is not None:
                notes.append("event")
            elif events.armed is not None and room_shown is None:
                room_shown = events.armed
                messages.append("--- room level: %d ppm (steady over the last %d s); ready for a test ---"
                                % (events.armed, events.room_seconds()))
        if ppm >= TOP_PPM:
            notes.append("TOP OF RANGE")
        if not line.connected:
            notes.append("LINE OFF")
        print("t=%5d s  CO2 %5d ppm  %s  %-10s %-12s %-7s %s"
              % (int(t), ppm, bar(ppm), monitor.state, alarm.display(), breathing.shown(), " ".join(notes)))
    for m in messages:
        print(m)
    print(json.dumps({"v": VERSION, "t": int(t), "ppm": ppm, "cr1": monitor.state, "cr1_why": monitor.reason,
                      "alarm": alarm.state, "show": alarm.display(), "why": alarm.reason,
                      "acked": alarm.acked, "latched": alarm.latched,
                      "press": short, "hold": held, "dash_ack": remote,
                      "rr": None if breathing.rate is None else round(breathing.rate, 1),
                      "rr_why": breathing.breathing.why, "advisory": breathing.advisory,
                      "line": line.connected}))

    next_t += 1.0
    wait = next_t - time.monotonic()
    if wait > 0:
        show.wait(wait, sound.service)
    else:
        sound.service(time.monotonic())
        next_t = time.monotonic()
