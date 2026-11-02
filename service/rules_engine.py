"""The service's rules: what the dashboard shows and sounds, alarm records, acknowledgements, and the
link watchdog.

One alarm path. The board decides every patient alarm itself (firmware/lib/alarm.py) and keeps
alarming if the laptop or this service stops (as long as it has power). The service never re-decides those
alarms, so the board and the dashboard cannot disagree about what counts as an alarm. It adds what
only the laptop can know:

    LINK LOST   no reading from the board for LINK_TIMEOUT_S: a technical alarm (CR-3), never shown as
                apnoea. If the board's last word was a critical alarm that nobody had acknowledged,
                the dashboard keeps showing and sounding it (a fault never hides a patient alarm).
    Alarm log   every alarm the board raises becomes a record with when it started and ended.
    Acknowledge who acknowledged, how (bedside button or dashboard) and when. The dashboard's
                button is sent to the board, which silences itself and confirms in its next reading.
                Without that confirmation (older firmware, or the link down), the dashboard still
                silences its own sound for SILENCE_S and records the acknowledgement as unconfirmed.

Pure Python, no I/O: feed it readings and clock ticks, and it returns events for the store.
"""
from __future__ import annotations

SOUNDING = ("CRITICAL", "ADVISORY", "TECHNICAL")   # alarm states with a sound
SOUND_OF = {"CRITICAL": "critical", "ADVISORY": "advisory", "TECHNICAL": "technical"}
LINK_TIMEOUT_S = 5.0     # the board sends a reading every second (every 1.5 s while the sensor is silent)
SILENCE_S = 120.0        # same as the board (firmware/lib/alarm.py)
ACK_CONFIRM_S = 5.0      # how long to wait for the board to confirm a dashboard acknowledgement


