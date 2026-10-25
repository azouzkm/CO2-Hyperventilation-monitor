# Team 6 - CO2 monitor v0.4: CR-1 present/absent, and the project card's four alarm states (test version)
#
# Serial console, one line per second:
#     t= 312 s  CO2  1814 ppm  |##########....................|  PRESENT    NORMAL
#   (CR-1 state, then the alarm state) and a banner at every change, e.g.
#     >>> CO2 ABSENT: fell 108 ppm from 1814 in under 20 s <<<
#     >>> ALARM CRITICAL: CO2 lost: fell 108 ppm from 1814 in under 20 s <<<
# CR-1 (lib/cr1.py): WARMING UP -> ABSENT <-> PRESENT, and FAULT (no answer, stuck at 400, or a jump
#   no real CO2 change can make), then a 3-minute re-warm.
# Alarm (lib/alarm.py): STANDBY until the first breath, then NORMAL (green), CRITICAL (red, 10 pulses,
#   latched) when CO2 is lost, TECHNICAL (cyan, chirp) for any sensor problem, never CRITICAL.
#   After a fault, 30 s for a breath once the sensor is trusted again, then CRITICAL if still no CO2.
#   ADVISORY (amber, 3 pulses) is wired up but waits for CR-4.
# Button (GP20): press = acknowledge (sound off 2 min); hold 3 s = stop monitoring (STANDBY).
# Display: Pico LED and the light ring on D16 (lib/indicator.py). Sound: speaker on GP18 (lib/annunciator.py).
# At power-up: every alarm colour for 0.4 s (lamp test), then a rising chirp (speaker test).
# Response timing for each CO2 event is still printed for the characterisation runs (lib/co2events.py).
#
# On the Mac:  bash tools/live_co2.sh       live view, saved to data/raw/
#              bash tools/scripted_run.sh   spoken cues for verification runs, scored for ER-1/ER-2
import time
import board
from mhz19c import read_co2, probe
from co2events import EventDetector, TOP_PPM, describe
from cr1 import PresenceMonitor, WARMING_UP, FAULT
from alarm import AlarmManager
from indicator import Indicator
from annunciator import Annunciator, HOLD_S

RING_PIN = board.GP16     # light ring on the Grove shield's D16 socket (None = Pico LED only)
SPEAKER_PIN = board.GP18  # speaker (through a resistor, or the PAM8302 amplifier's A+ input)
BUTTON_PIN = board.GP20   # acknowledge button, other side to GND
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
alarm = AlarmManager()
events = EventDetector(max_event_s=300)
show = Indicator(board.LED, RING_PIN)
sound = Annunciator(SPEAKER_PIN, BUTTON_PIN)
orientation = "normal"
room_shown = None


def idle(now):
    """Keep the light flashing, the sound playing and the button read while waiting for the sensor."""
    sound.service(now)
    show.tick(now)


print()
print("Team 6 CO2 monitor v0.4 - CR-1 present/absent and the four alarm states (test version), "
      "one reading per second, scale %d-%d ppm" % (BAR_LO, BAR_HI))

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

    messages = []
    if short:
        messages.append(">>> BUTTON pressed <<<")
    if held:
        messages.append(">>> BUTTON held %d s <<<" % HOLD_S)
    if changed:
        messages.append(">>> %s: %s <<<" % (BANNER[monitor.state], monitor.reason))
        if monitor.state == FAULT:
            events.reset()
            room_shown = None
    for action in alarm.update(t, monitor.state, monitor.reason, ppm, short, held):
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
        print("t=%5d s  CO2 %5d ppm  %s  %-10s %-12s %s"
              % (int(t), ppm, bar(ppm), monitor.state, alarm.display(), " ".join(notes)))
    for m in messages:
        print(m)

    next_t += 1.0
    wait = next_t - time.monotonic()
    if wait > 0:
        show.wait(wait, sound.service)
    else:
        sound.service(time.monotonic())
        next_t = time.monotonic()
