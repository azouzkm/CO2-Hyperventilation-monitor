"""Phone alerts (service/notifier.py): when a message goes, to whom, what it says, and what happens
when CallMeBot cannot be reached or refuses. No network: a fake CallMeBot records what would have
been sent, and the real sender is checked against fake answers.

Run from the repository root:   python -m pytest tests/
"""
import io
import os
import sqlite3
import sys
import urllib.error

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from service import notifier as nt  # noqa: E402
from service.notifier import Notifier, callmebot_url, plain, public_user, validate_signup  # noqa: E402
from service.store import Store  # noqa: E402


class FakeBot:
    def __init__(self, answers=None):
        self.sent = []
        self.answers = list(answers or [])

    def send(self, user, text):
        self.sent.append((user["name"], text))
        return self.answers.pop(0) if self.answers else (True, False, "Message queued")


def setup(tmp_path, answers=None, dry_run=None, **cfg):
    st = Store(str(tmp_path / "n.sqlite"))
    bot = FakeBot(answers)
    now = [1000.0]
    said = []
    n = Notifier(st, bot, cfg, clock=lambda: now[0], dry_run=dry_run, echo=said.append)
    return st, bot, n, now, said


def sign_up(st, name, level=1, channel="whatsapp", phone="+15145550123"):
    form = {"name": name, "channel": channel, "level": level, "consent": True}
    if channel == "telegram":
        form["telegram"] = "@" + name.lower() + "_test"
    else:
        form.update(phone=phone, apikey="123456")
    ok, v = validate_signup(form)
    assert ok, v
    return st.save_user(500.0, v["name"], v["role"], v["channel"], v["phone"], v["telegram"], v["apikey"], v["level"])


def raise_(st, n, key, priority, ts, reason="CO2 lost: fell 108 ppm from 1814 in under 20 s", never=False):
    e = {"type": "alarm_raised", "key": key, "priority": priority, "ts": ts, "reason": reason, "ppm": 900,
         "never": never}
    st.apply(e)
    n.on_event(e, st.open_alarm_id(key))


def clear(st, n, key, ts):
    e = {"type": "alarm_cleared", "key": key, "ts": ts}
    st.apply(e)
    n.on_event(e, None)


def ack(st, n, key, ts):
    e = {"type": "ack", "key": key, "method": "bedside button", "who": "bedside", "confirmed": True, "ts": ts,
         "confirmed_ts": ts}
    st.apply(e)
    n.on_event(e, None)


def run(n, now, t0, t1):
    for t in range(int(t0), int(t1) + 1):
        now[0] = float(t)
        n.tick(now[0])
        n.send_due(now[0])


# ---- the URLs --------------------------------------------------------------------------------------
def test_urls_for_each_app():
    text = "CRITICAL at 22:41. CO2 lost\nCheck"
    wa = callmebot_url({"channel": "whatsapp", "phone_e164": "+15145550123", "apikey": "123456"}, text)
    assert wa == ("https://api.callmebot.com/whatsapp.php?phone=%2B15145550123"
                  "&text=CRITICAL%20at%2022%3A41.%20CO2%20lost%0ACheck&apikey=123456")
    sg = callmebot_url({"channel": "signal", "phone_e164": "+15145550123", "apikey": "abc"}, "hi there")
    assert sg == "https://signal.callmebot.com/signal/send.php?phone=%2B15145550123&apikey=abc&text=hi%20there"
    tg = callmebot_url({"channel": "telegram", "telegram": "@abdel_m"}, "hi & bye")
    assert tg == "https://api.callmebot.com/text.php?user=@abdel_m&text=hi%20%26%20bye"


# ---- when, and to whom -----------------------------------------------------------------------------
def test_a_critical_alarm_goes_at_once_to_the_first_list_only(tmp_path):
    st, bot, n, now, _ = setup(tmp_path)
    sign_up(st, "AM", level=1)
    sign_up(st, "NW", level=2, phone="+15145550124")
    raise_(st, n, "device", "CRITICAL", 1000.0)
    run(n, now, 1000, 1001)
    assert [who for who, _ in bot.sent] == ["AM"]
    assert "CRITICAL alarm at" in bot.sent[0][1] and "fell 108 ppm" in bot.sent[0][1]
    assert "patient" in bot.sent[0][1].lower() and "name" not in bot.sent[0][1].lower()


