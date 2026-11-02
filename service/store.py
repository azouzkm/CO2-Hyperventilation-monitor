"""The SQLite database (interface IF-7): one file, write-ahead logging, one writer (the ingest thread).

    readings       one row per reading from the board
    alarm_events   every alarm, from the board or from the link watchdog: when it started and ended
    acks           who acknowledged which alarm, how (bedside button or dashboard), and when
    device_events  the board's banner lines (state changes, button presses), for the record
    users          message recipients: course participants who opted in, with the consent time,
                   their app (WhatsApp, Signal or Telegram through CallMeBot) and their own key
    notifications  every message to a phone: which alarm, to whom, its text, and whether it went
    calibrations   calibration fits against the reference capnograph

No patient identifiers go into any table. Times are UTC, ISO 8601. The file stays on this laptop
(git ignores it): it holds phone numbers and CallMeBot keys.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id        INTEGER PRIMARY KEY,
    ts_utc    TEXT NOT NULL,
    t_board   INTEGER,
    ppm       INTEGER,
    cr1       TEXT,
    alarm     TEXT,
    display   TEXT,
    acked     INTEGER,
    quality   TEXT,
    fw        TEXT
);
CREATE INDEX IF NOT EXISTS readings_ts ON readings (ts_utc);
CREATE TABLE IF NOT EXISTS alarm_events (
    alarm_id     INTEGER PRIMARY KEY,
    priority     TEXT NOT NULL,
    source       TEXT NOT NULL,
    ts_raised    TEXT NOT NULL,
    ts_cleared   TEXT,
    reason       TEXT,
    ppm_at_raise INTEGER
);
CREATE TABLE IF NOT EXISTS acks (
    ack_id       INTEGER PRIMARY KEY,
    alarm_id     INTEGER,
    ts           TEXT NOT NULL,
    user_id      TEXT,
    method       TEXT,
    confirmed    INTEGER,
    ts_confirmed TEXT
);
CREATE TABLE IF NOT EXISTS device_events (
    id     INTEGER PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    text   TEXT
);
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    role       TEXT,
    phone_e164 TEXT,
    optin_ts   TEXT,
    active     INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS notifications (
    id               INTEGER PRIMARY KEY,
    alarm_id         INTEGER,
    user_id          INTEGER,
    ts_sent          TEXT,
    provider         TEXT,
    provider_msg_id  TEXT,
    status           TEXT,
    error            TEXT
);
CREATE INDEX IF NOT EXISTS notifications_alarm ON notifications (alarm_id);
CREATE TABLE IF NOT EXISTS calibrations (
    id         INTEGER PRIMARY KEY,
    device_id  TEXT,
    ts         TEXT,
    slope      REAL,
    intercept  REAL,
    reference  TEXT,
    operator   TEXT,
    rms_resid  REAL
);
"""

# Columns added for the notifier (26 Oct). Added to older database files when they are opened.
ADDED_COLUMNS = {
    "users": (("channel", "TEXT"), ("apikey", "TEXT"), ("telegram", "TEXT"),
              ("level", "INTEGER DEFAULT 1"), ("optout_ts", "TEXT")),
    "notifications": (("kind", "TEXT"), ("text", "TEXT"), ("attempts", "INTEGER DEFAULT 0"),
                      ("ts_queued", "TEXT")),
}


def iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="milliseconds")


def epoch(iso_text: str | None) -> float | None:
    if not iso_text:
        return None
    return datetime.fromisoformat(iso_text).timestamp()


