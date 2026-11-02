"""Laptop-side tests for firmware/lib/alarm.py: the four alarm states on top of CR-1.

The first tests drive the alarm with CR-1 states directly; the last ones replay the real readings
of 22 Oct 2026 through CR-1 and the alarm together, including the two sensor faults of that night.

Run from the repository root:   python -m pytest tests/
"""
import csv
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

import alarm  # noqa: E402
from alarm import AlarmManager, STANDBY, NORMAL, ADVISORY, CRITICAL, TECHNICAL  # noqa: E402
from cr1 import PresenceMonitor  # noqa: E402

DATA = os.path.join(ROOT, "data", "2026-10-22_session2_readings.csv")


def run(steps):
    """steps: [(t, co2_state, ppm, short, held)]. Returns (alarm, [(t, display, actions)])."""
    a = AlarmManager()
    log = []
    for t, co2, ppm, short, held in steps:
        acts = a.update(t, co2, "test", ppm, short, held)
        log.append((t, a.display(), acts))
    return a, log


def sounds(log, name):
    return [t for t, _, acts in log for act in acts if act == ("sound", name)]


def seq(*parts):
    """parts: (from_t, to_t, co2_state, ppm) -> one step per second."""
    out = []
    for t0, t1, co2, ppm in parts:
        out += [(float(t), co2, ppm, 0, 0) for t in range(t0, t1)]
    return out


def test_standby_until_the_first_breath_then_normal():
    a, log = run(seq((0, 75, "WARMING UP", 500), (75, 100, "ABSENT", 830), (100, 120, "PRESENT", 2000)))
    assert [d for t, d, _ in log if t < 100] == [STANDBY] * 100
    assert log[-1][1] == NORMAL and not sounds(log, "critical")


def test_co2_loss_after_breathing_is_critical_with_repeating_bursts():
    a, log = run(seq((0, 20, "PRESENT", 2000), (20, 60, "ABSENT", 900)))
    assert log[20][1] == CRITICAL
    assert sounds(log, "critical") == [20.0, 30.0, 40.0, 50.0]       # every 10 s
    assert any(act[0] == "banner" and act[1].startswith("ALARM CRITICAL: CO2 lost") for act in log[20][2])


def test_acknowledge_silences_for_two_minutes_then_the_alarm_returns():
    steps = seq((0, 20, "PRESENT", 2000), (20, 200, "ABSENT", 900))
    steps[25] = (25.0, "ABSENT", 900, 1, 0)                           # press at 25 s
    a, log = run(steps)
    assert log[25][1] == "CRITICAL ACK"
    assert ("sound", "ack") in log[25][2] and ("cancel",) in log[25][2]
    burst_times = sounds(log, "critical")
    assert burst_times[0] == 20.0
    assert not [t for t in burst_times if 25 < t < 25 + alarm.SILENCE_S]   # silent for 120 s
    assert 25.0 + alarm.SILENCE_S in burst_times                          # then back
    assert log[-1][1] == CRITICAL


def test_critical_is_latched_until_the_button_even_if_co2_returns():
    steps = seq((0, 20, "PRESENT", 2000), (20, 40, "ABSENT", 900), (40, 60, "PRESENT", 2000))
    steps[50] = (50.0, "PRESENT", 2000, 1, 0)
    a, log = run(steps)
    assert all(d == CRITICAL for t, d, _ in log if 20 <= t < 40)
    # CO2 back at 40 s: still an alarm, shown red and green in turn until someone presses
    assert all(d == "CRITICAL BACK" for t, d, _ in log if 40 <= t < 50)
    banners = [act[1] for t, _, acts in log for act in acts if act[0] == "banner" and t == 40]
    assert banners == ["ALARM CRITICAL: CO2 is back; press the button to clear the alarm"]
    assert sounds(log, "critical") == [20.0, 30.0, 40.0]               # still sounding
    assert log[50][1] == NORMAL                                       # cleared by the press