def test_an_unacknowledged_critical_escalates_at_120_s_to_the_backups_too(tmp_path):
    st, bot, n, now, _ = setup(tmp_path)
    sign_up(st, "AM", level=1)
    sign_up(st, "NW", level=2, phone="+15145550124")
    raise_(st, n, "device", "CRITICAL", 1000.0)
    run(n, now, 1000, 1119)
    assert len(bot.sent) == 1
    run(n, now, 1120, 1121)
    assert sorted(who for who, _ in bot.sent[1:]) == ["AM", "NW"]
    assert all("still not acknowledged after 2 min" in text for _, text in bot.sent[1:])
    clear(st, n, "device", 1300.0)                     # both were told, so both hear that it ended
    run(n, now, 1300, 1301)
    assert sorted(who for who, text in bot.sent if "has ended" in text) == ["AM", "NW"]


def test_an_acknowledged_critical_does_not_escalate_and_ends_with_one_follow_up(tmp_path):
    st, bot, n, now, _ = setup(tmp_path)
    sign_up(st, "AM", level=1)
    sign_up(st, "NW", level=2, phone="+15145550124")
    raise_(st, n, "device", "CRITICAL", 1000.0)
    run(n, now, 1000, 1030)
    ack(st, n, "device", 1030.0)
    run(n, now, 1031, 1300)
    assert len(bot.sent) == 1                          # no escalation after an acknowledgement
    clear(st, n, "device", 1300.0)
    run(n, now, 1300, 1301)
    assert [who for who, _ in bot.sent] == ["AM", "AM"]
    assert "the critical alarm from" in bot.sent[1][1] and "has ended" in bot.sent[1][1]


def test_advisory_and_technical_alarms_wait_a_minute(tmp_path):
    st, bot, n, now, _ = setup(tmp_path)
    sign_up(st, "AM")
    raise_(st, n, "device", "ADVISORY", 1000.0, reason="CO2 falling")
    run(n, now, 1000, 1040)
    clear(st, n, "device", 1040.0)                     # gone within the minute: nobody is bothered
    run(n, now, 1040, 1100)
    assert bot.sent == []
    raise_(st, n, "device", "TECHNICAL", 1100.0, reason="no answer from the sensor")
    run(n, now, 1100, 1159)
    assert bot.sent == []
    run(n, now, 1160, 1161)
    assert len(bot.sent) == 1 and "technical alarm for 1 min now" in bot.sent[0][1]
    assert "no answer from the sensor" in bot.sent[0][1] and "not being watched" in bot.sent[0][1]


def test_an_acknowledged_technical_alarm_is_not_messaged(tmp_path):
    st, bot, n, now, _ = setup(tmp_path)
    sign_up(st, "AM")
    raise_(st, n, "link", "TECHNICAL", 1000.0, reason="no data from the monitor for 5 s: check the USB cable")
    ack(st, n, "link", 1010.0)
    run(n, now, 1000, 1200)
    assert bot.sent == []


def test_lost_data_is_messaged_after_a_minute_but_not_before_the_monitor_was_ever_plugged_in(tmp_path):
    st, bot, n, now, _ = setup(tmp_path)
    sign_up(st, "AM")
    raise_(st, n, "link", "TECHNICAL", 1000.0, reason="no data from the monitor yet: is it plugged in?",
           never=True)
    run(n, now, 1000, 1200)
    assert bot.sent == []
    clear(st, n, "link", 1200.0)
    raise_(st, n, "link", "TECHNICAL", 1300.0, reason="no data from the monitor for 5 s: check the USB cable")
    run(n, now, 1300, 1361)
    assert len(bot.sent) == 1
    assert "No data from the monitor since" in bot.sent[0][1] and "also powers the monitor" in bot.sent[0][1]


