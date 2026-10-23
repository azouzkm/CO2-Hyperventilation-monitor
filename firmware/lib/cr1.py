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
         (400 ppm) for STUCK_S seconds, which is never room air.

Pure Python: runs on the Pico and in the laptop tests, which replay real bench readings.
"""

WARMUP_S = 75
PRESENT_RISE = 100
RISE_WINDOW_S = 30
PRESENT_LEVEL = 2500
ABSENT_DROP_FRAC = 0.10
ABSENT_DROP_MIN = 50
DROP_WINDOW_S = 20
BACK_FRAC = 0.25
FLOOR_PPM = 400
STUCK_S = 30

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

    def update(self, t, ppm):
        """Feed one reading (ppm None = no answer). Returns True when the state changed."""
        if ppm is None:
            self.floor_run = 0
            return self._go(t, FAULT, "no answer from the sensor")
        self.floor_run = self.floor_run + 1 if ppm <= FLOOR_PPM else 0
        if self.floor_run >= STUCK_S:
            self.hist = []
            return self._go(t, FAULT, "reading stuck at %d ppm: check the brown calibration wire" % FLOOR_PPM)
        if t < self.warmup_s:
            self._keep(t, ppm)
            return self._go(t, WARMING_UP, "sensor warming up")

        if self.state in (WARMING_UP, FAULT):
            self._keep(t, ppm)
            if ppm >= PRESENT_LEVEL:
                self.base = self._low(t, RISE_WINDOW_S)
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