class Store:
    def __init__(self, path: str, people_path: str | None = None):
        """people_path: the database that holds the people signed up for phone alerts, when it is
        not this one. A replay keeps its readings apart (data/replay.sqlite) but shares the people
        in data/co2monitor.sqlite, so nobody has to sign up twice."""
        self.path = path
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        for table, columns in ADDED_COLUMNS.items():
            have = {row[1] for row in self._db.execute("PRAGMA table_info(%s)" % table)}
            for name, decl in columns:
                if name not in have:
                    self._db.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, decl))
        self._db.commit()
        self.people_path = None
        if people_path and os.path.abspath(people_path) != os.path.abspath(path):
            Store(people_path).close()               # create it, or bring an older file up to date
            self.people_path = os.path.abspath(people_path)
            self._db.execute("ATTACH DATABASE ? AS people", (self.people_path,))
        self._u = "people.users" if self.people_path else "main.users"
        self._open = {}          # key ("device" / "link") -> alarm_id of the alarm still on
        self._closed = {}        # key -> alarm_id of the last alarm that ended

    def open_alarm_id(self, key: str):
        """The alarm_id of the alarm still on for this key ("device" or "link"), or None."""
        return self._open.get(key)

    # -- writes (ingest thread) ----------------------------------------------------------------
    def add_reading(self, now: float, s: dict, quality: str) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO readings (ts_utc, t_board, ppm, cr1, alarm, display, acked, quality, fw) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (iso(now), s.get("t"), s.get("ppm"), s.get("cr1"), s.get("alarm"), s.get("show"),
                 int(bool(s.get("acked"))), quality, s.get("fw")))
            self._db.commit()
            return cur.lastrowid

    def drop_reading(self, rowid: int) -> None:
        with self._lock:
            self._db.execute("DELETE FROM readings WHERE id = ?", (rowid,))
            self._db.commit()

    def add_device_event(self, now: float, text: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO device_events (ts_utc, text) VALUES (?, ?)", (iso(now), text))
            self._db.commit()

    def apply(self, event: dict) -> None:
        """Write one event from rules_engine.Monitor."""
        with self._lock:
            kind = event["type"]
            if kind == "alarm_raised":
                cur = self._db.execute(
                    "INSERT INTO alarm_events (priority, source, ts_raised, reason, ppm_at_raise) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (event["priority"], event["key"], iso(event["ts"]), event.get("reason"), event.get("ppm")))
                self._open[event["key"]] = cur.lastrowid
            elif kind == "alarm_cleared":
                alarm_id = self._open.pop(event["key"], None)
                if alarm_id is not None:
                    self._closed[event["key"]] = alarm_id
                    self._db.execute("UPDATE alarm_events SET ts_cleared = ? WHERE alarm_id = ?",
                                     (iso(event["ts"]), alarm_id))
            elif kind == "alarm_reason":
                alarm_id = self._open.get(event["key"])
                if alarm_id is not None:
                    self._db.execute("UPDATE alarm_events SET reason = ? WHERE alarm_id = ?",
                                     (event["reason"], alarm_id))
            elif kind == "ack":
                self._db.execute(
                    "INSERT INTO acks (alarm_id, ts, user_id, method, confirmed, ts_confirmed) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (self._closed.get("device") if event.get("key") == "device_cleared" else self._open.get(event.get("key")),
                     iso(event["ts"]), event.get("who"), event.get("method"),
                     int(bool(event.get("confirmed"))), iso(event.get("confirmed_ts"))))
            self._db.commit()

    # -- message recipients and messages (the notifier) ------------------------------------------
    def save_user(self, now: float, name: str, role: str, channel: str, phone: str | None,
                  telegram: str | None, apikey: str | None, level: int) -> int:
        """Sign someone up, with the time they agreed. Signing up again with the same app and
        number (or Telegram name) updates that entry instead of adding a second one."""
        with self._lock:
            if channel == "telegram":
                row = self._db.execute("SELECT user_id FROM %s WHERE channel = ? AND telegram = ?" % self._u,
                                       (channel, telegram)).fetchone()
            else:
                row = self._db.execute("SELECT user_id FROM %s WHERE channel = ? AND phone_e164 = ?" % self._u,
                                       (channel, phone)).fetchone()
            values = (name, role, channel, phone, telegram, apikey, level, iso(now))
            if row is None:
                cur = self._db.execute(
                    ("INSERT INTO %s (name, role, channel, phone_e164, telegram, apikey, level, optin_ts, "
                     "active, optout_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, NULL)" % self._u), values)
                user_id = cur.lastrowid
            else:
                user_id = row[0]
                self._db.execute(
                    ("UPDATE %s SET name = ?, role = ?, channel = ?, phone_e164 = ?, telegram = ?, apikey = ?, "
                     "level = ?, optin_ts = ?, active = 1, optout_ts = NULL WHERE user_id = ?" % self._u), values + (user_id,))
            self._db.commit()
            return user_id

    def set_user_active(self, now: float, user_id: int, active: bool) -> bool:
        """Stop someone's messages (the record of their consent stays), or start them again."""
        with self._lock:
            if active:
                cur = self._db.execute("UPDATE %s SET active = 1, optin_ts = ?, optout_ts = NULL WHERE user_id = ?" % self._u,
                                       (iso(now), user_id))
            else:
                cur = self._db.execute("UPDATE %s SET active = 0, optout_ts = ? WHERE user_id = ?" % self._u,
                                       (iso(now), user_id))
            self._db.commit()
            return cur.rowcount == 1

    def users(self) -> list:
        """Everyone signed up, with their keys: for the notifier only, never sent to a browser."""
        db = self._read()
        try:
            rows = db.execute("SELECT * FROM %s ORDER BY user_id" % self._u).fetchall()
        finally:
            db.close()
        out = []
        for r in rows:
            u = dict(r)
            u["optin_ts"], u["optout_ts"] = epoch(u.get("optin_ts")), epoch(u.get("optout_ts"))
            u["level"] = u.get("level") or 1
            out.append(u)
        return out

    def add_notification(self, now: float, alarm_id, user_id: int, kind: str, text: str, provider: str,
                         status: str) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO notifications (alarm_id, user_id, kind, text, provider, status, attempts, ts_queued) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?)", (alarm_id, user_id, kind, text, provider, status, iso(now)))
            self._db.commit()
            return cur.lastrowid

    def update_notification(self, note_id: int, status: str, attempts: int, sent: float | None = None,
                            error: str | None = None) -> None:
        with self._lock:
            self._db.execute("UPDATE notifications SET status = ?, attempts = ?, ts_sent = COALESCE(?, ts_sent), "
                             "error = ? WHERE id = ?", (status, attempts, iso(sent), error, note_id))
            self._db.commit()

    def messages_since(self, user_id: int, since: float) -> int:
        """How many messages went (or were tried) to this person since then: the flood guard."""
        db = self._read()
        try:
            return db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND ts_queued >= ? "
                              "AND status NOT LIKE 'not sent%'", (user_id, iso(since))).fetchone()[0]
        finally:
            db.close()

    def told(self, alarm_id) -> set:
        """Who actually received a message about this alarm (CallMeBot accepted it)."""
        db = self._read()
        try:
            rows = db.execute("SELECT DISTINCT user_id FROM notifications WHERE alarm_id = ? AND status = 'sent' "
                              "AND kind IN ('alarm', 'escalation')", (alarm_id,)).fetchall()
        finally:
            db.close()
        return {r[0] for r in rows}

    def last_messages(self) -> dict:
        """user_id -> the last message to that person: what it was, how it went."""
        db = self._read()
        try:
            rows = db.execute("SELECT user_id, kind, status, error, ts_queued FROM notifications WHERE id IN "
                              "(SELECT MAX(id) FROM notifications GROUP BY user_id)").fetchall()
        finally:
            db.close()
        return {r["user_id"]: {"kind": r["kind"], "status": r["status"], "error": r["error"],
                               "ts": epoch(r["ts_queued"])} for r in rows}

    def notifications(self, limit: int = 20) -> list:
        db = self._read()
        try:
            rows = db.execute(
                "SELECT n.id, n.alarm_id, n.kind, n.status, n.attempts, n.error, n.ts_queued, n.ts_sent, "
                "u.name, u.channel FROM notifications n LEFT JOIN %s u ON u.user_id = n.user_id "
                "ORDER BY n.id DESC LIMIT ?" % self._u, (limit,)).fetchall()
        finally:
            db.close()
        return [{"id": r["id"], "alarm_id": r["alarm_id"], "kind": r["kind"], "status": r["status"],
                 "attempts": r["attempts"], "error": r["error"], "queued": epoch(r["ts_queued"]),
                 "sent": epoch(r["ts_sent"]), "who": r["name"], "channel": r["channel"]} for r in rows]

    def close(self) -> None:
        """At shutdown. SQLite then folds the write-ahead log into the .sqlite file, so that file
        alone holds everything (worth knowing before copying it anywhere)."""
        with self._lock:
            try:
                self._db.close()
            except sqlite3.Error:
                pass

    def close_open_alarms(self, now: float) -> None:
        """At shutdown: the service stops watching, so its open records end here."""
        with self._lock:
            for alarm_id in self._open.values():
                self._db.execute("UPDATE alarm_events SET ts_cleared = ? WHERE alarm_id = ? AND ts_cleared IS NULL",
                                 (iso(now), alarm_id))
            self._open = {}
            self._db.commit()

    # -- reads (web requests) ------------------------------------------------------------------
    def _read(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        if self.people_path:
            db.execute("ATTACH DATABASE ? AS people", (self.people_path,))
        return db

    def readings_since(self, since_epoch: float) -> list:
        db = self._read()
        try:
            rows = db.execute("SELECT ts_utc, ppm, display, cr1 FROM readings WHERE ts_utc >= ? ORDER BY id",
                              (iso(since_epoch),)).fetchall()
        finally:
            db.close()
        return [[epoch(r["ts_utc"]), r["ppm"], r["display"], r["cr1"]] for r in rows]

    def alarms(self, limit: int = 20) -> list:
        db = self._read()
        try:
            rows = db.execute("SELECT * FROM alarm_events ORDER BY alarm_id DESC LIMIT ?", (limit,)).fetchall()
            out = []
            for r in rows:
                acks = db.execute("SELECT ts, user_id, method, confirmed FROM acks WHERE alarm_id = ? ORDER BY ack_id",
                                  (r["alarm_id"],)).fetchall()
                notes = db.execute("SELECT n.kind, n.status, n.ts_queued, u.name FROM notifications n "
                                   "LEFT JOIN %s u ON u.user_id = n.user_id WHERE n.alarm_id = ? ORDER BY n.id" % self._u,
                                   (r["alarm_id"],)).fetchall()
                out.append({
                    "alarm_id": r["alarm_id"], "priority": r["priority"], "source": r["source"],
                    "raised": epoch(r["ts_raised"]), "cleared": epoch(r["ts_cleared"]),
                    "reason": r["reason"], "ppm_at_raise": r["ppm_at_raise"],
                    "acks": [{"ts": epoch(a["ts"]), "who": a["user_id"], "method": a["method"],
                              "confirmed": bool(a["confirmed"])} for a in acks],
                    "messages": [{"kind": n["kind"], "status": n["status"], "ts": epoch(n["ts_queued"]),
                                  "who": n["name"]} for n in notes],
                })
        finally:
            db.close()
        return out

    def counts(self) -> dict:
        db = self._read()
        try:
            return {t: db.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                    for t in ("readings", "alarm_events", "acks", "device_events")}
        finally:
            db.close()
