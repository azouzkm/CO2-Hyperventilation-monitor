"""Laptop-side tests for firmware/lib/co2events.py and a dry run of firmware/code.py.

Run from the repository root:   python -m pytest tests/
(or without pytest:              python tests/test_co2events.py)
"""
import math
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

from co2events import EventDetector, TOP_PPM, describe  # noqa: E402

LN9 = math.log(9)  # first-order system: 10-90 % time = tau * ln 9


def first_order(t, t_on, t_off, room, target, tau_up, tau_down):
    """CO2 seen by a first-order sensor when gas at `target` ppm arrives between t_on and t_off."""
    if t < t_on:
        return room
    if t < t_off:
        return room + (target - room) * (1 - math.exp(-(t - t_on) / tau_up))
    at_off = room + (target - room) * (1 - math.exp(-(t_off - t_on) / tau_up))
    return room + (at_off - room) * math.exp(-(t - t_off) / tau_down)


def run(curve, seconds, clip=True):
    det = EventDetector()
    out = []
    for t in range(seconds):
        ppm = int(round(curve(t)))
        if clip:
            ppm = min(ppm, TOP_PPM)
        r = det.update(float(t), ppm)
        if isinstance(r, dict):
            out.append(r)
    return det, out


def test_quiet_room_has_no_event():
    det, out = run(lambda t: 610 + 8 * math.sin(t / 3.0), 300)
    assert out == [] and det.count == 0
    assert 600 <= det.room_level() <= 620


def test_rise_and_fall_times_match_a_known_first_order_response():
    # long exposure so the curve settles: 10-90 % should equal tau * ln 9 in both directions
    tau_up, tau_down = 10.0, 30.0
    det, out = run(lambda t: first_order(t, 100, 220, 600, 3000, tau_up, tau_down), 600)
    assert len(out) == 1
    s = out[0]
    assert s["room"] == 600 and not s["capped"] and s["returned"]
    assert abs(s["rise_s"] - tau_up * LN9) < 1.0, s
    assert abs(s["fall_s"] - tau_down * LN9) < 1.0, s


def test_breath_that_hits_the_ceiling_is_flagged():
    det, out = run(lambda t: first_order(t, 60, 70, 620, 12000, 8.0, 40.0), 500)
    assert len(out) == 1
    s = out[0]
    assert s["capped"] and s["peak"] == TOP_PPM
    assert s["rise_s"] is not None and s["fall_s"] is not None
    text = "\n".join(describe(s))
    assert "top of range" in text and "ceiling" in text


def test_room_level_waits_for_the_tail_of_an_event_to_settle():
    curve = lambda t: first_order(t, 60, 70, 620, 4000, 6.0, 40.0)  # noqa: E731
    det = EventDetector()
    ended_at = None
    levels_after = []
    for t in range(600):
        r = det.update(float(t), int(round(curve(t))))
        if isinstance(r, dict):
            ended_at = t
        elif ended_at is not None and det.event is None:
            levels_after.append((t, det.room_level()))
    assert ended_at is not None
    assert levels_after[0][1] is None              # right after the event: still drifting
    settled = [lvl for _, lvl in levels_after if lvl is not None]
    assert settled and abs(settled[0] - 620) <= 60  # once steady, close to the true room level


def test_top_of_a_breath_is_not_taken_as_the_room_level():
    # 22 Oct 2026: the program restarted in the middle of a breath (834 -> 1441 ppm) and the
    # rounded top of the curve passed as a "steady" room level of 1423 ppm
    curve = lambda t: first_order(t, -20, 0, 840, 1500, 8.0, 40.0)  # noqa: E731  (falling from the top)
    det = EventDetector()
    levels = []
    for t in range(0, 240):
        det.update(float(t), int(round(curve(t) + 15 * math.exp(-((t - 5) / 6.0) ** 2))))
        levels.append(det.armed)
    first = next((lvl for lvl in levels if lvl is not None), None)
    assert first is not None and first < 960, levels[:60]


# Real readings, one per second, 00:54:20-00:57:14 on 22 Oct 2026: a breath toward the
# sensor at about 00:55:00 (rise seen from 00:55:06). Independent analysis of the log gave
# room 812 ppm, peak 1121 ppm, rise 10-90 % 10.6 s, fall 90-10 % 65.9 s.
BREATH_2026_10_22 = [
    821, 822, 822, 822, 822, 823, 823, 821, 820, 821, 822, 822, 822, 822, 821, 821,
    820, 818, 818, 816, 815, 814, 814, 812, 811, 812, 812, 812, 812, 812, 812, 811,
    811, 811, 811, 811, 810, 809, 809, 808, 807, 807, 806, 805, 803, 802, 822, 840,
    866, 890, 922, 951, 976, 1000, 1024, 1047, 1064, 1080, 1095, 1107, 1114, 1121, 1120, 1118,
    1119, 1120, 1118, 1116, 1114, 1112, 1108, 1105, 1098, 1091, 1084, 1077, 1072, 1066, 1058, 1052,
    1043, 1036, 1029, 1023, 1015, 1008, 1000, 996, 991, 987, 980, 974, 968, 961, 958, 956,
    952, 949, 940, 933, 925, 916, 917, 917, 914, 912, 911, 911, 908, 905, 903, 900,
    898, 897, 894, 892, 890, 887, 884, 883, 881, 880, 878, 875, 872, 868, 867, 866,
    864, 864, 861, 858, 856, 854, 852, 849, 847, 846, 844, 843, 841, 839, 837, 835,
    833, 833, 832, 832, 831, 831, 830, 829, 829, 830, 829, 827, 826, 824, 824, 823,
    822, 821, 821, 821, 820, 820, 819, 818, 818, 817, 817, 817, 817, 816, 816,
]


