"""The four alarm states from the project card (Figure 3), on top of the CR-1 states.

    STANDBY    white light circling, silent    warming up, or no breath seen yet: not monitoring
    NORMAL     green, steady, silent           exhaled CO2 present
    ADVISORY   amber, slow flash, 3 pulses     a sustained fall of the breathing rate or of the CO2
                                               (CR-4, lib/cr4.py); back to NORMAL after 30 s in range
    CRITICAL   red, fast flash, 10 pulses      CO2 lost after it was present (CR-2). Latched: it ends
                                               only once it is acknowledged AND CO2 is back (the card's
                                               "acknowledged and back in range"), in either order. If CO2
                                               comes back before anyone pressed, the ring alternates red
                                               and green ("breathing again: press to clear")
    TECHNICAL  cyan, steady, chirp             sensor fault, a reading stuck at the bottom of the scale,
                                               the sensor not trusted yet after a fault, the sampling
                                               line off (CR-3), or a reading stuck at the top of the scale
                                               (saturated: breaths cannot be seen, so "all fine" cannot
                                               be shown either)

Golden rule (CR-3): an equipment problem is TECHNICAL, never CRITICAL. A reading of exactly 400 ppm
(the bottom of the sensor's scale, which a room never reaches) counts as a suspected fault at once,
not after CR-1's 30 s, so a failing sensor cannot look like a patient who stopped breathing.
The other way round, a fault never hides a patient alarm either: a CRITICAL that is already latched
stays CRITICAL through a fault (higher priority wins, as in IEC 60601-1-8).
After a fault the sensor is trusted again only after CR-1's re-warm. If CO2 is then absent, the
monitor gives the patient BREATH_WAIT_S to show a breath (still TECHNICAL) before calling it CRITICAL:
the re-warm cannot see a rise that began before it ended, so an instant alarm there would be false.

A reading at the top of the scale for SATURATED_S (1 Nov: a sealed cell full of breath read 5,000 ppm
for 6 minutes with nobody breathing, and showed green) is TECHNICAL: the board cannot tell a breathing
patient from old gas. It is not a fault: when the reading falls and CO2 is called absent, CRITICAL
follows at once, with no grace period.

Button: a short press acknowledges a critical alarm (sound off for SILENCE_S, light steady red until
CO2 is back, then NORMAL), or an advisory (sound off for SILENCE_S, light still amber). Holding it HOLD_S stops
monitoring (back to STANDBY) until a new breath arrives.
Priority, highest first: CRITICAL (latched), TECHNICAL, ADVISORY, NORMAL. An advisory is judged
from the CO2 readings, so it cannot stand while the sensor is in doubt: a fault makes it TECHNICAL,
and a loss of CO2 during an advisory is CRITICAL (the card's Figure 3: Advisory -> Critical).
The sampling line: the safety clip on the tube (lib/lineclip.py, GP21) tells whether it is connected.
Line off is an equipment problem like a sensor fault (TECHNICAL "LINE OFF", never CRITICAL): this is
CR-3, and it is what makes CR-2 hold, since CO2 lost is CRITICAL only while the line reads connected.
Once the line is back on, the patient gets BREATH_WAIT_S to show a breath before a CRITICAL alarm,
as after a sensor fault: the cell still holds the room air that came in while the tube was off.

Pure Python, no hardware: update() returns what to do, and code.py does it. The laptop tests replay
real bench readings through it.
"""
STANDBY = "STANDBY"
NORMAL = "NORMAL"
ADVISORY = "ADVISORY"
CRITICAL = "CRITICAL"
TECHNICAL = "TECHNICAL"

SILENCE_S = 120                 # acknowledge: sound off this long
REPEAT_S = {CRITICAL: 10, ADVISORY: 20, TECHNICAL: 30}   # sound repeats while the state lasts
FLOOR_PPM = 400                 # the sensor's lowest reading
BREATH_WAIT_S = 30              # after a fault: time allowed for a first breath (= ER-2's 30 s)
SATURATED_S = 30                # at the top of the scale this long: the sensor cannot see breaths


