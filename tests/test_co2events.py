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


RING_FRAMES = []   # (time, bytes) written to the light ring during the last dry run
TONES = []         # (time, frequency or 0) sent to the speaker during the last dry run
BUTTON_DOWN = []   # (from, to) times when the simulated button is held down
TYPED = []         # (time, text) the simulated laptop sends to the board, e.g. (300.0, "ACK\n")
LINE_OFF = []      # (from, to) times when the simulated safety clip is open (tube off)


def _dry_run(sensor_fn, start, stop):
    """Run firmware/code.py against `sensor_fn(t)` on a virtual clock; return the printed lines."""
    clock = _Clock(start=start, stop=stop)
    del RING_FRAMES[:]
    del TONES[:]

    fake_time = types.ModuleType("time")
    fake_time.monotonic = clock.monotonic
    fake_time.sleep = clock.sleep
    fake_board = types.ModuleType("board")
    fake_board.LED = "LED"
    fake_board.GP16, fake_board.GP18, fake_board.GP20, fake_board.GP21 = "GP16", "GP18", "GP20", "GP21"
    fake_pwmio = types.ModuleType("pwmio")

    class PWMOut:
        def __init__(self, pin, frequency=500, duty_cycle=0, variable_frequency=False):
            self.frequency, self._duty = frequency, duty_cycle

        @property
        def duty_cycle(self):
            return self._duty

        @duty_cycle.setter
        def duty_cycle(self, v):
            self._duty = v
            TONES.append((clock.now, self.frequency if v else 0))

    fake_pwmio.PWMOut = PWMOut
    fake_npw = types.ModuleType("neopixel_write")
    fake_npw.neopixel_write = lambda pin, buf: RING_FRAMES.append((clock.now, bytes(buf)))
    fake_dio = types.ModuleType("digitalio")

    class DigitalInOut:
        def __init__(self, pin):
            self.pin = pin
            self._value = False
            self.direction = None
            self.pull = None

        @property
        def value(self):
            if self.pin == "GP20":   # button: pulled up, low while held down
                return not any(a <= clock.now < b for a, b in BUTTON_DOWN)
            if self.pin == "GP21":   # safety clip: pulled up, low while the loop is closed
                return any(a <= clock.now < b for a, b in LINE_OFF)
            return self._value

        @value.setter
        def value(self, v):
            self._value = v

    fake_dio.DigitalInOut = DigitalInOut
    fake_dio.Direction = types.SimpleNamespace(OUTPUT="out", INPUT="in")
    fake_dio.Pull = types.SimpleNamespace(UP="up", DOWN="down")
    fake_mhz = types.ModuleType("mhz19c")
    def fake_read(orientation, idle=None):
        ppm = sensor_fn(clock.now)
        if ppm is None:                    # no answer: the real driver waits 0.5 s, calling idle
            for _ in range(25):
                clock.now += 0.02
                if idle is not None:
                    idle(clock.now)
        return ppm

    fake_mhz.read_co2 = fake_read
    fake_mhz.probe = lambda idle=None: ("normal", fake_read("normal", idle))

    # the laptop's side of the USB link: text in TYPED arrives at its time, one character at a time
    pending = [c for when, text in sorted(TYPED) for c in [(when, ch) for ch in text]]

    class _Runtime:
        @property
        def serial_bytes_available(self):
            return sum(1 for when, _ in pending if when <= clock.now)

    class _Stdin:
        def read(self, n=1):
            when, ch = pending.pop(0)
            return ch

    fake_supervisor = types.ModuleType("supervisor")
    fake_supervisor.runtime = _Runtime()
    real_stdin = sys.stdin
    sys.stdin = _Stdin()

    saved = {k: sys.modules.get(k) for k in ("time", "board", "digitalio", "mhz19c", "neopixel_write", "pwmio",
                                              "supervisor")}
    sys.modules.update(time=fake_time, board=fake_board, digitalio=fake_dio, mhz19c=fake_mhz,
                       neopixel_write=fake_npw, pwmio=fake_pwmio, supervisor=fake_supervisor)
    for k in ("indicator", "cr1", "annunciator", "lineclip"):   # re-import against this run's fake clock
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
        sys.stdin = real_stdin
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        for k in ("indicator", "cr1", "annunciator"):
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
    # reading sat at exactly 400 ppm until the wire was moved. After the fault the monitor
    # re-warms for 3 minutes (cr1.RECOVERY_S), so the test breath comes after that.
    def sensor(t):
        if 200 <= t < 300:
            return 400
        return int(first_order(t, 550, 556, 830, 6000, 12.0, 40.0))

    lines = _dry_run(sensor, 100.0, 800.0)
    text = "\n".join(lines)
    assert text.count("SENSOR FAULT: reading stuck at 400 ppm") == 1
    assert any(ln.startswith("t=") and "FAULT" in ln for ln in lines)
    assert ">>> WARMING UP: sensor back after a fault; trusted again in 180 s <<<" in text
    assert ">>> CO2 ABSENT: no exhaled CO2 yet <<<" in text   # trusted again after the re-warm
    # the floor readings must not become the room level: the breath is measured against ~830
    assert "=== CO2 event 1: room 8" in text, text[-600:]


