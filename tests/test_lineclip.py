"""Laptop-side tests for the safety clip on the sampling line (CR-3): firmware/lib/lineclip.py,
its place in the alarm (lib/alarm.py) and in the board program (code.py, dry run).

Run from the repository root:   python -m pytest tests/
(or without pytest:              python tests/test_lineclip.py)
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import alarm  # noqa: E402
from alarm import AlarmManager, NORMAL, CRITICAL, TECHNICAL  # noqa: E402
from lineclip import LineClip  # noqa: E402
import test_co2events as dry  # noqa: E402


def test_the_clip_needs_the_change_to_hold_before_it_counts():
    c = LineClip()
    assert c.connected
    c.sample(0.00, True)                  # open for 0.1 s: a wiggle
    c.sample(0.10, False)
    c.sample(0.50, False)
    assert c.connected and not c.take_change()
    c.sample(1.00, True)                  # open and held
    c.sample(1.20, True)
    assert c.connected
    c.sample(1.31, True)
    assert not c.connected and c.take_change() and not c.take_change()
    c.sample(2.0, False)
    c.sample(2.4, False)
    assert c.connected and c.take_change()


def run(steps):
    """steps: [(t, co2_state, ppm, line_ok)] -> [(t, display, actions)]"""
    a = AlarmManager()
    out = []
    for t, co2, ppm, ok in steps:
        acts = a.update(t, co2, "test", ppm, line_ok=ok)
        out.append((t, a.display(), acts))
    return out


def seq(*parts):
    out = []
    for t0, t1, co2, ppm, ok in parts:
        out += [(float(t), co2, ppm, ok) for t in range(t0, t1)]
    return out


def test_tube_off_is_technical_never_critical_even_when_co2_goes():
    log = run(seq((0, 30, "PRESENT", 2000, True), (30, 47, "PRESENT", 1800, False),
                  (47, 120, "ABSENT", 900, False)))
    assert all(d == TECHNICAL for t, d, _ in log if t > 30)
    assert any(a == ("banner", "ALARM TECHNICAL: LINE OFF: sampling line disconnected (safety clip open)")
               for a in log[30][2])
    assert not [a for _, _, acts in log for a in acts if a == ("sound", "critical")]


def test_tube_back_on_and_breathing_is_normal():
    log = run(seq((0, 30, "PRESENT", 2000, True), (30, 60, "ABSENT", 900, False),
                  (60, 70, "ABSENT", 900, True), (70, 90, "PRESENT", 2000, True)))
    assert log[-1][1] == NORMAL
    assert not [a for _, _, acts in log for a in acts if a == ("sound", "critical")]


def test_tube_back_on_but_no_breath_is_critical_after_30_s():
    log = run(seq((0, 30, "PRESENT", 2000, True), (30, 60, "ABSENT", 900, False),
                  (60, 120, "ABSENT", 900, True)))
    assert all(d == TECHNICAL for t, d, _ in log if 60 <= t < 60 + alarm.BREATH_WAIT_S)
    assert log[60 + alarm.BREATH_WAIT_S][1] == CRITICAL


def test_a_critical_alarm_already_on_stays_when_the_tube_comes_off():
    log = run(seq((0, 30, "PRESENT", 2000, True), (30, 40, "ABSENT", 900, True),
                  (40, 60, "ABSENT", 900, False)))
    assert all(d == CRITICAL for t, d, _ in log if t >= 30)
    assert any(a[0] == "banner" and a[1].startswith("ALARM CRITICAL stays; also an equipment problem: LINE OFF")
               for a in log[40][2])


def test_code_py_pulling_the_tube_shows_line_off_in_cyan():
    def sensor(t):
        if t < 75:
            return 500
        if t < 200:
            return 830
        if t < 300:
            return min(2000, 830 + 60 * int(t - 200))
        return int(830 + 1170 * math.exp(-(t - 300) / 20.0))   # tube off at 300 s: the CO2 goes
    dry.LINE_OFF[:] = [(300.0, 400.0)]
    try:
        lines = dry._dry_run(sensor, 5.0, 380.0)
    finally:
        dry.LINE_OFF[:] = []
    text = "\n".join(lines)
    assert ">>> SAMPLING LINE OFF (safety clip open) <<<" in text
    assert ">>> ALARM TECHNICAL: LINE OFF: sampling line disconnected (safety clip open) <<<" in text
    assert "ALARM CRITICAL" not in text
    assert any("LINE OFF" in ln for ln in lines if ln.startswith("t="))
    assert "cyan" in dry._ring_kinds()[5:]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
