# Team 6 - CO2 monitor v0.3 (CR-1: is exhaled CO2 present or absent?)
#
# Serial console, one line per second:
#     t= 312 s  CO2  1814 ppm  |##########....................|  PRESENT
#   and a banner whenever the state changes, e.g.  >>> CO2 PRESENT: +102 ppm in under 30 s <<<
# States (lib/cr1.py): WARMING UP -> ABSENT <-> PRESENT, and FAULT (no answer, or stuck at 400).
# Display (lib/indicator.py): the Pico LED now; the light ring once it is soldered (set RING_PIN).
# Response timing for each CO2 event (room level, peak, 10-90 % rise, 90-10 % fall) is still
# printed for the characterisation runs (lib/co2events.py).
#
# On the Mac:  bash tools/live_co2.sh       live view, saved to data/raw/
#              bash tools/scripted_run.sh   spoken cues for verification runs, scored for ER-1/ER-2
import time
import board
from mhz19c import read_co2, probe
from co2events import EventDetector, TOP_PPM, describe
from cr1 import PresenceMonitor, WARMING_UP, FAULT
from indicator import Indicator

RING_PIN = None        # board.GP16 once the light ring is soldered and plugged into D16
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
events = EventDetector(max_event_s=300)
show = Indicator(board.LED, RING_PIN)
orientation = "normal"
room_shown = None

print()
print("Team 6 CO2 monitor v0.3 - CR-1 present/absent, one reading per second, scale %d-%d ppm"
      % (BAR_LO, BAR_HI))

next_t = time.monotonic()
while True:
    ppm = read_co2(orientation)
    if ppm is None:                       # wires moved? try both orientations
        found, ppm = probe()
        if found:
            orientation = found
    t = time.monotonic()
    changed = monitor.update(t, ppm)
    show.show(monitor.state)

    messages = []
    if changed:
        messages.append(">>> %s: %s <<<" % (BANNER[monitor.state], monitor.reason))
        if monitor.state == FAULT:
            events.reset()
            room_shown = None

    if ppm is None:
        print("t=%5d s  no answer from sensor  %s" % (int(t), monitor.state))
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
        print("t=%5d s  CO2 %5d ppm  %s  %-10s %s" % (int(t), ppm, bar(ppm), monitor.state, " ".join(notes)))
    for m in messages:
        print(m)

    next_t += 1.0
    wait = next_t - time.monotonic()
    if wait > 0:
        show.wait(wait)
    else:
        next_t = time.monotonic()
