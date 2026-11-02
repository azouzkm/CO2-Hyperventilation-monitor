"""Messages to phones (interface IF-9), through CallMeBot: WhatsApp, Signal or Telegram.

When (workshop slide 11; the numbers are in config.json, "notify"):
    Critical    a message at once to everyone signed up as "first to be told", and again at 120 s
                if nobody has acknowledged it, this time to the backups too ("escalate at 120 s")
    Advisory    a message if it lasts 60 s
    Technical   a message if it lasts 60 s: a sensor or link fault means the patient is not being
                watched. Not for "no data yet" at start-up, before the monitor was ever plugged in
    Ended       one short follow-up, when an alarm ends, to whoever really received a message about it
An acknowledgement (bedside button or dashboard) stops the escalation and any message still waiting.

How: one HTTPS request to CallMeBot per message. CallMeBot's free service only lets people message
themselves, so each person signs up with their own key (or, for Telegram, by starting its bot).
When CallMeBot cannot be reached, a message is tried 3 times (at once, after 10 s, after 30 s); a
refused key or sign-up fails at once, since trying again would not help. Every message and its
outcome is a row in the notifications table, and failures show on the dashboard. CallMeBot gives no
delivery receipt, so "sent" means that it accepted the message. At most 10 messages per person in
10 minutes, so a fault that comes and goes cannot flood anyone's phone.

The board never waits for any of this: its light and sound do not depend on a phone.
No patient identifiers in any message.
"""
from __future__ import annotations

import heapq
import html
import itertools
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

PROVIDER = "callmebot"
CHANNELS = {"whatsapp": "WhatsApp", "signal": "Signal", "telegram": "Telegram"}
LEVELS = {1: "first to be told", 2: "backup: only when a critical alarm is not acknowledged in time"}
DEFAULTS = {"advisory_after_s": 60.0, "technical_after_s": 60.0, "escalate_after_s": 120.0,
            "retry_s": [10.0, 30.0], "send_resolved": True, "max_per_10_min": 10}
REASON_WAIT_S = 2.0      # older firmware prints the reason for a critical alarm in a banner just after
HEAD = "Team 6 CO2 monitor (bench test)"
# CallMeBot does not document its answers; these words in one mean the key or the sign-up is wrong
REFUSED = ("invalid", "not authori", "unauthori", "not allowed", "denied", "wrong", "blocked",
           "not found", "not registered", "error")
WORD = {"CRITICAL": "critical", "ADVISORY": "advisory", "TECHNICAL": "technical"}


# ---- CallMeBot -----------------------------------------------------------------------------------
def callmebot_url(user: dict, text: str) -> str:
    channel = user.get("channel")
    if channel == "whatsapp":
        base = "https://api.callmebot.com/whatsapp.php"
        params = (("phone", user["phone_e164"]), ("text", text), ("apikey", user["apikey"]))
    elif channel == "signal":
        base = "https://signal.callmebot.com/signal/send.php"
        params = (("phone", user["phone_e164"]), ("apikey", user["apikey"]), ("text", text))
    elif channel == "telegram":
        base = "https://api.callmebot.com/text.php"
        params = (("user", user["telegram"]), ("text", text))
    else:
        raise ValueError("unknown messaging app: %r" % (channel,))
    return base + "?" + "&".join("%s=%s" % (k, urllib.parse.quote(str(v), safe="@")) for k, v in params)


def plain(page: str) -> str:
    """CallMeBot answers with a small web page; keep its words."""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _ssl_context():
    try:                                    # certifi (installed by tools/dashboard.sh) carries the
        import certifi                      # certificates some Mac Pythons lack
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