def test_acknowledged_then_co2_back_is_normal_without_a_second_press():
    # The card's Figure 3: Critical -> Normal when "acknowledged and back in range". 1 Nov: the board
    # asked for a second press after an acknowledged alarm, which the card does not ask for.
    steps = seq((0, 20, "PRESENT", 2000), (20, 40, "ABSENT", 900), (40, 200, "PRESENT", 2000))
    steps[30] = (30.0, "ABSENT", 900, 1, 0)                           # acknowledged at 30 s
    a, log = run(steps)
    assert log[35][1] == "CRITICAL ACK"
    assert log[40][1] == NORMAL and all(d == NORMAL for t, d, _ in log if t >= 40)
    assert any(act == ("banner", "ALARM CLEARED: acknowledged, and CO2 is back") for act in log[40][2])
    assert not sounds(log, "critical")[1:]                            # one burst, then silence
    # ... and if CO2 is lost again, a new CRITICAL
    steps = seq((0, 20, "PRESENT", 2000), (20, 40, "ABSENT", 900), (40, 60, "PRESENT", 2000),
                (60, 80, "ABSENT", 900))
    steps[30] = (30.0, "ABSENT", 900, 1, 0)
    a, log = run(steps)
    assert log[60][1] == CRITICAL and 60.0 in sounds(log, "critical")


def test_a_reading_stuck_at_the_top_is_technical_then_a_fall_is_critical_at_once():
    def go(steps):
        a = AlarmManager()
        out = []
        for t, co2, ppm, sat in steps:
            acts = a.update(float(t), co2, "test", ppm, saturated=sat)
            out.append((t, a.display(), acts))
        return out
    steps = ([(t, "PRESENT", 2000, False) for t in range(0, 20)] +
             [(t, "PRESENT", 5000, t >= 50) for t in range(20, 90)] +
             [(t, "ABSENT", 4700, False) for t in range(90, 100)])
    log = go(steps)
    assert log[49][1] == NORMAL and log[50][1] == TECHNICAL
    assert any(a[0] == "banner" and "top of the scale" in a[1] for a in log[50][2])
    assert log[90][1] == CRITICAL                                     # no grace period after it


def test_equipment_problems_are_technical_never_critical():
    # sensor fault while monitoring, then the 3-minute re-warm, then CO2 present again
    a, log = run(seq((0, 20, "PRESENT", 2000), (20, 30, "FAULT", None), (30, 210, "WARMING UP", 900),
                     (210, 230, "PRESENT", 2000)))
    assert all(d == TECHNICAL for t, d, _ in log if 20 <= t < 210)
    assert not sounds(log, "critical") and sounds(log, "technical")[0] == 20.0
    assert log[-1][1] == NORMAL
    # a reading at the bottom of the scale is a suspected fault at once, not a lost breath
    a, log = run(seq((0, 20, "PRESENT", 2000), (20, 40, "ABSENT", 400)))
    assert all(d == TECHNICAL for t, d, _ in log if t >= 20) and not sounds(log, "critical")


def test_after_a_fault_the_patient_gets_30_s_to_show_a_breath():
    # breathing, sensor fault, 3-minute re-warm, then CO2 absent: TECHNICAL for BREATH_WAIT_S, then CRITICAL
    a, log = run(seq((0, 20, "PRESENT", 2000), (20, 25, "FAULT", None), (25, 205, "WARMING UP", 900),
                     (205, 260, "ABSENT", 900)))
    assert all(d == TECHNICAL for t, d, _ in log if 20 <= t < 205 + alarm.BREATH_WAIT_S)
    assert log[205 + alarm.BREATH_WAIT_S][1] == CRITICAL
    assert any(act[0] == "banner" and "since the sensor came back" in act[1]
               for act in log[205 + alarm.BREATH_WAIT_S][2])
    # ... and a breath within that time is simply back to NORMAL, no alarm
    a, log = run(seq((0, 20, "PRESENT", 2000), (20, 25, "FAULT", None), (25, 205, "WARMING UP", 900),
                     (205, 215, "ABSENT", 900), (215, 260, "PRESENT", 1800)))
    assert log[-1][1] == NORMAL and not sounds(log, "critical")


def test_a_fault_never_hides_a_critical_alarm():
    # CO2 lost (CRITICAL), then the sensor fails: the patient alarm stays, with a note about the sensor
    a, log = run(seq((0, 20, "PRESENT", 2000), (20, 30, "ABSENT", 900), (30, 60, "FAULT", None)))
    assert all(d == CRITICAL for t, d, _ in log if t >= 20)
    assert any(act[0] == "banner" and act[1].startswith("ALARM CRITICAL stays") for act in log[30][2])
    assert sounds(log, "critical") == [20.0, 30.0, 40.0, 50.0]       # bursts carry on every 10 s


