"""Laptop-side tests for the service (service/) and its REST layer.

The rules engine is tested with explicit times; the REST layer with Flask's test client; the
serial link with a pseudo-terminal standing in for the Pico; and the whole chain with the real
alarm test of 25 Oct 2026 (data/raw/co2_2026-10-25_011421.log), replayed line by line.

Run from the repository root:   python -m pytest tests/
"""
import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from service.parse import clean, parse_line, quality, strip_clock  # noqa: E402
from service.rules_engine import Monitor  # noqa: E402
from service.store import Store  # noqa: E402

flask = pytest.importorskip("flask")
from service.core import Service  # noqa: E402
from service.main import create_app  # noqa: E402


def js(t, ppm, cr1, alarm, show=None, why="", acked=False, press=0, dash_ack=0):
    """One JSON line as firmware v0.5 prints it."""
    return json.dumps({"v": "0.5", "t": t, "ppm": ppm, "cr1": cr1, "cr1_why": "", "alarm": alarm,
                       "show": show or alarm, "why": why, "acked": acked, "latched": alarm == "CRITICAL",
                       "press": press, "hold": 0, "dash_ack": dash_ack})


def sample(*a, **k):
    return parse_line(js(*a, **k))


# ---- parse --------------------------------------------------------------------------------------
def test_parse_json_text_and_banner_lines():
    s = sample(312, 1814, "PRESENT", "NORMAL", why="exhaled CO2 present")
    assert s["kind"] == "sample" and s["source"] == "json" and s["ppm"] == 1814 and s["fw"] == "0.5"
    t = parse_line("t=  312 s  CO2  1814 ppm  |##########....................|  PRESENT    CRITICAL BACK")
    assert t["kind"] == "sample" and t["alarm"] == "CRITICAL" and t["show"] == "CRITICAL BACK" and not t["acked"]
    t = parse_line("t=  999 s  CO2   844 ppm  |###...........................|  ABSENT     CRITICAL ACK ")
    assert t["acked"] and t["cr1"] == "ABSENT"
    n = parse_line("t= 2315 s  no answer from sensor  FAULT      CRITICAL")
    assert n["ppm"] is None and n["cr1"] == "FAULT" and n["alarm"] == "CRITICAL"
    old = parse_line("t=  600 s  CO2  1159 ppm  |#####.........................|  PRESENT    event")
    assert old["show"] is None and old["alarm"] is None and old["ppm"] == 1159          # v0.3: no alarm column
    assert parse_line(">>> ALARM CRITICAL: CO2 lost: fell 50 ppm <<<") == {"kind": "banner",
                                                                          "text": "ALARM CRITICAL: CO2 lost: fell 50 ppm"}
    assert parse_line("Team 6 CO2 monitor v0.5 - CR-1 ...")["fw"] == "0.5"
    assert parse_line('{"t": 3, "ppm": ')["kind"] == "garbled"


def test_terminal_codes_and_clock_prefixes_are_removed():
    line = "\x1b]0;\U0001F40DWi-Fi: off | code.py | 9.2.9\x1b\\t=   20 s  CO2   500 ppm  |#....|  WARMING UP STANDBY"
    assert clean(line).startswith("t=   20 s")
    assert parse_line(line)["cr1"] == "WARMING UP"
    assert strip_clock("01:46:12  t=  2 s") == "t=  2 s"
    assert quality(sample(1, 5000, "PRESENT", "NORMAL")) == "top_of_range"
    assert quality(sample(1, None, "FAULT", "TECHNICAL")) == "no_answer"


# ---- rules engine -------------------------------------------------------------------------------
def feed(m, t0, t1, *a, **k):
    out = []
    for t in range(t0, t1):
        out += m.on_sample(float(t), sample(t, *a, **k))
        out += m.tick(float(t) + 0.5)
    return out


def test_a_board_alarm_becomes_one_record_with_its_reason():
    m = Monitor(0.0)
    ev = feed(m, 0, 10, 1500, "PRESENT", "NORMAL")
    ev += feed(m, 10, 20, 900, "ABSENT", "CRITICAL", why="CO2 lost: fell 108 ppm")
    ev += feed(m, 20, 25, 900, "ABSENT", "CRITICAL", show="CRITICAL BACK", why="CO2 is back")
    ev += feed(m, 25, 30, 1500, "PRESENT", "NORMAL")
    assert [e["type"] for e in ev] == ["alarm_raised", "alarm_cleared"]
    assert ev[0]["priority"] == "CRITICAL" and ev[0]["reason"] == "CO2 lost: fell 108 ppm" and ev[0]["ts"] == 10
    assert ev[1]["ts"] == 25


