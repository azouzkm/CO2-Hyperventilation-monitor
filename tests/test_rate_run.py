"""Laptop-side tests for tools/score_rate_run.py, the scoring of a paced-breathing run for CR-4.

A run log is rebuilt the way tools/rate_run.sh writes it on the Mac: the board's own lines, from a
dry run of firmware/code.py on simulated breathing that follows the plan (15/min for 150 s, 6/min
for 150 s, 15/min for 120 s), each line stamped with a clock time, and the run's marks
(## PHASE, ## CUE, ## STOP) in between. Then it is scored.

Run from the repository root:   python -m pytest tests/
(or without pytest:              python tests/test_rate_run.py)
"""
import importlib.util
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_co2events as dry  # noqa: E402
from test_cr4 import breathing  # noqa: E402

_spec = importlib.util.spec_from_file_location("score_rate_run", os.path.join(ROOT, "tools", "score_rate_run.py"))
score_rate_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score_rate_run)

PLAN = ((15, 150), (6, 150), (15, 120))
BREATHING_FROM = 150          # board time (s) of the first cue
CLOCK0 = 10 * 3600            # the Mac clock reads 10:00:00 at board time 0


def plan_rate(t):
    s = BREATHING_FROM
    for rate, seconds in PLAN:
        if t < s + seconds:
            return rate
        s += seconds
    return PLAN[-1][0]


def sensor(stop_at, seed=31):
    """Warm-up placeholder, room air, then breathing that follows the plan, stopping at stop_at."""
    import random
    rnd = random.Random(seed)
    span = stop_at - BREATHING_FROM
    sim = breathing(lambda s: plan_rate(s + BREATHING_FROM), span + 200,
                    excess=lambda s: 1100 if 1 <= s < span else 0,
                    swing=lambda s: 300 if s < span else 0, tau_cell=2.0, tau_sensor=3.0, seed=seed)
    table = dict((int(s), p) for s, p in sim)

    def read(t):
        if t < 75:
            return 500
        if t < BREATHING_FROM:
            return int(round(900 + rnd.gauss(0, 1.0)))
        return table.get(int(t - BREATHING_FROM), 900)
    return read


def clock(t):
    s = int(CLOCK0 + t)
    return "%02d:%02d:%02d" % (s // 3600 % 24, s // 60 % 60, s % 60)


def build_log(path, rr_shown=True):
    stop_at = BREATHING_FROM + sum(sec for _, sec in PLAN)
    lines = dry._dry_run(sensor(stop_at), 5.0, stop_at + 60.0)
    marks = [(BREATHING_FROM - 25, "## RUN START label=sim plan=15:150,6:150,15:120 cue=breathe rest=60")]
    s, n = BREATHING_FROM, 0
    for i, (rate, seconds) in enumerate(PLAN):
        marks.append((s, "## PHASE %d rate=%d seconds=%d" % (i + 1, rate, seconds)))
        k = 0
        while k * 60.0 / rate < seconds - 0.05:
            n += 1
            marks.append((int(s + k * 60.0 / rate), "## CUE %d" % n))
            k += 1
        s += seconds
    marks.append((stop_at, "## STOP"))
    marks.append((stop_at + 60, "## RUN END"))
    out, t, mi = [], 0, 0
    for ln in lines:
        if ln.startswith("t="):
            t = int(ln[2:7])
            while mi < len(marks) and marks[mi][0] <= t:
                out.append("%s  %s" % (clock(marks[mi][0]), marks[mi][1]))
                mi += 1
            if not rr_shown:                              # a run where no rate could be read
                ln = ln[:ln.index("RR ")] + "RR --"
        elif not rr_shown and ln.startswith((">>> ALARM ADVISORY", ">>> CR-4 RATE")):
            continue
        out.append("%s  %s" % (clock(t), ln))
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")


def scored(rr_shown=True):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "rate_sim.log")
        build_log(path, rr_shown)
        return score_rate_run.score(path)


def test_a_good_run_passes_er7_in_every_phase_and_er8_on_the_slowing():
    info, res = scored()
    assert info["label"] == "sim" and info["valid"]
    assert [r["er7"] for r in res] == ["PASS", "PASS", "PASS"], res
    assert abs(res[0]["median"] - 15) <= 0.5 and abs(res[1]["median"] - 6) <= 0.5
    assert res[0]["right_after_s"] is not None and res[0]["right_after_s"] <= 60
    assert res[1]["er8"] == "PASS" and 30 <= res[1]["advisory_s"] <= 90, res[1]
    assert res[0]["er8"] == "PASS"                              # no advisory while steady
    assert res[2]["er8"] == "cleared" and res[2]["cleared_s"] <= 100, res[2]
    # the stop at the end raises the critical alarm, but only after the last phase
    assert not [b for _, b in info["problems"] if "CRITICAL" in b]


def test_no_rate_shown_fails_er7_and_says_why():
    info, res = scored(rr_shown=False)
    assert [r["er7"] for r in res] == ["FAIL", "FAIL", "FAIL"]
    assert "no rate shown" in res[0]["notes"]
    assert res[1]["er8"] == "FAIL" and res[1]["advisory_s"] is None


def test_midnight_does_not_break_the_clock():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "x.log")
        with open(path, "w") as f:
            f.write("23:59:58  ## PHASE 1 rate=10 seconds=4\n23:59:59  t=  1 s  CO2  1500 ppm  |#|  "
                    "PRESENT    NORMAL       RR 10.0\n00:00:01  t=  3 s  CO2  1500 ppm  |#|  PRESENT    "
                    "NORMAL       RR 10.0\n00:00:02  ## STOP\n")
        info, res = score_rate_run.score(path)
        # scored from 2 s into the phase (00:00:00) to the stop: the reading at 00:00:01 only,
        # which would be lost if 00:00:01 came before 23:59:58
        assert res[0]["scored_s"] == 1 and res[0]["median"] == 10.0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
