"""Laptop-side tests for firmware/lib/cr4.py (CR-4: breathing rate from the CO2 signal, and the
advisory on a sustained fall).

Two kinds of evidence:
  - real bench readings: the 22 Oct paced run (15 breaths/min, open air) must read 15/min, and
    nothing else logged on 22 and 25 Oct (room air, an operator nearby, breaths into the sealed
    flow-cell, flushes, sensor faults) may ever show a rate or an advisory;
  - simulated breathing: gas that alternates breath by breath, seen through a sensor that lags by
    two first-order delays (cell and sensor, 2 to 8 s), with noise and the 400-5,000 ppm scale.
    The bench has no paced run with a pump yet, so the simulation stands in for the slowing and
    falling cases until tools/rate_run.sh has been run on the rig.

Run from the repository root:   python -m pytest tests/
(or without pytest:              python tests/test_cr4.py)
"""
import csv
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

import cr4  # noqa: E402
from cr4 import RateMonitor, BreathingRate, FallWatch, PRESENT, ABSENT  # noqa: E402
from cr1 import PresenceMonitor  # noqa: E402

DATA = os.path.join(ROOT, "data", "2026-10-22_session2_readings.csv")
RAW = os.path.join(ROOT, "data", "raw")
LINE = re.compile(r"t=\s*(\d+) s\s+CO2\s+(\d+) ppm")


# ---------------------------------------------------------------- simulated breathing
def breathing(rate, seconds, room=900, excess=1200, swing=300, tau_cell=3.0, tau_sensor=5.0,
              noise=1.0, seed=1, jitter=0.05, ie=0.4, top=5000, dt=0.05):
    """One reading a second: gas at the inlet alternates between breath (room + excess + swing)
    and the gas between breaths, through two first-order lags. rate, excess and swing may be
    functions of time. jitter: each breath's length varies by up to this fraction."""
    rnd = random.Random(seed)
    rate_at = rate if callable(rate) else (lambda t: rate)
    excess_at = excess if callable(excess) else (lambda t: excess)
    swing_at = swing if callable(swing) else (lambda t: swing)
    c1 = c2 = room + excess_at(0)
    t, next_breath, out_end, exhaling, next_sample = 0.0, 0.0, 0.0, False, 0.0
    out = []
    while t < seconds:
        if t >= next_breath:
            period = 60.0 / rate_at(t) * (1 + rnd.uniform(-jitter, jitter))
            exhaling, out_end, next_breath = True, t + ie * period, t + period
        if exhaling and t >= out_end:
            exhaling = False
        sw = swing_at(t)
        gas = room + excess_at(t) + (sw if exhaling else -sw * ie / (1 - ie))
        c1 += (gas - c1) * dt / tau_cell
        c2 += (c1 - c2) * dt / tau_sensor
        if t >= next_sample:
            out.append((round(t, 3), max(400, min(top, int(round(c2 + rnd.gauss(0, noise)))))))
            next_sample += 1.0
        t += dt
    return out


def room_air(monitor, seconds=120, level=900, noise=1.0, seed=7):
    """Room air before breathing starts, as the board sees it (CR-1 says ABSENT): this is where
    the rig's own noise is learnt."""
    rnd = random.Random(seed)
    for t in range(-seconds, 0):
        monitor.update(float(t), int(round(level + rnd.gauss(0, noise))), ABSENT)


def run(readings, room_first=True):
    """[(t, rate, advisory)] for readings fed with CR-1 saying PRESENT throughout."""
    rm = RateMonitor()
    if room_first:
        room_air(rm)
    out = []
    for t, ppm in readings:
        rm.update(t, ppm, PRESENT)
        out.append((t, rm.rate, rm.advisory))
    return out


def rates_after(trace, t0):
    return [r for t, r, _ in trace if t >= t0 and r is not None]


# ---------------------------------------------------------------- real bench readings
def replay_22_oct():
    """The whole 22 Oct session through CR-1 and CR-4: [(mac_seconds, label, rate, advisory)]."""
    mon, rm, out = PresenceMonitor(), RateMonitor(), []
    with open(DATA) as f:
        for row in csv.DictReader(f):
            t, ppm = float(row["seconds_since_power_up"]), int(row["co2_ppm"])
            mon.update(t, ppm)
            rm.update(t, ppm, mon.state)
            h, m, s = (int(x) for x in row["mac_time"].split(":"))
            out.append((h * 3600 + m * 60 + s, row["label"], rm.rate, rm.advisory))
    return out