class CallMeBot:
    name = PROVIDER

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self._ctx = None

    def send(self, user: dict, text: str):
        """Returns (sent, worth trying again, what happened)."""
        if self._ctx is None:
            self._ctx = _ssl_context()
        req = urllib.request.Request(callmebot_url(user, text), headers={"User-Agent": "team6-co2-monitor/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as r:
                status, page = r.status, r.read(4000).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return False, e.code >= 500, "CallMeBot answered HTTP %d" % e.code
        except (urllib.error.URLError, OSError) as e:
            return False, True, "could not reach CallMeBot (%s)" % (getattr(e, "reason", None) or e,)
        said = plain(page)[:200]
        if status != 200 or any(w in said.lower() for w in REFUSED):
            return False, False, "CallMeBot answered: " + (said or "HTTP %d" % status)
        return True, False, said or "accepted"


# ---- signing up ----------------------------------------------------------------------------------
PHONE = re.compile(r"^\+[1-9]\d{7,14}$")
TELEGRAM = re.compile(r"^@[A-Za-z0-9_]{5,32}$")
APIKEY = re.compile(r"^[A-Za-z0-9-]{3,64}$")


def validate_signup(form: dict):
    """(True, clean values) or (False, what to fix), in words for the sign-up page."""
    name = str(form.get("name") or "").strip()[:40]
    role = str(form.get("role") or "").strip()[:40]
    channel = str(form.get("channel") or "").strip().lower()
    try:
        level = int(form.get("level", 1))
    except (TypeError, ValueError):
        level = 0
    if not name:
        return False, "Write your name or initials."
    if channel not in CHANNELS:
        return False, "Choose WhatsApp, Signal or Telegram."
    if level not in LEVELS:
        return False, "Choose which messages you want."
    phone = telegram = apikey = None
    if channel == "telegram":
        telegram = str(form.get("telegram") or "").strip()
        if telegram and not telegram.startswith("@"):
            telegram = "@" + telegram
        if not TELEGRAM.match(telegram):
            return False, "Write your Telegram username, for example @abdel_m (Telegram, Settings, Username)."
    else:
        phone = re.sub(r"[\s().-]", "", str(form.get("phone") or ""))
        if phone.startswith("00"):
            phone = "+" + phone[2:]
        if not PHONE.match(phone):
            return False, "Write your number with its country code, for example +1 514 555 0123."
        apikey = str(form.get("apikey") or "").strip()
        if not APIKEY.match(apikey):
            return False, "Paste the API key that CallMeBot sent you on %s." % CHANNELS[channel]
    if form.get("consent") is not True:
        return False, "Tick the box to agree to receive the messages."
    return True, {"name": name, "role": role, "channel": channel, "level": level,
                  "phone": phone, "telegram": telegram, "apikey": apikey}


def mask_phone(phone: str | None) -> str:
    if not phone:
        return ""
    return phone[:2] + "•" * max(0, len(phone) - 6) + phone[-4:]


def public_user(u: dict, last: dict | None = None) -> dict:
    """What a browser may see about a person: never the key, and only the end of the number."""
    channel = u.get("channel")
    return {"user_id": u["user_id"], "name": u["name"], "role": u.get("role") or "",
            "channel": channel, "app": CHANNELS.get(channel, "?"),
            "address": u.get("telegram") if channel == "telegram" else mask_phone(u.get("phone_e164")),
            "level": u.get("level") or 1, "level_text": LEVELS.get(u.get("level") or 1, ""),
            "optin_ts": u.get("optin_ts"), "optout_ts": u.get("optout_ts"), "active": bool(u.get("active")),
            "last": last}


def usable(u: dict) -> bool:
    if u.get("channel") == "telegram":
        return bool(u.get("telegram"))
    return u.get("channel") in CHANNELS and bool(u.get("phone_e164")) and bool(u.get("apikey"))


# ---- the words -----------------------------------------------------------------------------------
def _hm(t: float) -> str:
    return time.strftime("%H:%M", time.localtime(t))


def _span(s: float) -> str:
    s = int(round(s))
    return "%d min" % (s // 60) if s >= 60 and s % 60 == 0 else "%d s" % s


def message(kind: str, a: dict, now: float, cfg: dict) -> str:
    when = _hm(a["raised"])
    reason = (a.get("reason") or "").strip().rstrip(".")
    if kind == "escalation":
        return ("%s: the CRITICAL alarm from %s is still not acknowledged after %s. %s. Go to the monitor now."
                % (HEAD, when, _span(cfg["escalate_after_s"]), reason or "CO2 lost"))
    if kind == "resolved":
        return "%s: the %s alarm from %s has ended (%s)." % (HEAD, WORD.get(a["priority"], "earlier"), when, _hm(now))
    if a["priority"] == "CRITICAL":
        return ("%s: CRITICAL alarm at %s. %s. Check the patient and the airway, then acknowledge at the "
                "monitor or on the dashboard." % (HEAD, when, reason or "CO2 lost"))
    if a["priority"] == "ADVISORY":
        return "%s: advisory alarm for %s now, since %s. %s." % (HEAD, _span(now - a["raised"]), when,
                                                                  reason or "CO2 falling")
    if a["key"] == "link":
        return ("%s: technical alarm. No data from the monitor since %s. Check the USB cable, which also "
                "powers the monitor. The patient is not being watched." % (HEAD, when))
    return ("%s: technical alarm for %s now, since %s: %s. The patient is not being watched until it is "
            "fixed." % (HEAD, _span(now - a["raised"]), when, reason or "sensor problem"))


def test_text(level: int) -> str:
    return ("%s: test message. You are signed up for its alarm messages (%s). No patient information is "
            "ever sent. Stop them any time on the dashboard's Phone alerts page." % (HEAD, LEVELS.get(level, "")))


# ---- the notifier --------------------------------------------------------------------------------
class Notifier:
    """Decides who is told what and when, and sends the messages from a background thread.

    on_event() and tick() are called with the service's lock held; the sending thread only touches
    its own queue and the store (which has its own lock)."""

    def __init__(self, store, sender, cfg: dict | None = None, clock=time.time, dry_run: str | None = None,
                 echo=print):
        self.cfg = dict(DEFAULTS)
        self.cfg.update(cfg or {})
        self.store, self.sender, self.clock, self.echo = store, sender, clock, echo
        self.dry_run = dry_run         # None, "replay" (alarm messages not sent) or "--no-messages" (none sent)
        self.open = {}                 # alarm_id -> what the notifier knows about it
        self.by_key = {}               # "device" / "link" -> alarm_id still on
        self._heap = []
        self._seq = itertools.count()
        self._cv = threading.Condition()
        self._stopping = False
        self._thread = None

    # -- who -----------------------------------------------------------------------------------
    def recipients(self, levels) -> list:
        return [u for u in self.store.users()
                if u.get("active") and u.get("optin_ts") and (u.get("level") or 1) in levels and usable(u)]

    # -- what the rules engine reports -----------------------------------------------------------
    def on_event(self, e: dict, alarm_id) -> None:
        kind = e["type"]
        now = e["ts"] if e.get("ts") is not None else self.clock()
        if kind == "alarm_raised" and alarm_id is not None:
            priority = e["priority"]
            if priority == "CRITICAL":
                wait = 0.0 if e.get("reason") else REASON_WAIT_S
            elif priority == "ADVISORY":
                wait = float(self.cfg["advisory_after_s"])
            else:
                wait = float(self.cfg["technical_after_s"])
            self.open[alarm_id] = {"key": e["key"], "priority": priority, "raised": now,
                                   "reason": e.get("reason") or "", "due": now + wait,
                                   "first_done": bool(e.get("never")), "acked": False, "escalated": False,
                                   "told": set()}
            self.by_key[e["key"]] = alarm_id
        elif kind == "alarm_reason":
            a = self.open.get(self.by_key.get(e["key"]))
            if a is not None:
                a["reason"] = e.get("reason") or a["reason"]
                if a["priority"] == "CRITICAL" and not a["first_done"]:
                    a["due"] = min(a["due"], self.clock())
        elif kind == "alarm_cleared":
            alarm_id = self.by_key.pop(e["key"], None)
            a = self.open.pop(alarm_id, None)
            if a is not None and a["told"] and self.cfg["send_resolved"]:
                received = self.store.told(alarm_id)           # only those who really got the alarm
                for u in self.store.users():
                    if u["user_id"] in received and u.get("active"):
                        self._queue(alarm_id, u, "resolved", message("resolved", a, now, self.cfg), now)
        elif kind == "ack":
            alarm_id = self.by_key.get(e.get("key")) if e.get("key") in ("device", "link") else None
            if alarm_id in self.open:
                self.open[alarm_id]["acked"] = True

    def tick(self, now: float) -> None:
        for alarm_id, a in list(self.open.items()):
            if not a["first_done"] and now >= a["due"]:
                a["first_done"] = True
                if not a["acked"]:                         # acknowledged already: someone is on it
                    for u in self.recipients((1,)):
                        self._queue(alarm_id, u, "alarm", message("alarm", a, now, self.cfg), now)
            if (a["priority"] == "CRITICAL" and a["first_done"] and not a["escalated"] and not a["acked"]
                    and now >= a["raised"] + float(self.cfg["escalate_after_s"])):
                a["escalated"] = True
                for u in self.recipients((1, 2)):
                    self._queue(alarm_id, u, "escalation", message("escalation", a, now, self.cfg), now)

    def test(self, user: dict) -> None:
        """A test message, from the sign-up page."""
        self._queue(None, user, "test", test_text(user.get("level") or 1), self.clock())

    def mode(self) -> str | None:
        return self.dry_run

    # -- sending -------------------------------------------------------------------------------
    def _queue(self, alarm_id, user: dict, kind: str, text: str, now: float) -> None:
        if alarm_id in self.open and kind in ("alarm", "escalation"):
            self.open[alarm_id]["told"].add(user["user_id"])
        if self.dry_run == "--no-messages" or (self.dry_run == "replay" and kind != "test"):
            self.store.add_notification(now, alarm_id, user["user_id"], kind, text, PROVIDER,
                                        "not sent: " + self.dry_run)
            return
        if self.store.messages_since(user["user_id"], now - 600.0) >= int(self.cfg["max_per_10_min"]):
            self.store.add_notification(now, alarm_id, user["user_id"], kind, text, PROVIDER,
                                        "not sent: too many messages in 10 min")
            return
        note_id = self.store.add_notification(now, alarm_id, user["user_id"], kind, text, PROVIDER, "queued")
        self._push(now, (note_id, user, text, 1))

    def _push(self, due: float, item) -> None:
        with self._cv:
            heapq.heappush(self._heap, (due, next(self._seq), item))
            self._cv.notify()

    def send_due(self, now: float) -> int:
        """Send every message that is due by `now`. The thread calls this; tests call it directly."""
        done = 0
        while True:
            with self._cv:
                if not self._heap or self._heap[0][0] > now:
                    return done
                _, _, (note_id, user, text, attempt) = heapq.heappop(self._heap)
            try:
                sent, again, said = self.sender.send(user, text)
            except Exception as e:                         # a bug in sending must not stop the notifier
                sent, again, said = False, True, "error while sending: %r" % (e,)
            if sent:
                self.store.update_notification(note_id, "sent", attempt, sent=self.clock(), error=None)
            elif again and attempt <= len(self.cfg["retry_s"]):
                self.store.update_notification(note_id, "retrying", attempt, error=said)
                self._push(now + float(self.cfg["retry_s"][attempt - 1]), (note_id, user, text, attempt + 1))
            else:
                self.store.update_notification(note_id, "failed", attempt, error=said)
                self.echo("[dashboard] A message to %s could not be sent: %s" % (user.get("name"), said))
            done += 1

    def start(self) -> None:
        if self.dry_run == "--no-messages" or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="notifier")
        self._thread.start()

    def stop(self, wait: float = 3.0) -> None:
        with self._cv:
            self._stopping = True
            self._cv.notify()
        if self._thread is not None:
            self._thread.join(wait)
        with self._cv:
            left, self._heap = self._heap, []
        for _, _, (note_id, _user, _text, attempt) in left:
            self.store.update_notification(note_id, "failed", attempt - 1,
                                           error="the service stopped before it could be sent")

    def _run(self) -> None:
        while True:
            with self._cv:
                if self._stopping:
                    return
            self.send_due(self.clock())
            with self._cv:
                if self._stopping:
                    return
                wait = 1.0 if not self._heap else min(1.0, max(0.05, self._heap[0][0] - self.clock()))
                self._cv.wait(wait)
