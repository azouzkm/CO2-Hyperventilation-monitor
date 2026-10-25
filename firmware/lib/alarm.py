"""The four alarm states from the project card (Figure 3), on top of the CR-1 states.

    STANDBY    white light circling, silent    warming up, or no breath seen yet: not monitoring
    NORMAL     green, steady, silent           exhaled CO2 present
    ADVISORY   amber, slow flash, 3 pulses     a sustained fall in CO2 (CR-4). Not triggered yet
    CRITICAL   red, fast flash, 10 pulses      CO2 lost after it was present (CR-2). Latched: it stays
                                               until someone presses the button, even if CO2 comes back
    TECHNICAL  cyan, steady, chirp             sensor fault, a reading stuck at the bottom of the scale,
                                               or the sensor not trusted yet after a fault (CR-3)

Golden rule (CR-3): an equipment problem is TECHNICAL, never CRITICAL. A reading of exactly 400 ppm
(the bottom of the sensor's scale, which a room never reaches) counts as a suspected fault at once,
not after CR-1's 30 s, so a failing sensor cannot look like a patient who stopped breathing.
The other way round, a fault never hides a patient alarm either: a CRITICAL that is already latched
stays CRITICAL through a fault (higher priority wins, as in IEC 60601-1-8).
After a fault the sensor is trusted again only after CR-1's re-warm. If CO2 is then absent, the
monitor gives the patient BREATH_WAIT_S to show a breath (still TECHNICAL) before calling it CRITICAL:
the re-warm cannot see a rise that began before it ended, so an instant alarm there would be false.

Button: a short press acknowledges a critical alarm (sound off for SILENCE_S, light steady red until
CO2 is back). Holding it HOLD_S stops monitoring (back to STANDBY) until a new breath arrives.
Until the break-wire loop exists, the sampling line is taken as connected.

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
        self.next_sound = None

    def display(self):
        """What the light should show: the state, or CRITICAL ACK (steady red) once acknowledged."""
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
        self.state, self.reason = state, reason
        out.append(("cancel",))
        out.append(("banner", "ALARM %s: %s" % (state, reason)))
        self.next_sound = t                       # sound at once on entry

    def update(self, t, co2, co2_reason, ppm=None, short=0, held=0):
        """co2: the CR-1 state (WARMING UP, ABSENT, PRESENT or FAULT) and its reason; ppm: the reading;
        short / held: button presses since the last call. Returns a list of actions:
        ("banner", text), ("cancel",) for stopping any sound, ("sound", name)."""
        out = []
        if held:
            self.armed = self.latched = self.acked = False
            self.need_new_breath = True
            self.back_at = None
            out.append(("sound", "stop"))
            self._set(t, STANDBY, "monitoring stopped with the button; it starts again at the next breath", out)
        problem = None                             # an equipment problem, if there is one
        if co2 == "FAULT":
            problem = "sensor fault: " + co2_reason
        elif co2 == "WARMING UP" and self.fault_open:
            problem = "sensor back, not trusted yet (re-warming)"
        elif co2 != "WARMING UP" and ppm is not None and ppm <= FLOOR_PPM:
            problem = "reading at the bottom of the scale (%d ppm): suspected sensor fault" % ppm
        if problem is not None:
            if self.latched and not self.fault_open:   # a patient alarm stands: say so, keep it
                out.append(("banner", "ALARM CRITICAL stays; also a sensor problem: " + problem))
            self.fault_open = True
            self.back_at = None
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
                if self.latched:
                    self._set(t, CRITICAL, "CO2 is back; press the button to clear the alarm", out)
                elif self.armed:
                    self._set(t, NORMAL, "exhaled CO2 present", out)
                else:
                    self._set(t, STANDBY, "waiting for a new breath", out)
            else:                                  # ABSENT
                self.need_new_breath = False
                waiting = self.back_at is not None and t - self.back_at < BREATH_WAIT_S
                if self.latched:
                    self._set(t, CRITICAL, "CO2 lost: " + co2_reason, out)
                elif self.armed and waiting:
                    self._set(t, TECHNICAL, "sensor trusted again; waiting up to %d s for a breath"
                              % BREATH_WAIT_S, out)
                elif self.armed:
                    self.latched = True
                    if self.back_at is not None:
                        why = "no CO2 in the %d s since the sensor came back" % BREATH_WAIT_S
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
                    self.latched = False
                    self._set(t, NORMAL, "exhaled CO2 present", out)
        if self.state == CRITICAL and self.acked and t >= self.silent_until:
            self.acked = False                     # silence over and CO2 still absent: alarm again
            out.append(("banner", "ALARM CRITICAL: still no CO2 after the %d s silence" % SILENCE_S))
            self.next_sound = t
        if self.state in REPEAT_S and self.next_sound is not None and t >= self.next_sound:
            if not (self.state == CRITICAL and self.acked):
                out.append(("sound", self.state.lower()))
            self.next_sound = t + REPEAT_S[self.state]
        return out