class Monitor:
    def __init__(self, started_at: float, link_timeout_s: float = LINK_TIMEOUT_S,
                 silence_s: float = SILENCE_S, ack_confirm_s: float = ACK_CONFIRM_S):
        self.started_at = started_at
        self.link_timeout_s = link_timeout_s
        self.silence_s = silence_s
        self.ack_confirm_s = ack_confirm_s
        self.last = None              # the last reading (dict from parse.parse_line)
        self.before_last = None       # the one before it
        self.cleared_at = None        # when the board's last alarm ended
        self.last_rx = None           # laptop time it arrived
        self.fw = None                # firmware version the board reported
        self.device_alarm = None      # open alarm raised by the board: {"priority", "since", "reason"}
        self.link_alarm = None        # open link-lost alarm
        self.display_since = started_at
        self.cr1_since = None
        self.pending = []             # dashboard acknowledgements sent to the board, not yet confirmed
        self.silenced_until = 0.0     # the dashboard's own silence
        self.last_ack = None
        self.alarm_banner = None      # text firmware: the reason from the last "ALARM ..." banner

    # -- what the board sends ------------------------------------------------------------------
    def on_boot(self, fw: str) -> None:
        self.fw = fw

    def on_banner(self, now: float, text: str) -> list:
        """Banner lines matter for older firmware, which printed no JSON."""
        out = []
        if text.startswith("ALARM ") and ":" in text:
            head, reason = text.split(":", 1)
            self.alarm_banner = reason.strip()
            a = self.device_alarm
            # older firmware prints the reading before the banner that explains it
            if a is not None and a.get("reason_pending") and head == "ALARM " + a["priority"]:
                a["reason"], a["reason_pending"] = self.alarm_banner, False
                out.append({"type": "alarm_reason", "key": "device", "reason": self.alarm_banner})
        if text == "BUTTON pressed" and (self.last is None or self.last.get("source") == "text"):
            # older firmware prints the press after the reading that already shows its effect
            out += self._bedside_ack(now, self.before_last, self.last)
        return out

    def on_sample(self, now: float, s: dict) -> list:
        out = []
        prev = self.last
        if s.get("fw"):
            self.fw = s["fw"]
        if self.link_alarm is not None:
            out.append({"type": "alarm_cleared", "key": "link", "ts": now})
            self.link_alarm = None
        if prev is None or prev.get("cr1") != s.get("cr1"):
            self.cr1_since = now
        if prev is None or prev.get("show") != s.get("show"):
            self.display_since = now
        # acknowledgements first, so they attach to the alarm that was on when they happened
        if s.get("press"):
            out += self._bedside_ack(now, prev, s)
        for _ in range(s.get("dash_ack") or 0):
            if self.pending:
                who, asked = self.pending.pop(0)
                out.append(self._ack(now, "dashboard", who, True, asked))
        self.before_last, self.last, self.last_rx = self.last, s, now

        # the board's own alarm becomes a record
        alarm = s.get("alarm")
        if alarm in SOUNDING:
            if self.device_alarm is None or self.device_alarm["priority"] != alarm:
                if self.device_alarm is not None:
                    out.append({"type": "alarm_cleared", "key": "device", "ts": now})
                reason = s.get("why") or ""
                self.device_alarm = {"priority": alarm, "since": now, "reason": reason,
                                     "reason_pending": not reason}
                self.silenced_until = 0.0          # a new alarm is heard at once
                out.append({"type": "alarm_raised", "key": "device", "priority": alarm, "ts": now,
                            "reason": reason, "ppm": s.get("ppm")})
        elif self.device_alarm is not None:
            out.append({"type": "alarm_cleared", "key": "device", "ts": now})
            self.device_alarm = None
            self.cleared_at = now
        return out

    # -- the laptop's clock --------------------------------------------------------------------
    def tick(self, now: float) -> list:
        out = []
        quiet_since = self.last_rx if self.last_rx is not None else self.started_at
        if self.link_alarm is None and now - quiet_since > self.link_timeout_s:
            reason = ("no data from the monitor for %d s: check the USB cable" % (now - quiet_since)
                      if self.last_rx is not None else "no data from the monitor yet: is it plugged in?")
            self.link_alarm = {"priority": "TECHNICAL", "since": now, "reason": reason}
            if self.device_alarm is None or self.device_alarm["priority"] != "CRITICAL":
                self.silenced_until = 0.0
            out.append({"type": "alarm_raised", "key": "link", "priority": "TECHNICAL", "ts": now,
                        "reason": reason, "ppm": None,
                        "never": self.last_rx is None})     # not yet plugged in: nothing was being watched
        while self.pending and now - self.pending[0][1] > self.ack_confirm_s:
            who, asked = self.pending.pop(0)            # the board never confirmed it
            out.append(self._ack(now, "dashboard", who, False, asked))
        return out

    # -- the dashboard's acknowledge button ----------------------------------------------------
    def request_ack(self, now: float, who: str) -> dict:
        """Returns {"ok", "send": text for the board or None, "message"}; acks come back as events."""
        who = (who or "").strip()[:20]
        if not who:
            return {"ok": False, "send": None, "message": "Type your initials first."}
        view = self.view(now)
        if view["sound"] is None and view["display"] not in ("CRITICAL BACK",):
            return {"ok": False, "send": None, "message": "There is no alarm to acknowledge."}
        self.silenced_until = now + self.silence_s
        if view["link"] == "live" and (self.last or {}).get("alarm") == "CRITICAL":
            self.pending.append((who, now))
            return {"ok": True, "send": "ACK\n", "message": "Acknowledged. Waiting for the monitor to confirm."}
        self.pending.append((who, now))             # recorded as unconfirmed by tick()
        return {"ok": True, "send": None,
                "message": "Sound off on this screen for %d s. The monitor itself can only be "
                           "acknowledged at its button for this alarm." % self.silence_s}

    def _bedside_ack(self, now: float, prev: dict | None = None, cur: dict | None = None) -> list:
        """A press of the board's own button while an alarm was on."""
        before = (prev if prev is not None else self.last) or {}
        if before.get("alarm") in SOUNDING or (cur or {}).get("alarm") in SOUNDING:
            return [self._ack(now, "bedside button", "bedside", True, now)]
        return []

    def _ack(self, now: float, method: str, who: str, confirmed: bool, asked: float) -> dict:
        self.last_ack = {"who": who, "method": method, "ts": asked, "confirmed": confirmed}
        if self.device_alarm is not None:
            key = "device"
        elif self.cleared_at is not None and now - self.cleared_at <= 2.0:
            key = "device_cleared"                     # the press that just cleared it
        elif self.link_alarm is not None:
            key = "link"
        else:
            key = None
        return {"type": "ack", "key": key, "method": method, "who": who, "confirmed": confirmed,
                "ts": asked, "confirmed_ts": now if confirmed else None}

    # -- what the dashboard should show and sound now ------------------------------------------
    def view(self, now: float) -> dict:
        s = self.last or {}
        if self.last_rx is None:
            link = "lost" if self.link_alarm is not None else "waiting"
        elif now - self.last_rx > self.link_timeout_s:
            link = "lost"
        else:
            link = "live"
        show = s.get("show")
        if link == "live":
            display = show or "UNKNOWN"
        elif show in ("CRITICAL", "CRITICAL BACK") and not s.get("acked"):
            display = show                           # keep the patient alarm; the link banner says why
        else:
            display = "LINK LOST" if link == "lost" else "WAITING"
        if display == "LINK LOST":
            sound = "technical"
        elif display in ("CRITICAL", "CRITICAL BACK"):
            sound = "critical"
        else:
            sound = SOUND_OF.get(display)
        if s.get("acked") and display.startswith("CRITICAL"):
            sound = None
        if sound is not None and now < self.silenced_until:
            sound = None
        alarm = self.device_alarm if self.device_alarm is not None else self.link_alarm
        return {
            "link": link,
            "since_rx_s": None if self.last_rx is None else round(now - self.last_rx, 1),
            "display": display,
            "display_since": self.display_since,
            "sound": sound,
            "silenced_until": self.silenced_until if now < self.silenced_until else None,
            "ppm": s.get("ppm"),
            "cr1": s.get("cr1"),
            "cr1_why": s.get("cr1_why"),
            "cr1_since": self.cr1_since,
            "why": s.get("why") or (alarm or {}).get("reason"),
            "alarm": s.get("alarm"),
            "acked": bool(s.get("acked")),
            "t_board": s.get("t"),
            "fw": self.fw,
            "link_alarm": self.link_alarm,
            "device_alarm": self.device_alarm,
            "last_ack": self.last_ack,
            "waiting_for_confirm": len(self.pending),
        }