def test_real_breath_from_22_oct():
    det = EventDetector(max_event_s=300)
    out = []
    for i, ppm in enumerate(BREATH_2026_10_22):
        r = det.update(float(i), ppm)
        if isinstance(r, dict):
            out.append(r)
    assert len(out) == 1, out
    s = out[0]
    assert 805 <= s["room"] <= 815 and s["peak"] == 1121
    # the board printed "rise n/a" that night: the 10 % point came before the event threshold
    assert s["rise_s"] is not None and abs(s["rise_s"] - 10.6) < 1.0, s
    assert abs(s["fall_s"] - 65.9) < 2.0, s


def test_event_that_never_returns_times_out():
    det = EventDetector(max_event_s=120)
    out = []
    for t in range(400):
        ppm = 600 if t < 50 else 1500
        r = det.update(float(t), ppm)
        if isinstance(r, dict):
            out.append(r)
    assert len(out) >= 1 and out[0]["returned"] is False


def test_two_breaths_are_two_events():
    def curve(t):
        a = first_order(t, 60, 66, 600, 4000, 6.0, 20.0)
        b = first_order(t, 300, 306, 600, 4000, 6.0, 20.0)
        return a + b - 600
    det, out = run(curve, 600)
    assert [s["n"] for s in out] == [1, 2]


# ---- dry run of code.py with fake CircuitPython modules and a simulated sensor ----

class _Clock:
    def __init__(self, start, stop):
        self.now = start
        self.stop = stop

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.now += s
        if self.now > self.stop:
            raise _Done()


class _Done(Exception):
    pass


def _dry_run(sensor_fn, start, stop):
    """Run firmware/code.py against `sensor_fn(t)` on a virtual clock; return the printed lines."""
    clock = _Clock(start=start, stop=stop)

    fake_time = types.ModuleType("time")
    fake_time.monotonic = clock.monotonic
    fake_time.sleep = clock.sleep
    fake_board = types.ModuleType("board")
    fake_board.LED = "LED"
    fake_dio = types.ModuleType("digitalio")

    class DigitalInOut:
        def __init__(self, pin):
            self.value = False
            self.direction = None

    fake_dio.DigitalInOut = DigitalInOut
    fake_dio.Direction = types.SimpleNamespace(OUTPUT="out")
    fake_mhz = types.ModuleType("mhz19c")
    fake_mhz.read_co2 = lambda orientation: sensor_fn(clock.now)
    fake_mhz.probe = lambda: ("normal", sensor_fn(clock.now))

    saved = {k: sys.modules.get(k) for k in ("time", "board", "digitalio", "mhz19c")}
    sys.modules.update(time=fake_time, board=fake_board, digitalio=fake_dio, mhz19c=fake_mhz)
    for k in ("indicator", "cr1"):          # re-import against this run's fake clock
        sys.modules.pop(k, None)
    lines = []
    import builtins
    real_print = builtins.print
    builtins.print = lambda *a, **k: lines.append(" ".join(str(x) for x in a))
    try:
        src = open(os.path.join(ROOT, "firmware", "code.py")).read()
        try:
            exec(compile(src, "code.py", "exec"), {"__name__": "__main__"})
        except _Done:
            pass
    finally:
        builtins.print = real_print
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        for k in ("indicator", "cr1"):
            sys.modules.pop(k, None)
    return lines


def test_code_py_dry_run():
    def sensor(t):
        if t < 60:
            return 500  # warm-up placeholder
        return min(TOP_PPM, int(first_order(t, 250, 258, 615, 9000, 7.0, 35.0) + 5 * math.sin(t)))

    text = "\n".join(_dry_run(sensor, 5.0, 420.0))
    assert "WARMING UP" in text
    assert "room level:" in text
    assert "--- CO2 event 1:" in text
    assert "TOP OF RANGE" in text
    assert "=== CO2 event 1:" in text
    assert ">>> CO2 PRESENT" in text and ">>> CO2 ABSENT" in text


def test_code_py_flags_a_reading_stuck_at_the_floor():
    # 22 Oct 2026: the sensor's brown HD wire touched the laptop's grounded case and the
    # reading sat at exactly 400 ppm until the wire was moved
    def sensor(t):
        if 200 <= t < 300:
            return 400
        return int(first_order(t, 450, 456, 830, 6000, 12.0, 40.0))

    lines = _dry_run(sensor, 100.0, 700.0)
    text = "\n".join(lines)
    assert text.count("SENSOR FAULT: reading stuck at 400 ppm") == 1
    assert any(ln.startswith("t=") and "FAULT" in ln for ln in lines)
    assert ">>> CO2 ABSENT: no exhaled CO2 yet <<<" in text   # recovered after the fault
    # the floor readings must not become the room level: the breath is measured against ~830
    assert "=== CO2 event 1: room 8" in text, text[-600:]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