def test_a_critical_alarm_from_older_firmware_waits_for_its_reason(tmp_path):
    st, bot, n, now, _ = setup(tmp_path)
    sign_up(st, "AM")
    raise_(st, n, "device", "CRITICAL", 1000.0, reason="")
    run(n, now, 1000, 1000)
    assert bot.sent == []                              # the banner with the reason comes just after
    e = {"type": "alarm_reason", "key": "device", "reason": "CO2 lost: fell 50 ppm from 1111 in under 20 s"}
    st.apply(e)
    n.on_event(e, None)
    run(n, now, 1001, 1001)
    assert len(bot.sent) == 1 and "fell 50 ppm" in bot.sent[0][1]


def test_people_who_stopped_their_messages_get_none(tmp_path):
    st, bot, n, now, _ = setup(tmp_path)
    uid = sign_up(st, "AM")
    st.set_user_active(900.0, uid, False)
    raise_(st, n, "device", "CRITICAL", 1000.0)
    run(n, now, 1000, 1200)
    assert bot.sent == []


# ---- delivery ----------------------------------------------------------------------------------------
def statuses(st):
    return [(x["status"], x["attempts"]) for x in reversed(st.notifications())]


def test_three_tries_when_callmebot_cannot_be_reached_then_failed_on_the_dashboard(tmp_path):
    down = (False, True, "could not reach CallMeBot (timed out)")
    st, bot, n, now, said = setup(tmp_path, answers=[down, down, down])
    sign_up(st, "AM")
    raise_(st, n, "device", "CRITICAL", 1000.0)
    run(n, now, 1000, 1009)
    assert statuses(st) == [("retrying", 1)]
    run(n, now, 1010, 1039)
    assert statuses(st) == [("retrying", 2)]
    run(n, now, 1040, 1041)                            # tries at 1000, 1010 and 1040
    assert statuses(st) == [("failed", 3)] and len(bot.sent) == 3
    assert any("could not be sent" in s for s in said)
    assert st.alarms()[0]["messages"] == [{"kind": "alarm", "status": "failed", "ts": 1000.0, "who": "AM"}]


def test_nobody_hears_that_an_alarm_ended_if_its_message_never_reached_them(tmp_path):
    st, bot, n, now, _ = setup(tmp_path, answers=[(False, False, "CallMeBot answered: user not authorized")])
    sign_up(st, "AM")
    raise_(st, n, "device", "CRITICAL", 1000.0)
    run(n, now, 1000, 1010)
    ack(st, n, "device", 1010.0)
    clear(st, n, "device", 1020.0)
    run(n, now, 1020, 1030)
    assert len(bot.sent) == 1 and statuses(st) == [("failed", 1)]


def test_a_second_try_that_works_is_sent(tmp_path):
    st, bot, n, now, _ = setup(tmp_path, answers=[(False, True, "could not reach CallMeBot"), (True, False, "ok")])
    sign_up(st, "AM")
    raise_(st, n, "device", "CRITICAL", 1000.0)
    run(n, now, 1000, 1011)
    assert statuses(st) == [("sent", 2)]


def test_a_refused_key_fails_at_once_without_trying_again(tmp_path):
    st, bot, n, now, _ = setup(tmp_path, answers=[(False, False, "CallMeBot answered: APIKey is invalid")])
    sign_up(st, "AM")
    raise_(st, n, "device", "CRITICAL", 1000.0)
    run(n, now, 1000, 1100)
    assert statuses(st) == [("failed", 1)] and len(bot.sent) == 1
    assert st.notifications()[0]["error"] == "CallMeBot answered: APIKey is invalid"


def test_a_replay_sends_no_alarm_messages_but_a_sign_up_test_still_goes(tmp_path):
    st, bot, n, now, _ = setup(tmp_path, dry_run="replay")
    uid = sign_up(st, "AM")
    raise_(st, n, "device", "CRITICAL", 1000.0)
    run(n, now, 1000, 1200)
    assert bot.sent == [] and statuses(st) == [("not sent: replay", 0), ("not sent: replay", 0)]
    n.test(next(u for u in st.users() if u["user_id"] == uid))
    run(n, now, 1201, 1201)
    assert len(bot.sent) == 1 and "test message" in bot.sent[0][1]