def test_holding_the_button_stops_monitoring_until_a_new_breath():
    steps = seq((0, 20, "PRESENT", 2000), (20, 40, "ABSENT", 900), (40, 60, "PRESENT", 2000),
                (60, 80, "ABSENT", 900), (80, 90, "PRESENT", 2000))
    steps[30] = (30.0, "ABSENT", 900, 0, 1)                           # hold during the alarm
    a, log = run(steps)
    assert log[30][1] == STANDBY and ("sound", "stop") in log[30][2]
    assert log[45][1] == NORMAL                                       # the next breath re-arms it
    steps[45] = (45.0, "PRESENT", 2000, 0, 1)                         # hold while CO2 is still in
    a, log = run(steps)
    assert all(d == STANDBY for t, d, _ in log if 45 <= t < 80)      # gas still there: no re-arm
    assert log[-1][1] == NORMAL                                       # a new breath at 80 s


# ---- CR-4's advisory -----------------------------------------------------------------------------
SLOW = "breathing rate 6/min, below 8/min, for 30 s"


def run_adv(steps):
    """steps: [(t, co2_state, ppm, short, advisory)]. Returns [(t, display, actions)]."""
    a = AlarmManager()
    log = []
    for t, co2, ppm, short, adv in steps:
        acts = a.update(t, co2, "test", ppm, short, 0, adv)
        log.append((t, a.display(), acts))
    return log


def seq_adv(*parts):
    """parts: (from_t, to_t, co2_state, ppm, advisory) -> one step per second."""
    out = []
    for t0, t1, co2, ppm, adv in parts:
        out += [(float(t), co2, ppm, 0, adv) for t in range(t0, t1)]
    return out


def test_advisory_is_amber_with_3_pulses_every_20_s_then_normal_when_back_in_range():
    log = run_adv(seq_adv((0, 100, "PRESENT", 2000, None), (100, 160, "PRESENT", 1500, SLOW),
                          (160, 180, "PRESENT", 2000, None)))
    assert all(d == ADVISORY for t, d, _ in log if 100 <= t < 160)
    assert sounds(log, "advisory") == [100.0, 120.0, 140.0] and not sounds(log, "critical")
    assert any(act == ("banner", "ALARM ADVISORY: " + SLOW) for act in log[100][2])
    assert log[160][1] == NORMAL
    assert any(act == ("banner", "ALARM NORMAL: back in range for 30 s") for act in log[160][2])


def test_advisory_escalates_to_critical_when_co2_is_lost():
    log = run_adv(seq_adv((0, 100, "PRESENT", 2000, None), (100, 130, "PRESENT", 1500, SLOW),
                          (130, 160, "ABSENT", 900, None), (160, 170, "PRESENT", 2000, None)))
    assert log[130][1] == CRITICAL                                    # the card's Advisory -> Critical
    assert log[-1][1].startswith(CRITICAL)                            # latched, even with CO2 back


def test_acknowledging_an_advisory_silences_it_for_two_minutes_and_keeps_it_amber():
    steps = seq_adv((0, 100, "PRESENT", 2000, None), (100, 400, "PRESENT", 1500, SLOW))
    steps[105] = (105.0, "PRESENT", 1500, 1, SLOW)                    # press at 105 s
    log = run_adv(steps)
    assert all(d == ADVISORY for t, d, _ in log if t >= 100)
    pulses = sounds(log, "advisory")
    assert pulses[0] == 100.0 and not [t for t in pulses if 105 < t < 105 + alarm.SILENCE_S]
    assert [t for t in pulses if t >= 105 + alarm.SILENCE_S]          # then it sounds again
    assert any(act[0] == "banner" and act[1].startswith("ADVISORY ACKNOWLEDGED") for act in log[105][2])


def test_a_new_advisory_after_an_acknowledged_one_sounds_at_once():
    steps = seq_adv((0, 100, "PRESENT", 2000, None), (100, 110, "PRESENT", 1500, SLOW),
                    (110, 140, "PRESENT", 2000, None), (140, 150, "PRESENT", 1500, SLOW))
    steps[102] = (102.0, "PRESENT", 1500, 1, SLOW)
    log = run_adv(steps)
    assert 140.0 in sounds(log, "advisory")