def replay_log(name):
    """One raw log of 25 Oct through CR-1 and CR-4: [(t, ppm, CR-1 state, rate, advisory)]."""
    mon, rm, out = PresenceMonitor(), RateMonitor(), []
    with open(os.path.join(RAW, name), encoding="utf-8", errors="replace") as f:
        for line in f:
            m = LINE.search(line)
            if not m:
                continue
            t, ppm = float(m.group(1)), int(m.group(2))
            mon.update(t, ppm)
            rm.update(t, ppm, mon.state)
            out.append((t, ppm, mon.state, rm.rate, rm.advisory))
    return out


def test_22_oct_paced_run_reads_15_per_minute_and_nothing_else_does():
    rows = replay_22_oct()
    start = next(t for t, label, _, _ in rows if label == "rhythmic_run_1_breathing")   # 01:10:04
    shown = [(t - start, r) for t, _, r, _ in rows if r is not None]
    assert shown, "no rate shown during the paced run"
    assert all(20 <= dt <= 75 for dt, _ in shown), shown          # only during the run (and its end)
    assert all(14.5 <= r <= 16.0 for _, r in shown), shown        # paced at 15/min
    assert len(shown) >= 30, shown                                 # shown for most of the run
    assert not any(a for _, _, _, a in rows)                       # no advisory all night


def test_25_oct_flow_cell_logs_never_show_a_rate_or_an_advisory():
    names = sorted(n for n in os.listdir(RAW) if n.startswith(("co2_2026-10-25", "co2_2026-10-26")))
    assert len(names) >= 3
    present = 0
    for name in names:
        rows = replay_log(name)
        present += sum(1 for r in rows if r[2] == "PRESENT")
        assert not [r for r in rows if r[3] is not None], name     # breaths into a sealed cell: no rhythm
        assert not [r for r in rows if r[4]], name
    assert present > 1000                                          # and CO2 was present for a long time


# ---------------------------------------------------------------- the rate itself
def test_steady_breathing_reads_the_right_rate():
    for (tau_cell, tau_sensor), rates in (((2, 3), (6, 10, 15, 20)), ((4, 8), (6, 10, 15))):
        for rate in rates:
            trace = run(breathing(rate, 200, tau_cell=tau_cell, tau_sensor=tau_sensor, seed=rate))
            got = rates_after(trace, 70)
            assert len(got) >= 0.8 * 130, (rate, tau_cell, len(got))       # shown nearly all the time
            assert all(abs(r - rate) <= 0.6 for r in got), (rate, min(got), max(got))


def test_a_slower_sensor_counts_only_slower_breathing_and_is_never_wrong():
    # the faster the breathing, the smaller the wobble a slow sensor passes on: the highest rate
    # this hardware can count is a property to measure (ER-7), not to guess
    shown = {}
    for rate in (6, 15):
        trace = run(breathing(rate, 200, swing=100, tau_cell=4, tau_sensor=8, seed=rate))
        got = rates_after(trace, 70)
        assert all(abs(r - rate) <= 0.6 for r in got), (rate, got)
        shown[rate] = len(got)
    assert shown[6] >= 100 and shown[15] == 0, shown


def test_irregular_breathing_is_never_read_too_low():
    # 25 % breath-to-breath variation: the rate wanders, but never shows below 80 % of the real
    # one (a falsely low rate is the error that would raise a false advisory)
    for rate in (10, 15, 20):
        for seed in (1, 2):
            trace = run(breathing(rate, 240, jitter=0.25, seed=seed * 100 + rate))
            got = rates_after(trace, 70)
            assert got, rate
            assert min(got) >= 0.8 * rate and max(got) <= 1.2 * rate, (rate, min(got), max(got))


def test_too_small_a_wobble_is_withheld_not_guessed():
    # a slow sensor and a small swing: at 15/min the wobble is lost in the noise
    trace = run(breathing(15, 200, swing=30, tau_cell=4, tau_sensor=8, seed=3))
    assert rates_after(trace, 0) == []


def test_room_air_noise_and_drift_never_show_a_rate():
    for noise in (1.0, 2.0, 3.0):
        rnd = random.Random(int(noise * 10))
        br = BreathingRate()
        level = 900.0
        for t in range(-120, 1200):
            level += rnd.gauss(0, 0.3)
            ppm = int(round(level + rnd.gauss(0, noise)))
            br.update(float(t), ppm, ABSENT if t < 0 else PRESENT)
            assert br.rate is None, (noise, t)


