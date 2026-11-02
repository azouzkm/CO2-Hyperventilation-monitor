"""Ties the service together: lines from the board -> parse -> rules -> database and phone messages,
and the state the dashboard asks for. Used by service/__main__.py (the real thing) and by the tests.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque

from .notifier import CHANNELS, DEFAULTS as NOTIFY_DEFAULTS, LEVELS, CallMeBot, Notifier, public_user, validate_signup
from .parse import clean, parse_line, quality
from .rules_engine import Monitor
from .store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(path: str | None = None) -> dict:
    """config.json, shared with the rest of the project. Missing keys fall back to sensible values."""
    path = path or os.path.join(ROOT, "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    svc = cfg.get("service", {})
    notify = dict(NOTIFY_DEFAULTS)
    notify.update({k: v for k, v in cfg.get("notify", {}).items() if k in NOTIFY_DEFAULTS})
    return {
        "link_timeout_s": float(cfg.get("technical_timeout_s", 5.0)),
        "silence_s": float(svc.get("silence_s", 120.0)),
        "http_port": int(svc.get("http_port", 8000)),
        "history_s": float(svc.get("history_s", 600.0)),
        "db_path": os.path.join(ROOT, svc.get("db_path", "data/co2monitor.sqlite")),
        "raw_log_dir": os.path.join(ROOT, svc.get("raw_log_dir", "data/raw")),
        "notify": notify,
    }


class Service:
    def __init__(self, cfg: dict, source_factory, raw_log=None, echo=print, clock=time.time, preload=True,
                 sender=None, messages: str | None = None):
        """messages: None sends phone messages; "replay" sends test messages only; "--no-messages" none."""
        self.cfg, self.echo, self.clock = cfg, echo, clock
        self.started_at = clock()
        self.monitor = Monitor(self.started_at, link_timeout_s=cfg["link_timeout_s"], silence_s=cfg["silence_s"])
        self.store = Store(cfg["db_path"], people_path=cfg.get("people_db"))
        self.notifier = Notifier(self.store, sender if sender is not None else CallMeBot(), cfg.get("notify"),
                                 clock=clock, dry_run=messages, echo=echo)
        self.raw_log = raw_log
        self.lock = threading.RLock()
        self.status_text = "Starting"
        self.garbled = 0
        self.json_seen = False         # firmware 0.5+: its JSON line is the reading, the text line is for people
        self._last_text = None         # (board time, row id) of the last reading taken from a text line
        self.history = deque(maxlen=int(cfg["history_s"] * 2) + 10)
        if preload:                    # a restart mid-session keeps the trend on screen
            for ts, ppm, display, cr1 in self.store.readings_since(self.started_at - cfg["history_s"]):
                self.history.append((ts, ppm, display, cr1))
        self.source = source_factory(self.on_line, self.on_status)
        self._stop = threading.Event()
        self._ticker = threading.Thread(target=self._tick_loop, daemon=True, name="link-watchdog")

    # -- life cycle ----------------------------------------------------------------------------
    def start(self) -> None:
        self.source.start()
        self._ticker.start()
        self.notifier.start()

    def stop(self) -> None:
        self._stop.set()
        self.source.stop()
        for thread in (self.source, self._ticker):
            if isinstance(thread, threading.Thread) and thread.is_alive():
                thread.join(timeout=2.0)
        self.notifier.stop()
        with self.lock:
            self.store.close_open_alarms(self.clock())
            self.store.close()             # folds the write-ahead log back into the .sqlite file
        if self.raw_log is not None:
            self.raw_log.close()

    def _tick_loop(self) -> None:
        last_error = None
        while not self._stop.wait(0.5):
            try:
                self.tick()
                last_error = None
            except Exception as e:             # keep watching the link whatever goes wrong
                if repr(e) != last_error:
                    self.echo("[dashboard] Link watchdog error (still watching): %r" % (e,))
                    last_error = repr(e)

    def tick(self) -> None:
        with self.lock:
            now = self.clock()
            for e in self.monitor.tick(now):
                self._apply(e)
            try:
                self.notifier.tick(now)
            except Exception as err:                   # phone messages must never stop the link watchdog
                if repr(err) != getattr(self, "_notify_error", None):
                    self.echo("[dashboard] Phone alerts error: %r" % (err,))
                    self._notify_error = repr(err)

    # -- what arrives from the board -----------------------------------------------------------
    def on_status(self, text: str) -> None:
        with self.lock:
            self.status_text = text
        self.echo("[dashboard] " + text)

    def on_line(self, text: str, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        if self.raw_log is not None:
            self.raw_log.write(text, now)
        d = parse_line(text)
        if d["kind"] == "sample" and d["source"] == "json":
            self.json_seen = True
        elif d["kind"] == "sample" and self.json_seen:
            d = {"kind": "echo"}         # the same reading as the JSON line that follows it
        with self.lock:
            if d["kind"] == "sample":
                if d["source"] == "json" and self._last_text and self._last_text[0] == d["t"]:
                    self.store.drop_reading(self._last_text[1])     # at start-up the text line came first
                    if self.history:
                        self.history.pop()
                self._last_text = None
                events = self.monitor.on_sample(now, d)
                rowid = self.store.add_reading(now, d, quality(d))
                if d["source"] == "text":
                    self._last_text = (d["t"], rowid)
                self.history.append((now, d["ppm"], d["show"], d["cr1"]))
            elif d["kind"] == "banner":
                events = self.monitor.on_banner(now, d["text"])
                self.store.add_device_event(now, d["text"])
            elif d["kind"] == "boot":
                self.monitor.on_boot(d["fw"])
                self.store.add_device_event(now, d["text"])
                events = []
            else:
                if d["kind"] == "garbled":
                    self.garbled += 1
                events = []
            for e in events:
                self._apply(e)
        if not (d["kind"] == "sample" and d.get("source") == "json"):
            self.echo(time.strftime("%H:%M:%S  ", time.localtime(now)) + clean(text))

    def _apply(self, e: dict) -> None:
        self.store.apply(e)
        alarm_id = self.store.open_alarm_id(e["key"]) if e["type"] == "alarm_raised" else None
        try:
            self.notifier.on_event(e, alarm_id)
        except Exception as err:                       # phone messages must never stop the monitoring
            self.echo("[dashboard] Phone alerts error: %r" % (err,))
        if e["type"] == "alarm_raised" and e["key"] == "link":
            self.echo("[dashboard] TECHNICAL: " + e["reason"])
        elif e["type"] == "alarm_cleared" and e["key"] == "link":
            self.echo("[dashboard] Readings are arriving again.")
        elif e["type"] == "ack" and e["method"] == "dashboard":
            self.echo("[dashboard] Acknowledged by %s on the dashboard%s" % (
                e["who"], "" if e["confirmed"] else " (not confirmed by the monitor: sound off on the dashboard only)"))

    # -- what the dashboard asks for -----------------------------------------------------------
    def ack(self, who: str) -> dict:
        with self.lock:
            r = self.monitor.request_ack(self.clock(), who)
            if r["ok"] and r["send"]:
                if not self.source.send(r["send"]):
                    r["message"] = ("Sound off on this screen for %d s. The monitor could not be reached, "
                                    "so it keeps sounding until someone presses its button."
                                    % self.cfg["silence_s"])
            r.pop("send", None)
            return r

    def latest(self) -> dict:
        with self.lock:
            v = self.monitor.view(self.clock())
            v["port"] = getattr(self.source, "port", None)
            v["status"] = self.status_text
            v["garbled_lines"] = self.garbled
            v["raw_log"] = os.path.relpath(self.raw_log.path, ROOT) if self.raw_log is not None else None
            v["server_time"] = self.clock()
        # the starter REST contract: co2 in percent and the state in lower case
        v["co2_pct"] = None if v["ppm"] is None else round(v["ppm"] / 10000.0, 4)
        v["state"] = {"LINK LOST": "technical", "WAITING": "technical", "CRITICAL ACK": "critical",
                      "CRITICAL BACK": "critical"}.get(v["display"], (v["display"] or "unknown").lower())
        return v

    def readings(self, seconds: float) -> list:
        since = self.clock() - seconds
        with self.lock:
            return [[round(ts, 3), ppm, display] for ts, ppm, display, _ in self.history if ts >= since]

    def alarms(self, limit: int = 20) -> list:
        return self.store.alarms(limit)

    # -- phone alerts: the sign-up page --------------------------------------------------------
    def phones(self) -> dict:
        """For the dashboard: how many people get messages, and any message that failed lately."""
        since = self.clock() - 3600.0
        failed = [n for n in self.store.notifications(50)
                  if n["status"] == "failed" and (n["queued"] or 0) >= since]
        return {"active": sum(1 for u in self.store.users() if u.get("active")),
                "mode": self.notifier.mode(),
                "failed": [{"who": n["who"], "ts": n["queued"], "error": n["error"]} for n in failed[:3]]}

    def people(self) -> dict:
        last = self.store.last_messages()
        return {"users": [public_user(u, last.get(u["user_id"])) for u in self.store.users()],
                "apps": CHANNELS, "levels": {str(k): v for k, v in LEVELS.items()}, "mode": self.notifier.mode()}

    def signup(self, form: dict):
        ok, value = validate_signup(form)
        if not ok:
            return 400, {"ok": False, "message": value}
        with self.lock:
            user_id = self.store.save_user(self.clock(), value["name"], value["role"], value["channel"],
                                           value["phone"], value["telegram"], value["apikey"], value["level"])
            user = next(u for u in self.store.users() if u["user_id"] == user_id)
            self.notifier.test(user)
        note = ("Signed up. A test message is on its way: check your phone in a minute."
                if self.notifier.mode() != "--no-messages" else
                "Signed up. This service was started with --no-messages, so nothing is sent.")
        return 201, {"ok": True, "message": note, "user": public_user(user)}

    def send_test(self, user_id: int):
        with self.lock:
            user = next((u for u in self.store.users() if u["user_id"] == user_id), None)
            if user is None:
                return 404, {"ok": False, "message": "No such person."}
            if not user.get("active"):
                return 409, {"ok": False, "message": "Messages to %s are stopped. Start them again first." % user["name"]}
            self.notifier.test(user)
        return 202, {"ok": True, "message": "Test message on its way to %s." % user["name"]}

    def set_active(self, user_id: int, active: bool):
        with self.lock:
            if not self.store.set_user_active(self.clock(), user_id, active):
                return 404, {"ok": False, "message": "No such person."}
        return 200, {"ok": True, "message": "Messages started again." if active else "Messages stopped."}