def test_a_sensor_fault_during_an_advisory_is_technical():
    log = run_adv(seq_adv((0, 100, "PRESENT", 2000, None), (100, 120, "PRESENT", 1500, SLOW),
                          (120, 130, "FAULT", None, None)))
    assert all(d == TECHNICAL for t, d, _ in log if t >= 120) and not sounds(log, "critical")


def test_acknowledging_a_critical_alarm_with_an_advisory_standing_goes_to_advisory():
    steps = seq_adv((0, 20, "PRESENT", 2000, None), (20, 40, "ABSENT", 900, None),
                    (40, 60, "PRESENT", 1500, SLOW))
    steps[50] = (50.0, "PRESENT", 1500, 1, SLOW)
    log = run_adv(steps)
    assert log[49][1].startswith(CRITICAL) and log[50][1] == ADVISORY


# ---- the 22 Oct readings through CR-1 and the alarm ---------------------------------------------
def secs(clock):
    h, m, s = (int(x) for x in clock.split(":"))
    return h * 3600 + m * 60 + s


def rows(start, end):
    """The 22 Oct readings between two Mac-clock times: [(mac_seconds, t, ppm)]."""
    with open(DATA) as f:
        return [(secs(r["mac_time"]), float(r["seconds_since_power_up"]), int(r["co2_ppm"]))
                for r in csv.DictReader(f) if start <= r["mac_time"] <= end]


def replay(readings):
    """Readings [(label_time, t, ppm)] through a fresh CR-1 and alarm: [(label_time, state, reason)]."""
    mon, a = PresenceMonitor(), AlarmManager()
    out = []
    for when, t, ppm in readings:
        mon.update(t, ppm)
        before = a.state
        a.update(t, mon.state, mon.reason, ppm)
        if a.state != before:
            out.append((when, a.state, a.reason))
    return out


def test_22_oct_breathing_stops_raises_critical_within_30_s():
    ch = replay(rows("01:09:00", "01:15:00"))          # the 1-minute rhythmic run
    start, stop = secs("01:10:04"), secs("01:11:04")
    normal = [t for t, s, _ in ch if s == NORMAL and t >= start]
    crit = [t for t, s, _ in ch if s == CRITICAL and t >= stop]
    assert normal and normal[0] - start < 12, ch                   # breathing seen: monitoring
    assert crit and crit[0] - stop <= 30, ch                        # stopped: critical alarm


def check_fault_episode(ch, fault_at, trusted_at):
    """While monitoring, a sensor fault: TECHNICAL from its first reading, never CRITICAL through the
    fault and the re-warm. A CRITICAL can only come BREATH_WAIT_S after the sensor is trusted again,
    if there is still no CO2 then (on 22 Oct nobody was breathing at it, so it does come)."""
    before = [s for t, s, _ in ch if t < fault_at]
    assert before and before[-1] == NORMAL, ch                      # it was monitoring
    assert [s for t, s, _ in ch if t == fault_at] == [TECHNICAL], ch
    crit = [(t, r) for t, s, r in ch if s == CRITICAL]
    assert crit and crit[0][0] - trusted_at >= alarm.BREATH_WAIT_S, ch
    assert "since the sensor came back" in crit[0][1], ch


def test_22_oct_first_sensor_fault_is_technical_not_critical():
    # 00:25:49 the operator's breath reads as CO2 PRESENT (monitoring); 00:25:57 the reading falls
    # from 1,784 to 778 ppm in one second (the HD wire): before the jump rule that was "CO2 lost".
    ch = replay(rows("00:25:30", "00:33:30"))
    check_fault_episode(ch, secs("00:25:57"), secs("00:32:23"))


def test_22_oct_second_sensor_fault_while_a_patient_breathes():
    # The second fault (01:31:46) came during room air, so a breath is put in front of it: two
    # minutes of synthetic breathing up from the room's 846 ppm, then the real readings of the fault.
    real = rows("01:31:46", "01:38:30")
    t0, m0 = real[0][1], real[0][0]
    breath = [(m0 - k, t0 - k, int(846 + 700 * (1 - math.exp(-(120 - k) / 15.0)))) for k in range(120, 0, -1)]
    ch = replay(breath + real)
    check_fault_episode(ch, secs("01:31:46"), secs("01:37:27"))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