class AlarmManager:
    def __init__(self):
        self.state = STANDBY
        self.reason = "sensor warming up"
        self.armed = False          # CO2 seen since the last start or stop: a loss is now an alarm
        self.latched = False        # a critical alarm waits for the button
        self.acked = False          # ... and someone has pressed it
        self.silent_until = 0.0
        self.fault_open = False     # sensor fault seen, sensor not trusted again yet
        self.need_new_breath = False
        self.back_at = None         # when the sensor was trusted again after a fault
        self.co2_back = False       # a latched CRITICAL, and CO2 is present again
        self.next_sound = None
        self.adv_silent_until = 0.0  # an acknowledged advisory: no sound until then
        self.was_line = False       # the last equipment problem was the sampling line (not the sensor)

    def display(self):
        """What the light should show: the state; CRITICAL BACK (red and green in turn) while a
        critical alarm waits for the button with CO2 present again; CRITICAL ACK (steady red) once
        acknowledged."""
        if self.state == CRITICAL and self.co2_back:
            return "CRITICAL BACK"
        if self.state == CRITICAL and self.acked:
            return "CRITICAL ACK"
        return self.state

    def _set(self, t, state, reason, out):
        if state == self.state:
            self.reason = reason
            return
        if state == CRITICAL:
            self.acked = False
            self.silent_until = 0.0
        if state == ADVISORY:
            self.adv_silent_until = 0.0
        self.state, self.reason = state, reason
        out.append(("cancel",))
        out.append(("banner", "ALARM %s: %s" % (state, reason)))
        self.next_sound = t                       # sound at once on entry

    def update(self, t, co2, co2_reason, ppm=None, short=0, held=0, advisory=None, line_ok=True,
               saturated=False):
        """co2: the CR-1 state (WARMING UP, ABSENT, PRESENT or FAULT) and its reason; ppm: the reading;
        short / held: button presses since the last call; advisory: CR-4's reason while it sees a
        sustained fall, else None; line_ok: False while the safety clip says the sampling line is
        off; saturated: True while the reading has sat at the top of the scale for SATURATED_S.
        Returns a list of actions:
        ("banner", text), ("cancel",) for stopping any sound, ("sound", name)."""
        out = []
        if held:
            self.armed = self.latched = self.acked = self.co2_back = False
            self.need_new_breath = True
            self.back_at = None
            out.append(("sound", "stop"))
            self._set(t, STANDBY, "monitoring stopped with the button; it starts again at the next breath", out)
        problem = None                             # an equipment problem, if there is one
        if not line_ok:
            problem = "LINE OFF: sampling line disconnected (safety clip open)"
        elif co2 == "FAULT":
            problem = "sensor fault: " + co2_reason
        elif co2 == "WARMING UP" and self.fault_open:
            problem = "sensor back, not trusted yet (re-warming)"
        elif co2 != "WARMING UP" and ppm is not None and ppm <= FLOOR_PPM:
            problem = "reading at the bottom of the scale (%d ppm): suspected sensor fault" % ppm
        if problem is not None:
            self.co2_back = False
            if self.latched and not self.fault_open:   # a patient alarm stands: say so, keep it
                out.append(("banner", "ALARM CRITICAL stays; also an equipment problem: " + problem))
            self.fault_open = True
            self.back_at = None
            self.was_line = not line_ok
            if not self.latched:
                self._set(t, TECHNICAL, problem, out)
        elif co2 == "WARMING UP":
            self._set(t, STANDBY, "sensor warming up", out)
        else:
            if self.fault_open:                    # trusted again after a fault
                self.fault_open = False
                self.back_at = t
            if co2 == "PRESENT":
                self.back_at = None
                if not self.need_new_breath:
                    self.armed = True
                if self.latched and self.acked:       # acknowledged and back in range: the
                    self.latched = self.acked = self.co2_back = False   # card's Critical -> Normal
                    out.append(("banner", "ALARM CLEARED: acknowledged, and CO2 is back"))
                if self.latched:
                    if not self.co2_back:
                        self.co2_back = True
                        out.append(("banner", "ALARM CRITICAL: CO2 is back; press the button to clear the alarm"))
                    self._set(t, CRITICAL, "CO2 is back; press the button to clear the alarm", out)
                elif self.armed and saturated:
                    self._set(t, TECHNICAL, "reading at the top of the scale (5,000 ppm) for %d s: the "
                              "sensor cannot see breaths; flush or dilute the sample" % SATURATED_S, out)
                elif self.armed and advisory:
                    self._set(t, ADVISORY, advisory, out)
                elif self.armed:
                    why = "back in range for 30 s" if self.state == ADVISORY else "exhaled CO2 present"
                    self._set(t, NORMAL, why, out)
                else:
                    self._set(t, STANDBY, "waiting for a new breath", out)
            else:                                  # ABSENT
                self.need_new_breath = False
                self.co2_back = False
                waiting = self.back_at is not None and t - self.back_at < BREATH_WAIT_S
                if self.latched:
                    self._set(t, CRITICAL, "CO2 lost: " + co2_reason, out)
                elif self.armed and waiting:
                    what = "sampling line back on" if self.was_line else "sensor trusted again"
                    self._set(t, TECHNICAL, "%s; waiting up to %d s for a breath" % (what, BREATH_WAIT_S), out)
                elif self.armed:
                    self.latched = True
                    if self.back_at is not None:
                        why = "no CO2 in the %d s since the %s came back" % (
                            BREATH_WAIT_S, "sampling line" if self.was_line else "sensor")
                    else:
                        why = "CO2 lost: " + co2_reason
                    self._set(t, CRITICAL, why, out)
                else:
                    self._set(t, STANDBY, "waiting for the first breath", out)
        if short:
            out.append(("sound", "ack"))
            if self.state == CRITICAL:
                self.acked = True
                self.silent_until = t + SILENCE_S
                out.append(("cancel",))
                out.append(("banner", "ALARM ACKNOWLEDGED: sound off for %d s" % SILENCE_S))
                if co2 == "PRESENT" and problem is None:
                    self.latched = self.co2_back = False
                    if advisory:
                        self._set(t, ADVISORY, advisory, out)
                    else:
                        self._set(t, NORMAL, "exhaled CO2 present", out)
            elif self.state == ADVISORY:
                self.adv_silent_until = t + SILENCE_S
                out.append(("cancel",))
                out.append(("banner", "ADVISORY ACKNOWLEDGED: sound off for %d s" % SILENCE_S))
        if self.state == CRITICAL and self.acked and t >= self.silent_until:
            self.acked = False                     # silence over, alarm not cleared: sound again
            if self.co2_back:
                out.append(("banner", "ALARM CRITICAL: still waiting for the button (CO2 is back)"))
            else:
                out.append(("banner", "ALARM CRITICAL: still no CO2 after the %d s silence" % SILENCE_S))
            self.next_sound = t
        if self.state in REPEAT_S and self.next_sound is not None and t >= self.next_sound:
            if not (self.state == CRITICAL and self.acked) and not (self.state == ADVISORY and t < self.adv_silent_until):
                out.append(("sound", self.state.lower()))
            self.next_sound = t + REPEAT_S[self.state]
        return out