def test_link_lost_is_a_technical_alarm_and_clears_when_readings_return():
    m = Monitor(0.0)
    feed(m, 0, 5, 1500, "PRESENT", "NORMAL")
    assert m.view(5.0)["link"] == "live" and m.view(5.0)["sound"] is None
    ev = m.tick(10.5)
    assert ev and ev[0]["key"] == "link" and ev[0]["priority"] == "TECHNICAL"
    v = m.view(10.5)
    assert v["display"] == "LINK LOST" and v["sound"] == "technical" and v["link"] == "lost"
    ev = m.on_sample(12.0, sample(12, 1500, "PRESENT", "NORMAL"))
    assert ev == [{"type": "alarm_cleared", "key": "link", "ts": 12.0}]
    assert m.view(12.0)["display"] == "NORMAL"


def test_a_lost_link_never_hides_a_critical_alarm():
    m = Monitor(0.0)
    feed(m, 0, 5, 900, "ABSENT", "CRITICAL", why="CO2 lost")
    m.tick(11.0)
    v = m.view(11.0)
    assert v["link"] == "lost" and v["display"] == "CRITICAL" and v["sound"] == "critical"


def test_no_data_at_all_is_reported_too():
    m = Monitor(100.0)
    assert m.view(103.0)["display"] == "WAITING" and m.tick(103.0) == []
    ev = m.tick(106.0)
    assert ev[0]["reason"].startswith("no data from the monitor yet")
    assert m.view(106.0)["display"] == "LINK LOST"


def test_dashboard_ack_goes_to_the_board_and_is_confirmed_by_it():
    m = Monitor(0.0)
    feed(m, 0, 5, 900, "ABSENT", "CRITICAL", why="CO2 lost")
    assert m.request_ack(5.2, "")["ok"] is False                       # initials first
    r = m.request_ack(5.2, "AM")
    assert r["ok"] and r["send"] == "ACK\n"
    assert m.view(5.3)["sound"] is None                                # quiet at once on the screen
    ev = m.on_sample(6.0, sample(6, 900, "ABSENT", "CRITICAL", show="CRITICAL ACK", acked=True, dash_ack=1))
    acks = [e for e in ev if e["type"] == "ack"]
    assert acks == [{"type": "ack", "key": "device", "method": "dashboard", "who": "AM", "confirmed": True,
                     "ts": 5.2, "confirmed_ts": 6.0}]
    assert m.view(6.0)["display"] == "CRITICAL ACK" and m.view(6.0)["sound"] is None


def test_an_unconfirmed_ack_silences_this_screen_only_and_for_two_minutes():
    m = Monitor(0.0)
    feed(m, 0, 5, 900, "ABSENT", "CRITICAL", why="CO2 lost")
    m.request_ack(5.0, "AM")
    ev = feed(m, 5, 12, 900, "ABSENT", "CRITICAL", why="CO2 lost")      # older firmware: no confirmation
    acks = [e for e in ev if e["type"] == "ack"]
    assert len(acks) == 1 and acks[0]["confirmed"] is False and acks[0]["who"] == "AM"
    feed(m, 12, 126, 900, "ABSENT", "CRITICAL", why="CO2 lost")
    assert m.view(124.0)["sound"] is None
    assert m.view(126.0)["sound"] == "critical"                        # back after 120 s


def test_nothing_to_acknowledge():
    m = Monitor(0.0)
    feed(m, 0, 5, 1500, "PRESENT", "NORMAL")
    r = m.request_ack(5.0, "AM")
    assert r["ok"] is False and "no alarm" in r["message"]


def test_the_bedside_button_is_recorded_against_the_alarm_it_cleared():
    m = Monitor(0.0)
    feed(m, 0, 5, 900, "ABSENT", "CRITICAL", why="CO2 lost")
    feed(m, 5, 8, 1500, "PRESENT", "CRITICAL", show="CRITICAL BACK", why="CO2 is back")
    ev = m.on_sample(8.0, sample(8, 1500, "PRESENT", "NORMAL", press=1))
    assert [e["type"] for e in ev] == ["ack", "alarm_cleared"]
    assert ev[0]["key"] == "device" and ev[0]["method"] == "bedside button"


def test_a_new_alarm_is_heard_at_once_even_after_a_silence():
    m = Monitor(0.0)
    feed(m, 0, 5, 900, "ABSENT", "CRITICAL", why="CO2 lost")
    m.request_ack(5.0, "AM")
    feed(m, 5, 8, 1500, "PRESENT", "NORMAL")
    feed(m, 8, 10, None, "FAULT", "TECHNICAL", why="sensor fault: no answer")
    assert m.view(10.0)["sound"] == "technical"


