"""Turns one line from the monitor into a dict the service can use.

The board (firmware v0.5 and later) prints two lines per second: one for people and one JSON object
for this service (interface IF-6). Older firmware printed only the line for people, so that one is
understood too: recorded logs from 22 to 25 Oct can be replayed into the dashboard.

    {"v": "0.5", "t": 312, "ppm": 1814, "cr1": "PRESENT", ...}            -> kind "sample" (JSON)
    t=  312 s  CO2  1814 ppm  |#########....|  PRESENT    NORMAL           -> kind "sample" (text)
    t=  315 s  no answer from sensor  FAULT      TECHNICAL                 -> kind "sample" (text)
    >>> ALARM CRITICAL: CO2 lost: fell 108 ppm from 1814 in under 20 s <<<  -> kind "banner"
    Team 6 CO2 monitor v0.5 - CR-1 present/absent ...                     -> kind "boot"

Pure Python, no I/O.
"""
from __future__ import annotations

import json
import re

CR1_STATES = ("WARMING UP", "ABSENT", "PRESENT", "FAULT")
DISPLAYS = ("STANDBY", "NORMAL", "ADVISORY", "CRITICAL ACK", "CRITICAL BACK", "CRITICAL", "TECHNICAL")

_CR1 = "|".join(CR1_STATES)
_SHOW = "|".join(DISPLAYS)
_READING = re.compile(r"^t=\s*(\d+) s\s+CO2\s+(\d+) ppm\s+\|[#.]*\|\s+(%s)(?:\s+(%s))?" % (_CR1, _SHOW))
_NO_ANSWER = re.compile(r"^t=\s*(\d+) s\s+no answer from sensor\s+(%s)(?:\s+(%s))?" % (_CR1, _SHOW))
_BANNER = re.compile(r"^>>> (.*) <<<$")
_BOOT = re.compile(r"Team 6 CO2 monitor v(\d+\.\d+)")
_CLOCK = re.compile(r"^\d\d:\d\d:\d\d  ")   # "HH:MM:SS  " put in front of each line by the Mac tools
# CircuitPython also writes terminal control codes: its status bar ("ESC]0;Wi-Fi: off | code.py ESC\")
# and line clearing ("ESC[2K"). They are not part of what the program printed.
_ESCAPES = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-z]")


def clean(line: str) -> str:
    """The line without terminal control codes."""
    return _ESCAPES.sub("", line)


def alarm_of(show: str | None) -> str | None:
    """The alarm state behind what the ring shows: CRITICAL ACK and CRITICAL BACK are CRITICAL."""
    if show is None:
        return None
    return "CRITICAL" if show.startswith("CRITICAL") else show


def strip_clock(line: str) -> str:
    """Drop the Mac's "HH:MM:SS  " prefix that the raw logs carry."""
    return line[10:] if _CLOCK.match(line) else line


def parse_line(line: str) -> dict:
    line = clean(line).strip()
    if line.startswith("{"):
        try:
            d = json.loads(line)
        except ValueError:
            return {"kind": "garbled", "text": line}
        if not isinstance(d, dict) or "t" not in d:
            return {"kind": "garbled", "text": line}
        show = d.get("show")
        return {
            "kind": "sample", "source": "json", "fw": d.get("v"),
            "t": d.get("t"), "ppm": d.get("ppm"),
            "cr1": d.get("cr1"), "cr1_why": d.get("cr1_why"),
            "alarm": d.get("alarm") or alarm_of(show), "show": show, "why": d.get("why"),
            "acked": bool(d.get("acked")), "latched": bool(d.get("latched")),
            "press": int(d.get("press") or 0), "hold": int(d.get("hold") or 0),
            "dash_ack": int(d.get("dash_ack") or 0),
        }
    m = _READING.match(line)
    if m:
        show = m.group(4)
        return {"kind": "sample", "source": "text", "fw": None, "t": int(m.group(1)), "ppm": int(m.group(2)),
                "cr1": m.group(3), "cr1_why": None, "alarm": alarm_of(show), "show": show, "why": None,
                "acked": show == "CRITICAL ACK", "latched": bool(show and show.startswith("CRITICAL")),
                "press": 0, "hold": 0, "dash_ack": 0}
    m = _NO_ANSWER.match(line)
    if m:
        show = m.group(3)
        return {"kind": "sample", "source": "text", "fw": None, "t": int(m.group(1)), "ppm": None,
                "cr1": m.group(2), "cr1_why": None, "alarm": alarm_of(show), "show": show, "why": None,
                "acked": show == "CRITICAL ACK", "latched": bool(show and show.startswith("CRITICAL")),
                "press": 0, "hold": 0, "dash_ack": 0}
    m = _BANNER.match(line)
    if m:
        return {"kind": "banner", "text": m.group(1)}
    m = _BOOT.search(line)
    if m:
        return {"kind": "boot", "fw": m.group(1), "text": line}
    return {"kind": "other", "text": line}


def quality(sample: dict) -> str:
    """How far a reading can be trusted, for the readings table."""
    ppm = sample.get("ppm")
    if ppm is None:
        return "no_answer"
    if sample.get("cr1") in ("WARMING UP", "FAULT"):
        return "not_trusted"
    if ppm <= 400:
        return "floor"
    if ppm >= 5000:
        return "top_of_range"
    return "ok"