def test_slower_than_5_per_minute_is_not_counted():
    br = BreathingRate()
    reasons = set()
    for t, ppm in breathing(4, 240, swing=600, seed=4):
        br.update(t, ppm, PRESENT)
        assert br.rate is None
        reasons.add(br.why)
    assert any("slower than 5/min" in r for r in reasons), reasons


def test_no_rate_at_the_top_of_the_scale():
    # undiluted breath: the sensor sits at 5,000 ppm, the ripple is cut off
    br = BreathingRate()
    for t, ppm in breathing(12, 200, excess=20000, swing=15000, seed=5):
        br.update(t, ppm, PRESENT)
        assert br.rate is None
    assert "top of the scale" in br.why


def test_no_rate_while_co2_is_absent_and_a_gap_starts_the_window_again():
    br = BreathingRate()
    readings = breathing(15, 200, seed=6)
    for t, ppm in readings[:150]:
        br.update(t, ppm, PRESENT)
    assert br.rate is not None
    br.update(151.0, readings[151][1], ABSENT)
    assert br.rate is None and br.why == "no exhaled CO2"
    br.update(160.0, readings[160][1], PRESENT)                   # 9 s later: a gap
    assert br.rate is None and len(br.x) == 1


# ---------------------------------------------------------------- the advisory (sustained fall)
def test_steady_breathing_never_raises_an_advisory():
    for rate in (10, 15, 20):
        for jitter in (0.05, 0.25):
            trace = run(breathing(rate, 600, jitter=jitter, seed=rate + int(jitter * 100)))
            assert not [t for t, _, a in trace if a], (rate, jitter)


def test_slowing_to_6_per_minute_raises_an_advisory_and_recovery_clears_it():
    rate = lambda t: 15 if t < 240 or t >= 480 else 6
    trace = run(breathing(rate, 720, seed=8))
    on = [t for t, _, a in trace if a]
    assert on and 240 + 45 <= on[0] <= 240 + 90, on[:1]          # the advisory follows the slowing ...
    advisory = next(a for _, _, a in trace if a)
    assert "below 8/min" in advisory, advisory
    off = next(t for t, _, a in trace if t >= 480 and not a)
    assert off - 480 <= 100, off                                  # ... and clears after the recovery
    low = next(t for t, r, _ in trace if t >= 240 and r is not None and r < 8)
    assert low - 240 <= 50, low                                   # the slow rate itself shows sooner


def test_a_large_fall_from_the_patients_own_rate_raises_an_advisory():
    rate = lambda t: 20 if t < 300 else 10                         # still above 8, but halved
    trace = run(breathing(rate, 480, seed=9))
    advisory = next((a for t, _, a in trace if a), None)
    assert advisory and "down" in advisory and "from 20/min" in advisory, advisory


def test_slow_fall_of_co2_raises_an_advisory_and_its_return_clears_it():
    # the card's Figure 2: CO2 above room air falls by half over 2 minutes, breathing at 12/min
    excess = lambda t: 1500 if t < 300 or t >= 540 else max(750, 1500 - 750 * (t - 300) / 120)
    trace = run(breathing(12, 720, excess=excess, seed=10))
    on = next((t for t, _, a in trace if a), None)
    assert on is not None and 300 + 60 <= on <= 300 + 140, on
    advisory = next(a for _, _, a in trace if a)
    assert advisory.startswith("CO2 down"), advisory
    off = next(t for t, _, a in trace if t >= 540 and not a)
    assert off - 540 <= 70, off


def feed_watch(watch, plan, ppm=2000, t=0.0):
    """plan: [(seconds, rate)] from time t; CR-1 PRESENT throughout. Returns [(t, advisory)]."""
    out = []
    for seconds, rate in plan:
        for _ in range(seconds):
            out.append((t, watch.update(t, ppm, PRESENT, rate)))
            t += 1.0
    return out


def test_an_unresolved_rate_neither_starts_nor_stops_the_clock():
    w = FallWatch()
    trace = feed_watch(w, [(20, 6.0), (20, None), (10, 6.0)])
    first = next((t for t, a in trace if a), None)
    assert first == 40.0, first          # 30 s after the fall began, with the low seconds seen
    w = FallWatch()
    trace = feed_watch(w, [(20, 6.0), (1, 12.0), (20, 6.0)])
    assert not [t for t, a in trace if a]    # a second back in range: the fall did not last