def test_older_firmware_gets_its_alarm_reason_from_the_banner_after_the_reading():
    m = Monitor(0.0)
    m.on_sample(1.0, parse_line("t=  1 s  CO2  1500 ppm  |#####...|  PRESENT    NORMAL"))
    ev = m.on_sample(2.0, parse_line("t=  2 s  CO2   900 ppm  |###.....|  ABSENT     CRITICAL"))
    assert ev[0]["type"] == "alarm_raised" and ev[0]["reason"] == ""
    ev = m.on_banner(2.1, "ALARM CRITICAL: CO2 lost: fell 50 ppm from 1111 in under 20 s")
    assert ev == [{"type": "alarm_reason", "key": "device", "reason": "CO2 lost: fell 50 ppm from 1111 in under 20 s"}]


# ---- store --------------------------------------------------------------------------------------
def test_store_links_acks_to_their_alarm(tmp_path):
    st = Store(str(tmp_path / "t.sqlite"))
    st.apply({"type": "alarm_raised", "key": "device", "priority": "CRITICAL", "ts": 100.0, "reason": "CO2 lost",
              "ppm": 900})
    st.apply({"type": "ack", "key": "device", "method": "dashboard", "who": "AM", "confirmed": True, "ts": 101.0,
              "confirmed_ts": 102.0})
    st.apply({"type": "alarm_cleared", "key": "device", "ts": 130.0})
    a = st.alarms()
    assert len(a) == 1 and a[0]["cleared"] == pytest.approx(130.0) and a[0]["reason"] == "CO2 lost"
    assert a[0]["acks"] == [{"ts": pytest.approx(101.0), "who": "AM", "method": "dashboard", "confirmed": True}]


# ---- the service and its REST layer -------------------------------------------------------------
def test_the_service_reads_the_shared_config_json():
    from service.core import load_config
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        raw = json.load(f)
    cfg = load_config()
    assert cfg["link_timeout_s"] == raw["technical_timeout_s"]            # one number for "link lost"
    assert cfg["silence_s"] == 120.0                                       # an ack silences for 2 minutes
    assert cfg["http_port"] == raw["service"]["http_port"]
    assert cfg["raw_log_dir"] == os.path.join(ROOT, "data", "raw")        # the same folder as live_co2.sh
    assert cfg["notify"]["escalate_after_s"] == 120 and cfg["notify"]["advisory_after_s"] == 60   # slide 11
    fallback = load_config(os.path.join(ROOT, "no_such_config.json"))
    assert fallback["link_timeout_s"] == 5.0 and fallback["http_port"] == 8000


def test_a_missing_recording_is_reported_not_crashed(capsys):
    from service.__main__ import main
    assert main(["--replay", "data/raw/no_such_recording.log"]) == 2
    assert "No such recording: data/raw/no_such_recording.log" in capsys.readouterr().out


class FakeSource:
    port = "test"

    def __init__(self, on_line, on_status):
        self.sent = []

    def start(self):
        pass

    def stop(self):
        pass

    def send(self, text):
        self.sent.append(text)
        return True


def make_service(tmp_path, now):
    cfg = {"link_timeout_s": 5.0, "silence_s": 120.0, "http_port": 0, "history_s": 600.0,
           "db_path": str(tmp_path / "svc.sqlite"), "raw_log_dir": str(tmp_path / "raw")}
    lines = []
    svc = Service(cfg, FakeSource, echo=lines.append, clock=lambda: now[0])
    return svc, create_app(svc).test_client(), lines


