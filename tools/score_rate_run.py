"""Score one paced-breathing run log (tools/rate_run.sh) against the draft CR-4 requirements.

    python3 tools/score_rate_run.py data/raw/rate_2026-10-27_101500_lung01.log

Reads the marks written by rate_run.sh (## RUN START, ## PHASE i rate=R seconds=D, ## STOP) and the
board's lines (... RR 15.2, or RR --) and banners (>>> ALARM ADVISORY ..., >>> ALARM NORMAL ...),
timed by the Mac clock (1 s). For each phase:

  ER-7, breathing rate: from SETTLE_S after the phase starts to its end, a rate is shown at least
       SHOWN_MIN of the time, its median is within TOL_BPM (or TOL_FRAC of the paced rate, the
       larger) of the paced rate, and it is never below LOW_FRAC of it (a falsely low rate is the
       error that raises false advisories). Also printed: how long the right rate took to show.
  ER-8, advisory: a phase slower than RR_LOW (8/min) raises the ADVISORY within ADVISORY_MAX_S of
       its start; a steady phase (not just after a slow one) raises none; after a slow phase, the
       time until the alarm is back to NORMAL is printed.

Prints a summary and appends one row per phase to data/runs/rate_results.csv. Python 3 standard
library only (the Mac's own python3 is enough).
"""
import csv
import os
import re
import statistics
import sys
import time

SETTLE_S = 50           # the rate is worked out over 64 s: give it this long into each phase
SHOWN_MIN = 0.80        # ER-7: a rate shown at least 80 % of the scored time ...
TOL_BPM = 1.0           # ... its median within 1 breath/min ...
TOL_FRAC = 0.10         # ... or 10 % of the paced rate, the larger ...
LOW_FRAC = 0.80         # ... and never below 80 % of the paced rate
RR_LOW = 8.0            # firmware/lib/cr4.py: an advisory below 8/min
ADVISORY_MAX_S = 90     # ER-8: the advisory within 90 s of the start of the slowing

CLOCK = re.compile(r"^(\d\d):(\d\d):(\d\d)  (.*)$")
READING = re.compile(r"^t=\s*\d+ s\s+CO2\s+(\d+) ppm\s.*\bRR (--|\d+(?:\.\d+)?)")
PHASE = re.compile(r"^## PHASE (\d+) rate=([\d.]+) seconds=(\d+)")


def read_log(path):
    """[(seconds, text)] with the Mac clock made continuous across midnight."""
    out, last, offset = [], None, 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = CLOCK.match(line.rstrip("\n"))
            if not m:
                continue
            s = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + offset
            if last is not None and s < last - 43200:
                offset += 86400
                s += 86400
            last = s
            out.append((s, m.group(4)))
    return out


def score(path):
    """Returns (run info, [phase results]). Each phase result is a dict."""
    lines = read_log(path)
    label = "none"
    phases, stop = [], None
    readings, banners = [], []
    for s, text in lines:
        if text.startswith("## RUN START"):
            m = re.search(r"label=(\S+)", text)
            label = m.group(1) if m else label
        m = PHASE.match(text)
        if m:
            phases.append({"n": int(m.group(1)), "rate": float(m.group(2)), "seconds": int(m.group(3)),
                           "start": s})
        if text.startswith("## STOP"):
            stop = s
        m = READING.match(text)
        if m:
            rr = None if m.group(2) == "--" else float(m.group(2))
            readings.append((s, int(m.group(1)), rr))
        if text.startswith(">>> "):
            banners.append((s, text))
    if not phases:
        raise ValueError("no ## PHASE marks in %s: is it a rate_run.sh log?" % path)
    for i, p in enumerate(phases):
        p["end"] = phases[i + 1]["start"] if i + 1 < len(phases) else (stop or p["start"] + p["seconds"])
    results = []
    for i, p in enumerate(phases):
        prev = phases[i - 1] if i > 0 else None
        results.append(_phase(p, prev, readings, banners))
    problems = [(s, b) for s, b in banners if s >= phases[0]["start"] and s < phases[-1]["end"]
                and (b.startswith(">>> SENSOR FAULT") or b.startswith(">>> ALARM CRITICAL")
                     or b.startswith(">>> ALARM TECHNICAL"))]
    info = {"label": label, "log": os.path.basename(path), "problems": problems,
            "valid": not any(b.startswith(">>> SENSOR FAULT") for _, b in problems)}
    return info, results


