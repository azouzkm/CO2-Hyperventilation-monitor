"""Laptop-side tests for firmware/lib/cr1.py (CR-1: exhaled CO2 present or absent).

Most tests replay the real readings logged on 22 Oct 2026 (data/2026-10-22_session2_readings.csv,
open-air bench, before the flow-cell existed). They check the draft acceptance numbers:
ER-1, present within 3 breaths; ER-2, absent within 30 s of the last breath.

Run from the repository root:   python -m pytest tests/
(or without pytest:              python tests/test_cr1.py)
"""
import csv
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

import cr1  # noqa: E402
from cr1 import PresenceMonitor, PRESENT, ABSENT, FAULT, WARMING_UP  # noqa: E402

DATA = os.path.join(ROOT, "data", "2026-10-22_session2_readings.csv")


def secs(clock):
    h, m, s = (int(x) for x in clock.split(":"))
    return h * 3600 + m * 60 + s


def replay(start, end):
    """Feed the 22 Oct readings between two Mac-clock times; return [(mac_seconds, state, reason)]."""
    mon = PresenceMonitor()
    changes = []
    with open(DATA) as f:
        for row in csv.DictReader(f):
            if not (start <= row["mac_time"] <= end):
                continue
            if mon.update(float(row["seconds_since_power_up"]), int(row["co2_ppm"])):
                changes.append((secs(row["mac_time"]), mon.state, mon.reason))
    return changes


def first(changes, state, after):
    return next((t for t, s, _ in changes if s == state and t >= after), None)


def test_rhythmic_run_meets_er1_and_er2():
    # 15 breaths/min from 01:10:04 for 60 s: breaths at +0, +4, +8, +12 s ...
    start, stop = secs("01:10:04"), secs("01:11:04")
    ch = replay("01:09:00", "01:15:00")
    present = first(ch, PRESENT, start)
    assert present is not None and present - start < 12, ch   # before breath 4: within 3 breaths
    absent = first(ch, ABSENT, stop)
    assert absent is not None and absent - stop <= 30, ch      # ER-2
    assert sum(1 for t, s, _ in ch if start <= t < stop and s == ABSENT) == 0   # no drop-out while breathing


def test_single_breaths_are_caught_quickly_and_clear():
    for breath, window in (("00:40:10", ("00:39:20", "00:43:00")), ("00:55:00", ("00:54:20", "00:58:00"))):
        ch = replay(*window)
        t0 = secs(breath)
        present = first(ch, PRESENT, t0)
        assert present is not None and present - t0 <= 12, ch
        assert first(ch, ABSENT, present) is not None, ch
        assert len([c for c in ch if c[0] >= t0]) <= 2, ch     # no flip-flopping


def test_both_sensor_faults_are_caught_at_their_first_impossible_reading():
    # 22 Oct, fault 1: 1,784 -> 778 ppm in one second (00:25:57); fault 2: 846 -> 400 (01:31:46).
    # Both then sat at 400 ppm, which is also reported, with what to check.
    ch = replay("00:25:00", "01:45:59")
    starts = [t for t, s, r in ch if s == FAULT and "jumped" in r]
    assert starts[0] == secs("00:25:57") and secs("01:31:46") in starts, ch
    for t0, t1 in (("00:25:57", "00:29:22"), ("01:31:46", "01:34:26")):
        reasons = [r for t, s, r in ch if s == FAULT and secs(t0) <= t <= secs(t1)]
        assert any("stuck at 400" in r for r in reasons), ch
    outside = [t for t, s, _ in ch if s == FAULT and not (secs("00:25:57") <= t <= secs("00:29:22")
                                                          or secs("01:31:46") <= t <= secs("01:34:26"))]
    assert not outside, ch                                    # no false faults the rest of the night


def test_real_breaths_are_never_taken_for_jumps():
    # the fastest real changes on the bench: 654 ppm/s up (a breath straight into the flow cell,
    # 25 Oct) and 163 ppm/s down; the limits keep a margin of about 2x over both
    assert cr1.RISE_JUMP_PPM >= 1.8 * 654 and cr1.FALL_JUMP_PPM >= 2 * 163
    mon = PresenceMonitor()
    rise = [830] * 100 + [830 + 654 * k for k in range(1, 7)] + [5000] * 20 + [5000 - 163 * k for k in range(1, 26)]
    for t, p in enumerate(rise):
        mon.update(float(t), p)
        assert mon.state != FAULT, (t, p, mon.reason)


def test_no_false_present_while_the_sensor_recovers_from_a_fault():
    # 22 Oct, 01:34:27: the reading came back from the second stuck-at-400 fault, climbed and
    # overshot to 2,265 ppm. Without the recovery wait that read as PRESENT for 90 s.
    ch = replay("01:25:00", "01:45:59")
    back = first(ch, WARMING_UP, secs("01:32:29"))
    assert back is not None and abs(back - secs("01:34:27")) <= 2, ch
    trusted = first(ch, ABSENT, back)
    assert trusted is not None and trusted - back >= cr1.RECOVERY_S, ch
    assert first(ch, PRESENT, secs("01:32:29")) is None or first(ch, PRESENT, secs("01:32:29")) > trusted