def test_rest_layer_end_to_end(tmp_path):
    now = [1000.0]
    svc, client, echoed = make_service(tmp_path, now)
    assert b"CO\xe2\x82\x82 ventilation monitor" in client.get("/").data
    for t in range(10):
        now[0] = 1000.0 + t
        svc.on_line("t=%5d s  CO2  1500 ppm  |#####|  PRESENT    NORMAL" % t, now[0])
        svc.on_line(js(t, 1500, "PRESENT", "NORMAL", why="exhaled CO2 present"), now[0])
    latest = client.get("/api/latest").get_json()
    assert latest["display"] == "NORMAL" and latest["link"] == "live"
    assert latest["co2_pct"] == 0.15 and latest["state"] == "normal"      # the starter REST contract
    assert not any(e.startswith("{") or "  {" in e for e in echoed)         # JSON is not echoed to Terminal

    r = client.post("/api/ack", json={"who": "AM"})
    assert r.status_code == 409                                         # nothing to acknowledge

    now[0] = 1010.0
    svc.on_line(js(10, 900, "ABSENT", "CRITICAL", why="CO2 lost: fell 108 ppm"), now[0])
    latest = client.get("/api/latest").get_json()
    assert latest["display"] == "CRITICAL" and latest["sound"] == "critical" and latest["state"] == "critical"
    r = client.post("/api/ack", json={"who": "AM"})
    assert r.status_code == 200 and svc.source.sent == ["ACK\n"]
    now[0] = 1011.0
    svc.on_line(js(11, 900, "ABSENT", "CRITICAL", show="CRITICAL ACK", acked=True, dash_ack=1), now[0])
    alarms = client.get("/api/alarms").get_json()["alarms"]
    assert alarms[0]["priority"] == "CRITICAL" and alarms[0]["reason"] == "CO2 lost: fell 108 ppm"
    assert alarms[0]["acks"][0]["who"] == "AM" and alarms[0]["acks"][0]["confirmed"] is True

    pts = client.get("/api/readings?seconds=600").get_json()["points"]
    assert len(pts) == 12 and pts[-1][1] == 900 and pts[-1][2] == "CRITICAL ACK"   # one per second, not two

    now[0] = 1020.0                                                      # cable pulled
    svc.tick()
    latest = client.get("/api/latest").get_json()
    assert latest["link"] == "lost" and latest["display"] == "LINK LOST" and latest["state"] == "technical"
    assert any("TECHNICAL: no data from the monitor" in e for e in echoed)


def test_the_25_oct_alarm_test_replayed_through_the_service(tmp_path):
    """The real bench session of 25 Oct 01:14-02:04 (firmware v0.3, then v0.4 from 01:39)."""
    path = os.path.join(ROOT, "data", "raw", "co2_2026-10-25_011421.log")
    if not os.path.exists(path):
        pytest.skip("raw log not in this copy of the repository")
    now = [0.0]
    svc, client, _ = make_service(tmp_path, now)
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.rstrip("\n")
            if len(raw) < 10 or raw[2] != ":":
                continue
            h, m, s = int(raw[0:2]), int(raw[3:5]), int(raw[6:8])
            now[0] = h * 3600 + m * 60 + s
            svc.on_line(strip_clock(raw), now[0])
            svc.tick()
    alarms = list(reversed(client.get("/api/alarms?limit=200").get_json()["alarms"]))
    hhmmss = lambda t: "%02d:%02d:%02d" % (t // 3600, t // 60 % 60, t % 60)   # noqa: E731
    seen = [(hhmmss(int(a["raised"])), a["priority"], a["source"]) for a in alarms]
    assert ("01:46:46", "CRITICAL", "device") in seen                  # breathing stopped
    assert ("01:58:22", "TECHNICAL", "device") in seen                 # the pulled data wire
    # no data while the board restarted with new firmware (01:39:39, 01:55:45): technical, and
    # nowhere else in the 50 minutes
    assert [t for t, _, src in seen if src == "link"] == ["01:39:39", "01:55:45"]
    first = next(a for a in alarms if hhmmss(int(a["raised"])) == "01:46:46")
    assert first["acks"] and first["acks"][0]["method"] == "bedside button"
    assert hhmmss(int(first["acks"][0]["ts"])) == "01:47:35"


# ---- the serial link, with a pseudo-terminal as the Pico ----------------------------------------
def _pty_round_trip(monkeypatch, backend):
    from service.logger import SerialSource
    master, slave = os.openpty()
    name = os.ttyname(slave)
    monkeypatch.setenv("CO2_SERIAL_BACKEND", backend)
    got, status = [], []
    src = SerialSource(lambda text, now: got.append(text), status.append, port=name)
    src.start()
    try:
        deadline = time.time() + 5
        while not any(s.startswith("Reading the Pico") for s in status) and time.time() < deadline:
            time.sleep(0.05)
        os.write(master, b't=  1 s  CO2  1500 ppm\r\n{"t": 1, "ppm": 1500}\r\npartial')
        while len(got) < 2 and time.time() < deadline:
            time.sleep(0.05)
        assert got == ["t=  1 s  CO2  1500 ppm", '{"t": 1, "ppm": 1500}']
        assert src.send("ACK\n")
        data = b""
        while b"\n" not in data and time.time() < deadline:
            data += os.read(master, 64)
        assert data == b"ACK\n"
    finally:
        src.stop()
        time.sleep(0.6)
        os.close(master)
        os.close(slave)


def test_serial_link_with_the_standard_library(monkeypatch):
    _pty_round_trip(monkeypatch, "termios")


def test_serial_link_with_pyserial(monkeypatch):
    pytest.importorskip("serial")
    _pty_round_trip(monkeypatch, "pyserial")