def _phase(p, prev, readings, banners):
    r = p["rate"]
    tol = max(TOL_BPM, TOL_FRAC * r)
    t0 = p["start"] + min(SETTLE_S, p["seconds"] // 2)
    scored = [rr for s, _, rr in readings if t0 <= s < p["end"]]
    shown = [x for x in scored if x is not None]
    res = {"phase": p["n"], "rate": r, "seconds": p["seconds"], "scored_s": len(scored),
           "shown_frac": (len(shown) / len(scored)) if scored else 0.0,
           "median": statistics.median(shown) if shown else None,
           "min": min(shown) if shown else None, "max": max(shown) if shown else None}
    first_right = next((s for s, _, rr in readings if p["start"] <= s < p["end"] and rr is not None
                        and abs(rr - r) <= tol), None)
    res["right_after_s"] = None if first_right is None else first_right - p["start"]
    notes = []
    if not scored:
        res["er7"] = "no data"
        notes.append("no readings in the scored part")
    elif not shown:
        res["er7"] = "FAIL"
        notes.append("no rate shown (is air moving through the cell?)")
    else:
        ok = (res["shown_frac"] >= SHOWN_MIN and abs(res["median"] - r) <= tol and res["min"] >= LOW_FRAC * r)
        res["er7"] = "PASS" if ok else "FAIL"
        if res["min"] < LOW_FRAC * r:
            notes.append("a rate below %.0f %% of the paced one was shown" % (100 * LOW_FRAC))
    # ER-8
    adv = [s for s, b in banners if b.startswith(">>> ALARM ADVISORY")]
    res["advisory_s"] = res["cleared_s"] = None
    slow_before = prev is not None and prev["rate"] < RR_LOW
    if r < RR_LOW:
        first = next((s for s in adv if p["start"] <= s < p["end"] + 30), None)
        res["advisory_s"] = None if first is None else first - p["start"]
        res["er8"] = "PASS" if first is not None and first - p["start"] <= ADVISORY_MAX_S else "FAIL"
    elif slow_before:
        back = next((s for s, b in banners if p["start"] <= s < p["end"] and b.startswith(">>> ALARM NORMAL")), None)
        res["cleared_s"] = None if back is None else back - p["start"]
        res["er8"] = "cleared" if back is not None else "not cleared"
    else:
        false = [s for s in adv if p["start"] <= s < p["end"]]
        res["er8"] = "PASS" if not false else "FAIL"
        if false:
            notes.append("%d advisory during steady breathing" % len(false))
    res["notes"] = "; ".join(notes)
    return res


def fmt(x, form="%.1f"):
    return "--" if x is None else form % x


def main(argv):
    if len(argv) != 2 or not os.path.isfile(argv[1]):
        print("usage: python3 tools/score_rate_run.py <rate run log>")
        return 1
    info, results = score(argv[1])
    print()
    print("================ rate run result: %s ================" % info["label"])
    for res in results:
        print("  phase %d, paced %s/min for %d s" % (res["phase"], fmt(res["rate"], "%g"), res["seconds"]))
        print("    rate shown        : %3.0f %% of the scored %d s, median %s/min (%s to %s), right after %s s"
              % (100 * res["shown_frac"], res["scored_s"], fmt(res["median"]), fmt(res["min"]), fmt(res["max"]),
                 fmt(res["right_after_s"], "%d")))
        print("    ER-7 (rate)       : %s" % res["er7"])
        if res["advisory_s"] is not None or res["rate"] < RR_LOW:
            print("    advisory          : %s s after the slowing began        ER-8 (<= %d s): %s"
                  % (fmt(res["advisory_s"], "%d"), ADVISORY_MAX_S, res["er8"]))
        elif res["er8"] in ("cleared", "not cleared"):
            print("    back to NORMAL    : %s s into the phase (%s)" % (fmt(res["cleared_s"], "%d"), res["er8"]))
        else:
            print("    advisory          : none expected                        ER-8 (none): %s" % res["er8"])
        if res["notes"]:
            print("    note              : %s" % res["notes"])
    for s, b in info["problems"]:
        print("  during the run     : %s" % b)
    print("  run                : %s" % ("valid" if info["valid"] else "invalid (sensor fault during the run)"))
    print()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "data", "runs", "rate_results.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    new = not os.path.exists(out)
    with open(out, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "time", "label", "phase", "rate_per_min", "seconds", "shown_pct", "median",
                        "min", "max", "right_after_s", "er7", "advisory_s", "cleared_s", "er8", "valid",
                        "notes", "log"])
        for res in results:
            w.writerow([time.strftime("%Y-%m-%d"), time.strftime("%H:%M:%S"), info["label"], res["phase"],
                        "%g" % res["rate"], res["seconds"], "%.0f" % (100 * res["shown_frac"]),
                        fmt(res["median"]), fmt(res["min"]), fmt(res["max"]), fmt(res["right_after_s"], "%d"),
                        res["er7"], fmt(res["advisory_s"], "%d"), fmt(res["cleared_s"], "%d"), res["er8"],
                        "valid" if info["valid"] else "invalid", res["notes"], info["log"]])
    print("Saved to %s" % os.path.relpath(out, root))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
