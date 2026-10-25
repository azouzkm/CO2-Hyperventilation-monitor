"""CR-1: is exhaled CO2 present or absent?

    WARMING UP -> ABSENT <-> PRESENT,  and FAULT from any state.

PRESENT  the reading climbs at least PRESENT_RISE ppm above its lowest point since it last
         became ABSENT (within RISE_WINDOW_S seconds): a new rise, not a level, so it works
         whatever the room air is and is not fooled by the slow tail of the last breath.
         Coming out of warm-up or a fault, a reading above PRESENT_LEVEL (which room air never
         reaches, e.g. pinned at the top) also counts.
ABSENT   while PRESENT, the reading falls fast: at least ABSENT_DROP_FRAC of the rise
         (and at least ABSENT_DROP_MIN ppm) below its highest point of the last
         DROP_WINDOW_S seconds. This calls absence from the trend: on 22 Oct the fall showed
         17 s after breathing stopped, while the return to room air took 89 s.
         A slow fall (hypoventilation) is too slow to trigger it; that is CR-4's job.
         Also ABSENT when the reading is back near where the rise started (within
         BACK_FRAC of the rise), so a small bump that fades slowly cannot stay PRESENT.
FAULT    no answer from the sensor, or a reading stuck at the bottom of the scale
         (400 ppm) for STUCK_S seconds, which is never room air. A single reading at the bottom
         of the scale is not used at all: on 22 Oct such readings were glitches, and as data they
         made a fall to 400 look like an absence and the way back up look like a breath.
         Also a FAULT: a reading that jumps impossibly far from the one before it (after the first
         warm-up): a fall of more than FALL_JUMP_PPM, or a rise of more than RISE_JUMP_PPM, in one
         second. Real CO2 cannot move that fast through this sensor: in all the bench runs the
         fastest real fall was 163 ppm/s and the fastest real rise 654 ppm/s (a breath straight
         into the flow cell, 25 Oct). The jumps of 22 Oct were 1,784 to 778, 400 to 3,237 and
         5,000 to 400: the sensor or its wiring failing, and as data they read as an absence or
         a breath.
         When the sensor answers again it is not trusted at once: WARMING UP for RECOVERY_S
         seconds first. On 22 Oct, after a fault the reading climbed and overshot to 2,265 ppm
         before settling, and without this wait that recovery read as CO2 PRESENT for 90 s.

Pure Python: runs on the Pico and in the laptop tests, which replay real bench readings.
"""

WARMUP_S = 75
RECOVERY_S = 180
PRESENT_RISE = 100
RISE_WINDOW_S = 30
PRESENT_LEVEL = 2500
ABSENT_DROP_FRAC = 0.10
ABSENT_DROP_MIN = 50
DROP_WINDOW_S = 20
BACK_FRAC = 0.25
FLOOR_PPM = 400
STUCK_S = 30
FALL_JUMP_PPM = 400       # real falls: at most 163 ppm/s; 22 Oct glitches: 1,006 to 4,600
RISE_JUMP_PPM = 1200      # real rises: at most 654 ppm/s; 22 Oct glitches: 1,763 and 2,837

WARMING_UP = "WARMING UP"
ABSENT = "ABSENT"
PRESENT = "PRESENT"
FAULT = "FAULT"