def _ring_kinds():
    """The light ring's frames as a list of what they showed: a colour name, 'spin' or 'off'."""
    names = {(0, 20, 0): "green", (20, 8, 0): "amber", (20, 0, 0): "red", (0, 16, 20): "cyan"}
    kinds = []
    for _, buf in RING_FRAMES:
        px = [tuple(buf[i:i + 3]) for i in range(0, len(buf), 3)]
        lit = [(r, g, b) for g, r, b in px if (g, r, b) != (0, 0, 0)]
        if not lit:
            k = "off"
        elif len(lit) == 1:
            k = "spin"
        else:
            assert len(lit) == 16 and len(set(lit)) == 1, px
            k = names.get(lit[0], str(lit[0]))
        if not kinds or kinds[-1] != k:
            kinds.append(k)
    return kinds


def test_alarm_display_lamp_test_standby_normal_then_critical():
    # power-up lamp test, STANDBY while warming up and before a breath, a breath (NORMAL, green),
    # then the breath stops and the gas is flushed: CRITICAL, red flashing, with 10-pulse bursts
    def sensor(t):
        if t < 75:
            return 500
        return int(first_order(t, 200, 260, 830, 6000, 12.0, 40.0))
    lines = _dry_run(sensor, 5.0, 330.0)
    kinds = _ring_kinds()
    assert kinds[:5] == ["green", "amber", "red", "cyan", "spin"], kinds
    assert "green" in kinds[5:] and kinds[-2:] in (["red", "off"], ["off", "red"]), kinds
    text = "\n".join(lines)
    assert ">>> ALARM NORMAL: exhaled CO2 present <<<" in text
    assert ">>> ALARM CRITICAL: CO2 lost:" in text
    bursts = [t for t, f in TONES if f == 2400]
    assert len(bursts) >= 10, TONES                        # a 10-pulse burst at least


def test_sensor_fault_from_green_is_cyan_with_a_chirp():
    # breathing (CO2 held at 2,000 ppm), then the data wire pulled for 15 s at 260 s
    def sensor(t):
        if t < 75:
            return 500
        if 260 <= t < 275:
            return None
        return 830 if t < 200 else min(2000, 830 + 60 * int(t - 200))
    lines = _dry_run(sensor, 5.0, 290.0)
    text = "\n".join(lines)
    assert ">>> ALARM NORMAL: exhaled CO2 present <<<" in text
    assert ">>> ALARM TECHNICAL: sensor fault: no answer from the sensor <<<" in text
    assert "ALARM CRITICAL" not in text
    assert "cyan" in _ring_kinds()[5:]
    assert any(260 <= t < 262 and f == 3000 for t, f in TONES), TONES     # the chirp


def test_red_keeps_flashing_and_beeping_while_the_sensor_is_silent():
    # 25 Oct: a data wire pulled during a CRITICAL alarm froze the ring on steady red, because the
    # program sat waiting for the sensor. The alarm must stay CRITICAL (a fault never hides it),
    # and keep flashing and beeping.
    def sensor(t):
        if t < 75:
            return 500
        if 335 <= t < 365:
            return None
        return int(first_order(t, 200, 260, 830, 6000, 12.0, 40.0))
    lines = _dry_run(sensor, 5.0, 380.0)
    text = "\n".join(lines)
    assert ">>> ALARM CRITICAL stays; also an equipment problem" in text
    during = [buf for t, buf in RING_FRAMES if 337 <= t < 363]
    assert len(set(during)) == 2 and len(during) >= 40, len(during)   # red / off, 2 flashes a second
    assert sum(1 for t, f in TONES if 337 <= t < 363 and f == 2400) >= 10   # bursts carry on


def test_ring_alternates_red_and_green_while_co2_is_back():
    import importlib
    added = "digitalio" not in sys.modules
    if added:                                   # indicator.py imports it; not needed for frames
        sys.modules["digitalio"] = types.SimpleNamespace()
    try:
        sys.modules.pop("indicator", None)
        ind = importlib.import_module("indicator")
        red, green = ind.ring_frame("LAMP RED", 0.0), ind.ring_frame("LAMP GREEN", 0.0)
        frames = [bytes(ind.ring_frame("CRITICAL BACK", k * 0.25)) for k in range(8)]
        assert frames[:4] == [bytes(red)] * 4 and frames[4:] == [bytes(green)] * 4
    finally:
        sys.modules.pop("indicator", None)
        if added:
            sys.modules.pop("digitalio", None)


