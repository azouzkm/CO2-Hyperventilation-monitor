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


def test_stuck_at_400_is_a_fault_both_times_it_happened():
    ch = replay("00:25:00", "01:45:59")
    faults = [t for t, s, _ in ch if s == FAULT]
    assert len(faults) == 2, ch
    assert abs(faults[0] - secs("00:26:32")) <= 2 and abs(faults[1] - secs("01:32:29")) <= 2
    assert all("stuck at 400" in r for _, s, r in ch if s == FAULT)


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
            return 3000
        return int(3000 - 4 * (t - 130))
    mon = PresenceMonitor()
    ch = feed(mon, ppm, 80, 430)
    assert [s for _, s, _ in ch] == [ABSENT, PRESENT], ch


def test_no_answer_is_a_fault_and_recovers():
    mon = PresenceMonitor()
    seq = [500] * 80 + [820] * 20 + [None] * 5 + [820] * 10
    states = []
    for t, p in enumerate(seq):
        mon.update(float(t), p)
        states.append(mon.state)
    assert states[101] == FAULT and states[-1] == ABSENT
    assert cr1.PRESENT_RISE == 100   # the threshold the 22 Oct replays were checked with


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