class PresenceMonitor:
    def __init__(self, warmup_s=WARMUP_S):
        self.warmup_s = warmup_s
        self.state = WARMING_UP
        self.reason = "sensor warming up"
        self.hist = []          # (t, ppm), last max(RISE_WINDOW_S, DROP_WINDOW_S) seconds
        self.base = None        # level the last rise started from
        self.changed_at = None  # time of the last state change
        self.absent_low = None  # lowest reading since the state became ABSENT
        self.peak = None        # highest reading since the state became PRESENT
        self.floor_run = 0
        self.trust_from = warmup_s  # end of the first warm-up: jumps until then are normal (the
                                    # sensor shows a fixed number while it warms, then the real one)
        self.last = None        # (t, ppm) of the previous reading

    def _keep(self, t, ppm):
        self.hist.append((t, ppm))
        horizon = max(RISE_WINDOW_S, DROP_WINDOW_S) + 1
        while self.hist and self.hist[0][0] < t - horizon:
            self.hist.pop(0)

    def _low(self, t, window):
        vals = [p for (s, p) in self.hist if s >= t - window]
        return min(vals) if vals else None

    def _high(self, t, window):
        vals = [p for (s, p) in self.hist if s >= t - window]
        return max(vals) if vals else None

    def _go(self, t, state, reason):
        if state != self.state:
            if state == PRESENT:
                self.peak = None
            self.state = state
            self.reason = reason
            self.changed_at = t
            return True
        return False

    def _fault(self, t, reason):
        self.hist = []
        if self.state == FAULT and reason != self.reason:   # still faulty, and a new finding:
            self.reason = reason                            # report it (e.g. now stuck at 400)
            self.changed_at = t
            return True
        return self._go(t, FAULT, reason)

    def update(self, t, ppm):
        """Feed one reading (ppm None = no answer). Returns True when the state changed."""
        if ppm is None:
            self.floor_run = 0
            return self._fault(t, "no answer from the sensor")
        self.floor_run = self.floor_run + 1 if ppm <= FLOOR_PPM else 0
        prev, self.last = self.last, (t, ppm)
        if prev is not None and prev[0] >= self.trust_from and t - prev[0] <= 2.5:
            step = ppm - prev[1]
            if step < -FALL_JUMP_PPM or step > RISE_JUMP_PPM:
                return self._fault(t, "reading jumped from %d to %d ppm in %d s: suspected sensor fault"
                                % (prev[1], ppm, round(t - prev[0])))
        if self.floor_run >= STUCK_S:
            return self._fault(t, "reading stuck at %d ppm: check the brown calibration wire" % FLOOR_PPM)
        if ppm <= FLOOR_PPM:                    # bottom of the scale: suspect, not used as data
            return False                        # (STUCK_S of them in a row is a FAULT, above)
        if self.state == FAULT:                 # answering again: re-warm before trusting it
            self.warmup_s = max(self.warmup_s, t + RECOVERY_S)
            self.hist = []
            self._keep(t, ppm)
            return self._go(t, WARMING_UP, "sensor back after a fault; trusted again in %d s" % RECOVERY_S)
        if t < self.warmup_s:
            self._keep(t, ppm)
            return self._go(t, WARMING_UP, "sensor warming up")

        if self.state == WARMING_UP:
            self._keep(t, ppm)
            if ppm >= PRESENT_LEVEL:
                # the rise itself was not seen (warm-up or fault): judge the fall from the floor
                self.base = min(self._low(t, RISE_WINDOW_S), FLOOR_PPM)
                return self._go(t, PRESENT, "reading above %d ppm" % PRESENT_LEVEL)
            self.absent_low = [(t, ppm)]
            return self._go(t, ABSENT, "no exhaled CO2 yet")

        if self.state == ABSENT:
            # lowest point since ABSENT began, over the last RISE_WINDOW_S seconds
            self.absent_low = [(s, p) for (s, p) in self.absent_low if s >= t - RISE_WINDOW_S]
            low = min(p for (_, p) in self.absent_low) if self.absent_low else None
            self.absent_low.append((t, ppm))
            self._keep(t, ppm)
            if low is not None and ppm - low >= PRESENT_RISE:
                self.base = low
                return self._go(t, PRESENT, "+%d ppm in under %d s" % (ppm - low, RISE_WINDOW_S))
            return False

        # PRESENT
        high = self._high(t, DROP_WINDOW_S)
        self._keep(t, ppm)
        self.peak = ppm if self.peak is None else max(self.peak, ppm)
        if high is not None and self.base is not None:
            need = max(ABSENT_DROP_MIN, ABSENT_DROP_FRAC * (high - self.base))
            if high - ppm >= need:
                self.absent_low = [(t, ppm)]
                return self._go(t, ABSENT, "fell %d ppm from %d in under %d s" % (high - ppm, high, DROP_WINDOW_S))
            if ppm <= self.base + BACK_FRAC * (self.peak - self.base):
                self.absent_low = [(t, ppm)]
                return self._go(t, ABSENT, "back to %d ppm, near the %d it rose from" % (ppm, self.base))
        return False