def test_code_py_a_cell_stuck_at_the_top_is_cyan_not_green():
    # 1 Nov, 19:25-19:31: firm breaths filled the sealed cell, the reading sat at 5,000 ppm for 6
    # minutes with the tube on the table, and the ring stayed green. Now: cyan after 30 s at the top,
    # and red at once when the reading finally falls.
    def sensor(t):
        if t < 75:
            return 500
        if t < 150:
            return 1500
        if t < 160:
            return 1500 + 400 * int(t - 150)
        if t < 500:
            return 5000
        return max(1500, int(5000 - 30 * (t - 500)))
    lines = _dry_run(sensor, 5.0, 560.0)
    text = "\n".join(lines)
    tech = [ln for ln in lines if ln.startswith("t=") and "TECHNICAL" in ln]
    assert tech, text[-800:]
    first = int(tech[0][2:7])
    assert 185 <= first <= 195, first                     # about 30 s after the reading hit the top
    assert ">>> ALARM TECHNICAL: reading at the top of the scale (5,000 ppm) for 30 s" in text
    assert not [ln for ln in lines if ln.startswith("t=") and 200 <= int(ln[2:7]) < 500 and "NORMAL" in ln]
    crit = [ln for ln in lines if ln.startswith(">>> ALARM CRITICAL: CO2 lost")]
    assert crit, text[-800:]


def test_a_reading_pinned_at_the_top_is_not_a_room_level():
    # 25 Oct: the board printed "room level: 5000 ppm ... ready for a test" with the cell full
    det = EventDetector()
    for t in range(60):
        det.update(float(t), TOP_PPM)
    assert det.room_level() is None and det.armed is None


def _json_lines(lines):
    import json
    return [json.loads(ln) for ln in lines if ln.startswith("{")]


def test_every_reading_also_goes_out_as_one_json_line():
    # IF-6: the laptop service reads one JSON object per line; the human line stays as it was
    def sensor(t):
        if t < 75:
            return 500
        if 300 <= t < 304:
            return None                                    # a short sensor drop-out
        return int(first_order(t, 200, 260, 830, 6000, 12.0, 40.0))
    lines = _dry_run(sensor, 5.0, 330.0)
    js = _json_lines(lines)
    readings = [ln for ln in lines if ln.startswith("t=")]
    assert len(js) == len(readings) and len(js) > 250
    keys = {"v", "t", "ppm", "cr1", "cr1_why", "alarm", "show", "why", "acked", "latched", "press", "hold",
            "dash_ack", "rr", "rr_why", "advisory", "line"}
    assert all(set(j) == keys and j["v"] == "0.6" for j in js)
    assert all(j["line"] is True and j["advisory"] is None for j in js)   # clip closed, no fall
    for j, ln in zip(js, readings):                         # the two lines say the same thing
        assert ln.startswith("t=%5d s" % j["t"])
        assert (j["ppm"] is None) == ("no answer" in ln)
        if j["ppm"] is not None:
            assert "CO2 %5d ppm" % j["ppm"] in ln
        assert j["cr1"] in ln and j["show"] in ln
    assert any(j["ppm"] is None and j["cr1"] == "FAULT" for j in js)
    assert js[-1]["alarm"] == "CRITICAL" and js[-1]["show"] == "CRITICAL" and not js[-1]["acked"]


def test_ack_from_the_dashboard_acknowledges_like_the_button():
    def sensor(t):
        if t < 75:
            return 500
        return int(first_order(t, 200, 260, 830, 6000, 12.0, 40.0))
    TYPED[:] = [(320.0, "ACK\n")]
    try:
        lines = _dry_run(sensor, 5.0, 340.0)
    finally:
        TYPED[:] = []
    text = "\n".join(lines)
    assert ">>> ACK from the dashboard <<<" in text and ">>> BUTTON pressed <<<" not in text
    assert ">>> ALARM ACKNOWLEDGED: sound off for 120 s <<<" in text
    js = _json_lines(lines)
    acked_at = [j["t"] for j in js if j["dash_ack"]]
    assert len(acked_at) == 1 and 320 <= acked_at[0] <= 322
    assert all(j["acked"] and j["show"] == "CRITICAL ACK" for j in js if j["t"] > acked_at[0])
    assert all(j["press"] == 0 for j in js)


def test_start_up_chirp_and_button_beep():
    BUTTON_DOWN[:] = [(150.0, 150.3), (150.31, 150.32)]      # one press, plus a contact bounce
    try:
        lines = _dry_run(lambda t: 830 if t >= 75 else 500, 5.0, 200.0)
    finally:
        BUTTON_DOWN[:] = []
    assert [f for _, f in TONES[:3]] == [1800, 2600, 0], TONES[:4]     # chirp at start-up
    assert sum(1 for ln in lines if ">>> BUTTON pressed <<<" in ln) == 1
    assert any(150.0 <= t <= 151.5 and f == 2000 for t, f in TONES), TONES
    assert TONES[-1][1] == 0                                          # silent again


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
