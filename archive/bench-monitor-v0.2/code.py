# Team 6 - bench monitor v0.2 (session 2, 22 Oct 2026).
#
# Serial console: one line per second
#     t= 312 s  CO2  4870 ppm  |##########################....|  event
#   t is the time since the board was powered (the sensor needs ~75 s to warm up).
# It also spots CO2 events (e.g. a breath toward the sensor) and, when each one is over,
# prints the room level, the peak and how fast the sensor followed: 10-90 % rise time and
# 90-10 % fall time. Those numbers feed the response-time requirement (D1/D6/D7).
#
# Pico LED: steady on = sensor answering | two quick flashes = no answer |
#           slow blink = reading stuck at 400 ppm, the bottom of the scale (sensor fault).
# A reading pinned at 400 is not room air (outdoor air is ~420 ppm). On 22 Oct it happened
# while the sensor's brown calibration wire (HD) touched the laptop's grounded case.
# On the Mac: bash tools/live_co2.sh  (shows this output and saves it to data/raw/)
import time
import board
import digitalio
from mhz19c import read_co2, probe
from co2events import EventDetector, TOP_PPM, describe

WARMUP_S = 75          # placeholder readings (e.g. 500 ppm) come before this
FLOOR_PPM = 400        # bottom of the sensor's scale
STUCK_S = 30           # this many readings in a row at the floor = sensor fault
BAR_LO, BAR_HI, BAR_W = 400, TOP_PPM, 30

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT


def bar(ppm):
    f = (min(max(ppm, BAR_LO), BAR_HI) - BAR_LO) / (BAR_HI - BAR_LO)
    n = int(f * BAR_W + 0.5)
    return "|" + "#" * n + "." * (BAR_W - n) + "|"


def flash_no_answer():
    for _ in range(2):
        led.value = True
        time.sleep(0.15)
        led.value = False
        time.sleep(0.35)


print()
print("Team 6 CO2 bench monitor v0.2 - one reading per second, scale %d-%d ppm" % (BAR_LO, BAR_HI))
print("Breath test: breathe out gently toward the sensor, then step back and wait.")

orientation = "normal"
detector = EventDetector(max_event_s=300)
floor_run = 0
room_shown = None
next_t = time.monotonic()

while True:
    ppm = read_co2(orientation)
    if ppm is None:                      # wires moved? try both orientations
        found, ppm = probe()
        if found:
            orientation = found
    t = time.monotonic()

    if ppm is None:
        print("t=%5d s  no answer from sensor" % int(t))
        flash_no_answer()
        next_t = time.monotonic()
        continue

    notes = []
    messages = []
    was_stuck = floor_run >= STUCK_S
    floor_run = floor_run + 1 if ppm <= FLOOR_PPM else 0
    stuck = floor_run >= STUCK_S
    if was_stuck and not stuck:
        messages.append("--- reading is off the floor again; measuring the room level afresh ---")
    led.value = (not led.value) if stuck else True
    if floor_run == STUCK_S:
        detector.reset()
        room_shown = None
        messages.append("!!! SENSOR FAULT: reading stuck at %d ppm (bottom of the scale) for %d s."
                        " Check that the brown calibration wire is not touching metal. !!!"
                        % (FLOOR_PPM, STUCK_S))
    if t < WARMUP_S:
        notes.append("warming up")
    elif stuck:
        notes.append("STUCK AT FLOOR")
    else:
        result = detector.update(t, ppm)
        if result == "start":
            messages.append("--- CO2 event %d started: %d ppm above the room level of %d ppm ---"
                            % (detector.count, ppm - detector.room, detector.room))
        elif result is not None:
            messages.extend(describe(result))
            room_shown = None
        if detector.event is not None:
            notes.append("event")
        else:
            room = detector.armed
            if room is not None and room_shown is None:
                room_shown = room
                messages.append("--- room level: %d ppm (steady over the last %d s); ready for a breath test ---"
                                % (room, detector.room_seconds()))
    if ppm >= TOP_PPM:
        notes.append("TOP OF RANGE")

    print("t=%5d s  CO2 %5d ppm  %s  %s" % (int(t), ppm, bar(ppm), " ".join(notes)))
    for m in messages:
        print(m)

    next_t += 1.0
    wait = next_t - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    else:
        next_t = time.monotonic()