def test_open_air_cannot_tell_the_operator_from_a_breath():
    # Documented limitation, not a goal: without the flow-cell, breathing near the bench reads as
    # exhaled CO2. The cap must shield the sensor; this test records the open-air behaviour.
    ch = replay("01:00:00", "01:05:59")
    assert any(s == PRESENT for _, s, _ in ch)


# ---- synthetic cases -----------------------------------------------------------------------

def feed(mon, ppm_at, t0, t1):
    out = []
    for t in range(t0, t1):
        if mon.update(float(t), ppm_at(t)):
            out.append((t, mon.state, mon.reason))
    return out


def test_warm_up_then_absent_in_room_air():
    mon = PresenceMonitor()
    assert mon.state == WARMING_UP
    ch = feed(mon, lambda t: 500 if t < 75 else 820, 0, 200)
    assert [(t, s) for t, s, _ in ch] == [(75, ABSENT)], ch


def test_starting_while_gas_is_already_at_the_top_reads_present():
    mon = PresenceMonitor()
    ch = feed(mon, lambda t: 500 if t < 75 else 5000, 0, 120)
    assert ch[-1][1] == PRESENT


def test_saturated_breathing_then_stop_reads_absent_within_30_s():
    def ppm(t):  # room 800, breathing from 100 s (sensor pinned at 5000), stops at 200 s
        if t < 100:
            return 800
        if t < 200:
            return min(5000, int(800 + 9000 * (1 - math.exp(-(t - 100) / 8.0))))
        return int(800 + 4200 * math.exp(-(t - 200) / 40.0))
    mon = PresenceMonitor()
    ch = feed(mon, ppm, 80, 400)
    assert first(ch, PRESENT, 100) - 100 <= 3
    assert first(ch, ABSENT, 200) - 200 <= 30


def test_slow_fall_stays_present_for_cr4_to_judge():
    # hypoventilation-like: 3,000 ppm sliding to 1,800 over 5 minutes is still exhaled CO2
    def ppm(t):
        if t < 100:
            return 800
        if t < 130:
            return min(3000, 800 + 400 * (t - 99))      # a real rise: about 400 ppm/s at most
        return int(3000 - 4 * (t - 130))
    mon = PresenceMonitor()
    ch = feed(mon, ppm, 80, 430)
    assert [s for _, s, _ in ch] == [ABSENT, PRESENT], ch


def breathing_with_ripple(mon, t0, seconds, rate, swing, level=2000, room=900):
    """Feed the level rising from room air to `level`, with a +/-swing ripple at `rate` breaths/min
    (as seen once air moves through the cell). Returns the CR-1 states called, and the end time."""
    calls = []
    for k in range(seconds):
        t = t0 + k
        rise = level - (level - room) * math.exp(-k / 8.0)
        ppm = int(rise + swing * math.sin(2 * math.pi * rate * k / 60.0) * min(1.0, k / 20.0))
        if mon.update(float(t), ppm):
            calls.append((t, mon.state))
    return calls, t0 + seconds


def test_the_swing_of_each_breath_is_not_an_absence():
    for rate, swing in ((4, 150), (6, 120), (10, 100), (15, 60)):
        mon = PresenceMonitor(warmup_s=0)
        feed(mon, lambda t: 900, 0, 60)
        calls, end = breathing_with_ripple(mon, 60, 300, rate, swing)
        assert calls and calls[0][1] == PRESENT and len(calls) == 1, (rate, calls)
        # then the line comes off: the reading falls back to room air, and ABSENT follows in time
        last = 2000
        for k in range(60):
            if mon.update(float(end + k), int(900 + (last - 900) * math.exp(-k / 20.0))):
                break
        assert mon.state == ABSENT and k <= 30, (rate, k, mon.reason)


def test_no_answer_is_a_fault_then_a_re_warm_then_absent():
    mon = PresenceMonitor()
    seq = [500] * 80 + [820] * 20 + [None] * 5 + [820] * (cr1.RECOVERY_S + 10)
    states = []
    for t, p in enumerate(seq):
        mon.update(float(t), p)
        states.append(mon.state)
    assert states[101] == FAULT and states[105] == WARMING_UP
    assert states[105 + cr1.RECOVERY_S - 1] == WARMING_UP and states[-1] == ABSENT
    assert cr1.PRESENT_RISE == 100   # the threshold the 22 Oct replays were checked with


def test_breathing_after_a_fault_is_called_once_the_re_warm_ends():
    mon = PresenceMonitor()
    seq = [820] * 100 + [None] * 3 + [5000] * (cr1.RECOVERY_S + 5)
    for t, p in enumerate(seq):
        mon.update(float(t), p)
    assert mon.state == PRESENT


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