def test_an_advisory_clears_only_after_30_s_back_in_range():
    w = FallWatch()
    trace = feed_watch(w, [(40, 6.0), (30, 12.0)])                 # in range from t = 40 s
    assert trace[-1] == (69.0, trace[-1][1]) and trace[-1][1] is not None   # 29 s in range: on
    trace = feed_watch(w, [(1, 12.0)], t=70.0)
    assert trace[-1][1] is None                                    # 30 s: cleared (card, Figure 3)


def test_co2_lost_then_back_starts_new_baselines():
    w = FallWatch()
    feed_watch(w, [(200, 15.0)])
    assert w.baselines(199.0)[1] == 15.0
    w.update(200.0, 900, ABSENT, None)                            # CO2 lost (CR-2's critical alarm)
    assert w.level_base == [] and w.rate_base == []


def test_holding_the_button_forgets_the_baselines():
    rm = RateMonitor()
    for t, ppm in breathing(15, 300, seed=11):
        rm.update(t, ppm, PRESENT)
    assert rm.watch.baselines(299.0)[1] is not None
    rm.restart()
    assert rm.watch.baselines(299.0) == (None, None)


def test_banners_say_when_the_rate_appears_and_when_it_is_lost():
    rm = RateMonitor()
    room_air(rm)
    banners = []
    readings = breathing(15, 200, seed=12)
    for t, ppm in readings:
        b = rm.update(t, ppm, PRESENT)
        if b:
            banners.append(b)
    for t in range(200, 290):                                     # breathing stops, CO2 lingers
        b = rm.update(float(t), readings[-1][1], PRESENT)
        if b:
            banners.append(b)
    assert banners[0] == "CR-4 RATE: 15/min", banners
    assert banners[1].startswith("CR-4 RATE: not resolved"), banners
    assert rm.shown() == "RR --"


def test_the_pico_keeps_its_light_sound_and_button_running_during_an_estimate():
    br = BreathingRate()
    calls = []
    readings = breathing(15, 120, seed=13)
    for t, ppm in readings:
        br.update(t, ppm, PRESENT, idle=lambda: calls.append(t))
        if br.evaluated:
            break
    assert br.evaluated and len(calls) >= 12, len(calls)       # every few rates, at least 12 times


# ---------------------------------------------------------------- the board program (dry run)
def sensor_for_dry_run(rate, start, breathing_from):
    """The sensor as code.py sees it: the warm-up placeholder, room air, then breathing at
    rate(t) from `breathing_from`, through a cell and sensor 2 + 3 s slow, with a swing of the
    size a pump would give (+/-100 ppm at 6/min)."""
    rnd = random.Random(21)
    excess = lambda s: 0 if s < 1 else 1100
    sim = breathing(lambda s: rate(s + breathing_from), 1200, excess=excess, swing=300,
                    tau_cell=2.0, tau_sensor=3.0, seed=22)
    table = dict((int(s), p) for s, p in sim)

    def sensor(t):
        if t < 75:
            return 500                                           # the warm-up placeholder
        if t < breathing_from:
            return int(round(900 + rnd.gauss(0, 1.0)))           # room air
        return table.get(int(t - breathing_from), sim[-1][1])
    return sensor


def test_code_py_shows_the_rate_and_slow_breathing_is_amber_not_red():
    import test_co2events as dry
    rate = lambda t: 15 if t < 420 else 6
    lines = dry._dry_run(sensor_for_dry_run(rate, 5.0, 150), 5.0, 600.0)
    text = "\n".join(lines)
    assert ">>> CR-4 RATE: 15/min <<<" in text
    assert "--- CR-4: one breathing-rate estimate took" in text
    shown = [float(ln.split("RR ")[1].split()[0]) for ln in lines if ln.startswith("t=") and "RR " in ln
             and "RR --" not in ln]
    assert shown and min(shown) >= 5.5, shown[:5]                # never a rate too low
    assert any(14.5 <= r <= 15.5 for r in shown) and any(r < 8 for r in shown)
    advisory = [ln for ln in lines if ln.startswith(">>> ALARM ADVISORY: breathing rate")]
    assert advisory and "below 8/min" in advisory[0], text[-800:]
    assert "ALARM CRITICAL" not in text and ">>> CO2 ABSENT" not in text.split("CO2 PRESENT")[-1]
    kinds = dry._ring_kinds()
    assert "amber" in kinds[5:], kinds                           # after the lamp test
    assert any(t > 420 and f == 1800 for t, f in dry.TONES)      # the advisory's 3 pulses


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