def test_no_messages_means_none_at_all(tmp_path):
    st, bot, n, now, _ = setup(tmp_path, dry_run="--no-messages")
    uid = sign_up(st, "AM")
    n.test(next(u for u in st.users() if u["user_id"] == uid))
    raise_(st, n, "device", "CRITICAL", 1000.0)
    run(n, now, 1000, 1200)
    assert bot.sent == []


def test_a_fault_that_comes_and_goes_cannot_flood_a_phone(tmp_path):
    st, bot, n, now, _ = setup(tmp_path, max_per_10_min=2)
    sign_up(st, "AM")
    for k in range(3):
        t0 = 1000 + 100 * k
        raise_(st, n, "device", "CRITICAL", t0)
        run(n, now, t0, t0 + 5)
        ack(st, n, "device", t0 + 5)
        clear(st, n, "device", t0 + 6)
        run(n, now, t0 + 6, t0 + 7)
    assert len(bot.sent) == 2
    assert any(s.startswith("not sent: too many") for s, _ in statuses(st))


def test_the_real_sender_reads_callmebots_answers(monkeypatch):
    class Answer(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    pages = {"ok": b"<html><body><p>Message queued. You will receive it in a few seconds.</p></body></html>",
             "bad": b"<html><body><b>APIKey is invalid.</b> Get a new one from the bot</body></html>"}
    user = {"channel": "whatsapp", "phone_e164": "+15145550123", "apikey": "123456", "name": "AM"}
    bot = nt.CallMeBot()
    bot._ctx = object()
    monkeypatch.setattr(nt.urllib.request, "urlopen", lambda req, timeout, context: Answer(pages["ok"]))
    assert bot.send(user, "hi") == (True, False, "Message queued. You will receive it in a few seconds.")
    monkeypatch.setattr(nt.urllib.request, "urlopen", lambda req, timeout, context: Answer(pages["bad"]))
    sent, again, said = bot.send(user, "hi")
    assert not sent and not again and "APIKey is invalid" in said

    def unreachable(req, timeout, context):
        raise urllib.error.URLError("timed out")
    monkeypatch.setattr(nt.urllib.request, "urlopen", unreachable)
    sent, again, said = bot.send(user, "hi")
    assert not sent and again and said == "could not reach CallMeBot (timed out)"
    assert plain("<p>a</p>\n<p>b &amp; c</p>") == "a b & c"


# ---- signing up --------------------------------------------------------------------------------------
def test_sign_up_checks_and_cleans_what_people_type():
    base = {"name": "Abdel", "channel": "whatsapp", "phone": "+1 (514) 555-0123", "apikey": "123456", "consent": True}
    ok, v = validate_signup(base)
    assert ok and v["phone"] == "+15145550123" and v["level"] == 1
    assert validate_signup(dict(base, phone="0015145550123"))[1]["phone"] == "+15145550123"
    assert validate_signup(dict(base, consent=False)) == (False, "Tick the box to agree to receive the messages.")
    assert validate_signup(dict(base, phone="514 555 0123"))[0] is False             # no country code
    assert validate_signup(dict(base, apikey=""))[0] is False
    assert validate_signup(dict(base, name=" "))[0] is False
    assert validate_signup(dict(base, channel="sms"))[0] is False
    ok, v = validate_signup({"name": "Abdel", "channel": "telegram", "telegram": "abdel_m", "consent": True,
                             "level": "2"})
    assert ok and v["telegram"] == "@abdel_m" and v["phone"] is None and v["level"] == 2


def test_a_browser_never_sees_the_key_or_the_whole_number(tmp_path):
    st = Store(str(tmp_path / "p.sqlite"))
    sign_up(st, "AM")
    shown = public_user(st.users()[0])
    assert "apikey" not in shown and "phone_e164" not in shown
    assert shown["address"] == "+1••••••0123" and shown["app"] == "WhatsApp"


def test_signing_up_again_updates_instead_of_adding(tmp_path):
    st = Store(str(tmp_path / "p.sqlite"))
    a = sign_up(st, "AM")
    st.set_user_active(600.0, a, False)
    b = sign_up(st, "Abdel")
    assert a == b and len(st.users()) == 1 and st.users()[0]["active"] == 1 and st.users()[0]["name"] == "Abdel"


# ---- the database --------------------------------------------------------------------------------------
def test_an_older_database_gets_the_new_columns(tmp_path):
    path = str(tmp_path / "old.sqlite")
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE users (user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, role TEXT, "
                     "phone_e164 TEXT, optin_ts TEXT, active INTEGER DEFAULT 1);"
                     "CREATE TABLE notifications (id INTEGER PRIMARY KEY, alarm_id INTEGER, user_id INTEGER, "
                     "ts_sent TEXT, provider TEXT, provider_msg_id TEXT, status TEXT, error TEXT);")
    db.close()
    Store(path).close()
    db = sqlite3.connect(path)
    cols = {r[1] for r in db.execute("PRAGMA table_info(users)")} | {r[1] for r in db.execute("PRAGMA table_info(notifications)")}
    db.close()
    assert {"channel", "apikey", "telegram", "level", "optout_ts", "kind", "text", "attempts", "ts_queued"} <= cols


def test_a_replay_shares_the_people_but_keeps_its_own_records(tmp_path):
    main = str(tmp_path / "co2monitor.sqlite")
    sign_up(Store(main), "AM")
    replay = Store(str(tmp_path / "replay.sqlite"), people_path=main)
    assert [u["name"] for u in replay.users()] == ["AM"]
    n = Notifier(replay, FakeBot(), {}, clock=lambda: 1000.0, dry_run="replay", echo=lambda *_: None)
    raise_(replay, n, "device", "CRITICAL", 1000.0)
    n.tick(1000.0)
    assert replay.alarms()[0]["messages"][0]["who"] == "AM"
    assert Store(main).alarms() == []                  # nothing from the replay in the real records


# ---- the sign-up page's REST calls -------------------------------------------------------------------------
def test_sign_up_page_rest_calls(tmp_path):
    pytest.importorskip("flask")
    from service.core import Service
    from service.main import create_app

    class Source:
        port = "test"

        def __init__(self, on_line, on_status):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def send(self, text):
            return True

    bot = FakeBot()
    cfg = {"link_timeout_s": 5.0, "silence_s": 120.0, "http_port": 0, "history_s": 600.0,
           "db_path": str(tmp_path / "svc.sqlite"), "raw_log_dir": str(tmp_path / "raw"), "notify": {}}
    svc = Service(cfg, Source, echo=lambda *_: None, clock=lambda: 1000.0, sender=bot)
    client = create_app(svc).test_client()
    assert b"Phone alerts" in client.get("/register").data

    r = client.post("/api/users", json={"name": "AM", "channel": "whatsapp", "phone": "+15145550123",
                                         "apikey": "123456", "level": 1})
    assert r.status_code == 400 and "Tick the box" in r.get_json()["message"]
    r = client.post("/api/users", json={"name": "AM", "channel": "whatsapp", "phone": "+15145550123",
                                         "apikey": "123456", "level": 1, "consent": True})
    assert r.status_code == 201 and r.get_json()["user"]["address"].endswith("0123")
    svc.notifier.send_due(1000.0)
    assert len(bot.sent) == 1 and "test message" in bot.sent[0][1]

    people = client.get("/api/users").get_json()
    assert b"123456" not in client.get("/api/users").data
    uid = people["users"][0]["user_id"]
    assert people["users"][0]["last"]["status"] == "sent"
    assert client.post("/api/users/%d/stop" % uid).status_code == 200
    assert client.post("/api/users/%d/test" % uid).status_code == 409
    assert client.post("/api/users/%d/start" % uid).status_code == 200
    assert client.post("/api/users/%d/test" % uid).status_code == 202
    assert client.post("/api/users/999/test").status_code == 404
    phones = client.get("/api/alarms").get_json()["phones"]
    assert phones == {"active": 1, "mode": None, "failed": []}
