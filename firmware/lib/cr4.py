"""CR-4: breathing rate from the CO2 signal, recorded every second, and the alarm on a sustained fall.

BREATHING RATE. This sensor is too slow to draw each breath (22 Oct: 11-13 s to rise, about 2 ppm
of ripple per breath on the level). But the breaths still leave a regular wobble on the reading's
slope (ppm per second), and a rhythm can be measured even when single breaths are too small to
count one by one. Every EVERY_S seconds, over the last WINDOW_S seconds of readings:
  1. slope = each reading minus the one before; its straight-line trend is taken off (a steady
     rise or fall of the CO2 level is not breathing);
  2. the strongest rhythms between SEARCH_LO and SEARCH_HI breaths/min are found in the slope's
     spectrum (the fraction of the signal that repeats at each rate);
  3. a rhythm is believed only if it looks like breathing: it stands well above the rest of the
     spectrum (PEAK_RATIO), is big enough not to be sensor noise (AMP_MIN ppm/s), and the slope,
     once its average over one period is taken off, swings the other way half a period later
     (HALF_NEG) and comes back one and two periods later (ONE_POS, TWO_POS). A slow drift or a
     single bump does not do that; that check is what keeps a falsely LOW rate off the screen;
  4. the rate shown is the median of the last 3 believed rhythms (held HOLD_S seconds if one
     check fails), from RATE_LO to RATE_HI breaths/min; anything else is "not resolved", with the
     reason. The noise floor of step 3 is raised to AMP_NOISE_X times the noise this rig shows in
     room air (learnt while CR-1 says ABSENT), so a noisier sensor needs a bigger wobble.
The window runs whatever CR-1 says, but a rate is shown only while CR-1 says PRESENT, and not
while the reading sits at the top of the scale (5,000 ppm) for more than TOP_FRAC of the window
(the ripple is cut off there).
THE DANGEROUS ERROR is a falsely low rate: it would raise a false "slow breathing" alarm. So when
in doubt the rate is withheld, never guessed. Tested (tests/test_cr4.py) on:
  - the real 22 Oct paced run (15/min, open air): 15.0 to 15.7/min from 31 s into the run until
    10 s after it ended, then "not resolved";
  - all the other real readings of 22 and 25 Oct (10,010 readings, 2.8 h: room air, an operator
    nearby, breaths into the sealed flow-cell, flushes, sensor faults): no rate, no advisory;
  - simulated breathing through a cell and sensor 2 to 8 s slow: regular breathing from 6 to
    20/min reads within 0.6/min whenever shown; with 25 % breath-to-breath variation, never below
    80 % of the true rate; room-air noise and drift never show a rate.
The faster the breathing, the smaller the wobble (the sensor averages over seconds): this hardware
has a highest rate it can count (in simulation 20 to 24/min for a fast cell and sensor, about
8/min for a slow sensor with a small swing), which the bench run measures (tools/rate_run.sh) for
ER-7.
Below RATE_LO the answer is "slower than 5/min, not counted": a slow sway of the room's CO2 can
look like that (22 Oct, operator nearby), and breathing that slow empties the cell between
breaths, which CR-1 calls ABSENT (a CRITICAL alarm) anyway.

SUSTAINED FALL. The project card, Figure 3: Normal -> Advisory when the "concentration or derived
rate" falls beyond a threshold; back to Normal when the "values [are] back in range for 30 s".
An ADVISORY is raised when, for SUSTAIN_S seconds:
  - the rate is below RR_LOW breaths/min, or RR_FALL below the patient's own baseline rate; or
  - the breath-averaged CO2 (the mean of the last LEVEL_WINDOW_S readings, above room air) is
    LEVEL_FALL below its baseline: the slow fall of hypoventilation in the card's Figure 2.
A rate that is not resolved neither starts nor stops the clock; a second back in range stops it.
It clears once what raised it has been back in range, with a margin (RR_CLEAR, LEVEL_CLEAR), for
CLEAR_S seconds (so with a weak signal, where a normal rate cannot be resolved, it stays on until
it can be, or until someone acknowledges it). Baselines: the median of the last BASE_S seconds of
breathing, sampled from SETTLE_S after CO2 became present (not from the rise itself) and only
while nothing is falling (so a slow fall does not drag its own baseline down), used once they
cover BASE_MIN_S, and frozen while a fall is timed or an advisory stands. Each stretch of CO2
PRESENT has its own: they are forgotten when CO2 is lost (CR-2's alarm), and when the button is
held. Room air is learnt while CR-1 says ABSENT.
A fall of CO2 to nothing is not CR-4's job: CR-1 calls it ABSENT and the alarm CRITICAL (CR-2).
Undiluted breath pins the sensor at 5,000 ppm: a fall from there shows only once the reading is
back below the top.

Pure Python, no hardware: runs on the Pico and in the laptop tests.
"""
import math

WINDOW_S = 64           # seconds of readings per estimate
EVERY_S = 2             # an estimate every 2 s (the Pico has time for it, but no need for more)
SEARCH_LO = 3.0         # breaths/min: rhythms searched over this band ...
SEARCH_HI = 27.0
RATE_LO = 5.0           # ... and reported only within this one
RATE_HI = 24.0          # above 24/min: 2.5 s a breath, too close to one reading a second
GRID = 0.5              # breaths/min between the rates tried (refined between them)
CANDIDATES = 3          # strongest rhythms checked, strongest first
PEAK_RATIO = 15.0       # the rhythm's power over the median power of the band
AMP_MIN = 2.0           # ppm/s: smallest wobble believed (room-air noise on the slope: SD 1.0) ...
AMP_NOISE_X = 2.5       # ... raised to 2.5 x the noise this rig shows in room air, once learnt
NOISE_HALF = 4          # room-air noise: each slope minus the mean of the 4 on either side
HALF_NEG = -0.30        # correlation of the slope with itself half a period later: at most this
ONE_POS = 0.30          # ... one period later: at least this
TWO_POS = 0.15          # ... two periods later: at least this (when the window holds 4 periods)
HOLD_S = 6              # a believed rate is kept this long when a check fails
TOP_PPM = 4990          # the top of the scale (5,000)
TOP_FRAC = 0.25         # more readings than this at the top: no rate
FLOOR_PPM = 400         # the bottom of the scale: a suspected fault, not data (CR-1)
GAP_S = 2.5             # readings further apart than this: start the window again

RR_LOW = 8.0            # breaths/min: advisory below this (config.json breathing_rate_normal_min_bpm)
RR_FALL = 0.40          # ... or 40 % below the patient's own baseline rate
RR_CLEAR = 0.25         # back in range: at least RR_LOW + 1 and within 25 % of the baseline
LEVEL_WINDOW_S = 20     # breath-averaged CO2: the mean of the last 20 readings
LEVEL_FALL = 0.30       # advisory: the CO2 above room air 30 % below its baseline
LEVEL_CLEAR = 0.20      # back in range: within 20 % of the baseline
LEVEL_MIN_EXCESS = 150  # ppm above room air needed before a fraction of it means anything
BASE_S = 180            # baselines: median of the last 3 minutes of monitoring ...
BASE_MIN_S = 90         # ... used once they cover 90 s
BASE_EVERY_S = 5        # one baseline sample every 5 s ...
SETTLE_S = 30           # ... from 30 s after CO2 became present (not from the rise itself)
SUSTAIN_S = 30          # a fall held this long is "sustained"
CLEAR_S = 30            # back in range this long to clear (project card, Figure 3)
ROOM_KEEP = 120         # room-air readings kept (while CR-1 says ABSENT)

PRESENT = "PRESENT"     # CR-1 states (lib/cr1.py)
ABSENT = "ABSENT"


def median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return None
    m = n // 2
    return s[m] if n % 2 else (s[m - 1] + s[m]) / 2.0


def detrended_slope(x):
    """The first difference of x with its straight-line trend taken off."""
    d = [x[i] - x[i - 1] for i in range(1, len(x))]
    n = len(d)
    tm = (n - 1) / 2.0
    mean = sum(d) / n
    sxx = sum((i - tm) * (i - tm) for i in range(n))
    b = sum((i - tm) * (v - mean) for i, v in enumerate(d)) / sxx
    return [v - mean - b * (i - tm) for i, v in enumerate(d)]


def power_at(wd, rate):
    """Power of the (already windowed) signal wd at `rate` breaths/min, one sample a second. The
    phase is turned by multiplication rather than with a cos/sin per sample: fast, and accurate
    enough with the Pico's single-precision floats."""
    a = 2.0 * math.pi * rate / 60.0
    ca, sa = math.cos(a), math.sin(a)
    c, s = 1.0, 0.0
    re = im = 0.0
    for v in wd:
        re += v * c
        im -= v * s
        c, s = c * ca - s * sa, c * sa + s * ca
    return re * re + im * im


def period_detrend(d, period):
    """d minus its centred moving average over one period (the end samples weighted for a
    fractional period): a rhythm at that period passes untouched, a slower drift does not.
    Returns only the part where the average is complete."""
    reach = (period - 1.0) / 2.0
    k_max = int(reach) + (1 if reach > int(reach) else 0)
    out = []
    for i in range(k_max, len(d) - k_max):
        tot, wsum, k, rem = d[i], 1.0, 1, reach
        while rem > 0:
            wgt = 1.0 if rem >= 1.0 else rem
            tot += wgt * (d[i - k] + d[i + k])
            wsum += 2 * wgt
            rem -= 1.0
            k += 1
        out.append(d[i] - tot / wsum)
    return out


def _lagged(h, k, e):
    """Correlation of h with itself k samples later (whole k), scaled by the overlap."""
    n = len(h)
    if k >= n:
        return 0.0
    tot = 0.0
    for i in range(n - k):
        tot += h[i] * h[i + k]
    return tot / e * n / (n - k)


def correlation(h, lag):
    """Correlation of h with itself `lag` samples later (fractional lags interpolated), scaled so
    that a perfect repeat gives 1 whatever the lag."""
    e = 0.0
    for v in h:
        e += v * v
    if e <= 0:
        return 0.0
    k = int(lag)
    f = lag - k
    return (1 - f) * _lagged(h, k, e) + f * _lagged(h, k + 1, e)


class RhythmFinder:
    """One estimate from WINDOW_S + 1 readings: (rate or None, reason, peak ratio, wobble ppm/s)."""

    def __init__(self, n=WINDOW_S):
        self.n = n
        self.w = [0.5 - 0.5 * math.cos(2.0 * math.pi * (i + 0.5) / n) for i in range(n)]
        self.wsum = sum(self.w)
        self.rates = []
        r = SEARCH_LO
        while r <= SEARCH_HI + 1e-6:
            self.rates.append(r)
            r += GRID

    def estimate(self, x, amp_min=AMP_MIN, idle=None):
        """x: WINDOW_S + 1 readings. idle(), if given, is called every few rates, so the light,
        the sound and the button keep running on the Pico while it works (about a tenth of a
        second, every EVERY_S seconds)."""
        d = detrended_slope(x)
        wd = [self.w[i] * d[i] for i in range(len(d))]
        powers = []
        for r in self.rates:
            powers.append(power_at(wd, r))
            if idle is not None and len(powers) % 4 == 0:
                idle()
        med = median(powers)
        peaks = [k for k in range(1, len(powers) - 1) if powers[k] > powers[k - 1] and powers[k] >= powers[k + 1]]
        peaks.sort(key=lambda k: -powers[k])
        best = powers[peaks[0]] / med if peaks and med > 0 else 0.0
        why = "no regular rhythm on the CO2 signal"
        raw = [x[i] - x[i - 1] for i in range(1, len(x))]
        for k in peaks[:CANDIDATES]:
            ratio = powers[k] / med if med > 0 else 0.0
            if ratio < PEAK_RATIO:
                break
            if idle is not None:
                idle()
            a = math.log(max(powers[k - 1], 1e-9))
            b = math.log(max(powers[k], 1e-9))
            c = math.log(max(powers[k + 1], 1e-9))
            den = a - 2 * b + c
            shift = 0.5 * (a - c) / den if den < 0 else 0.0
            rate = self.rates[k] + max(-0.5, min(0.5, shift)) * GRID
            amp = 2.0 * math.sqrt(power_at(wd, rate)) / self.wsum
            if amp < amp_min:
                why = "rhythm too small to trust (%.1f ppm/s)" % amp
                continue
            period = 60.0 / rate
            h = period_detrend(raw, period)
            if len(h) < 2 * period + 4:
                why = "window too short for %.1f/min" % rate
                continue
            if correlation(h, period / 2) > HALF_NEG:
                why = "no back-and-forth swing at %.1f/min" % rate
                continue
            if correlation(h, period) < ONE_POS:
                why = "does not repeat at %.1f/min" % rate
                continue
            if 2 * period <= len(h) / 2 and correlation(h, 2 * period) < TWO_POS:
                why = "does not keep repeating at %.1f/min" % rate
                continue
            if rate < RATE_LO:
                return None, "slower than %.0f/min: not counted" % RATE_LO, ratio, amp
            if rate > RATE_HI:
                return None, "faster than %.0f/min: too fast for this sensor" % RATE_HI, ratio, amp
            return rate, "", ratio, amp
        return None, why, best, 0.0


class BreathingRate:
    """Feeds RhythmFinder one reading a second and keeps the rate shown (breaths/min, or None)."""

    def __init__(self):
        self.finder = RhythmFinder()
        self.quiet = []         # |slope noise| seen in room air (CR-1 ABSENT), last 120
        self.reset("collecting readings")

    def noise(self):
        """This rig's noise on the slope in room air (ppm/s, as an SD), or None until learnt."""
        if len(self.quiet) < 30:
            return None
        return 1.4826 * median(self.quiet)

    def amp_min(self):
        n = self.noise()
        return AMP_MIN if n is None else max(AMP_MIN, AMP_NOISE_X * n)

    def _learn_noise(self):
        k = 2 * NOISE_HALF + 2
        if len(self.x) < k:
            return
        last = self.x[-k:]
        sl = [last[i] - last[i - 1] for i in range(1, k)]
        self.quiet = (self.quiet + [abs(sl[NOISE_HALF] - sum(sl) / len(sl))])[-120:]

    def reset(self, why):
        self.x = []             # readings of the current window
        self.last_t = None
        self.found = []         # (t, rate) of the believed estimates
        self.rate = None
        self.why = why
        self.next_eval = None
        self.ratio = self.amp = 0.0
        self.evaluated = False  # True when the last update() worked out a new estimate

    def update(self, t, ppm, co2_state, idle=None):
        """Feed one reading (ppm None = no answer) and CR-1's state; returns the rate or None.
        The window of readings runs whatever CR-1 says (so a rate can show about 30 s after
        breathing starts), but a rate is worked out and shown only while CR-1 says PRESENT.
        idle(): see RhythmFinder.estimate."""
        self.evaluated = False
        if ppm is None or ppm <= FLOOR_PPM:
            self.reset("no usable reading from the sensor")
            return None
        if self.last_t is not None and t - self.last_t > GAP_S:
            self.reset("readings interrupted")
        self.last_t = t
        self.x.append(ppm)
        if len(self.x) > WINDOW_S + 1:
            self.x.pop(0)
        if co2_state != PRESENT:
            if co2_state == ABSENT:
                self._learn_noise()
            self.found, self.rate, self.why, self.next_eval = [], None, "no exhaled CO2", None
            return None
        if len(self.x) < WINDOW_S + 1:
            self.rate = None
            self.why = "collecting %d of %d s of breathing" % (len(self.x) - 1, WINDOW_S)
            return None
        if self.next_eval is not None and t < self.next_eval:
            return self.rate
        self.next_eval = t + EVERY_S - 0.5
        at_top = sum(1 for v in self.x if v >= TOP_PPM) > TOP_FRAC * len(self.x)
        if at_top:
            rate, why, self.ratio, self.amp = None, "reading at the top of the scale: breaths cut off", 0.0, 0.0
        else:
            rate, why, self.ratio, self.amp = self.finder.estimate(self.x, self.amp_min(), idle)
            self.evaluated = True
        if rate is not None:
            self.found.append((t, rate))
        self.found = [(s, r) for (s, r) in self.found if s >= t - HOLD_S]
        if rate is None and (at_top or not self.found):
            self.rate, self.why = None, why
            return None
        self.rate = median([r for _, r in self.found[-3:]])
        self.why = ""
        return self.rate


LOW, OK, UNKNOWN = "low", "ok", "unknown"


class FallWatch:
    """The ADVISORY of CR-4: a sustained fall of the breathing rate or of the breath-averaged CO2."""

    def __init__(self):
        self.restart()

    def restart(self):
        """Forget the baselines (monitoring stopped with the button)."""
        self.room = []          # readings while CR-1 said ABSENT
        self.readings = []      # last LEVEL_WINDOW_S readings while PRESENT
        self.level_base = []    # (t, level) baseline samples
        self.rate_base = []     # (t, rate) baseline samples
        self.next_sample = None
        self._quiet()

    def _quiet(self):
        self.present_since = None   # start of this stretch of CO2 PRESENT
        self.level = None       # breath-averaged CO2, ppm
        self.fall = None        # fraction of the CO2 above room air lost since the baseline
        self.advisory = None    # reason text while an ADVISORY stands
        self.causes = ()
        self.low_since = None   # when the current fall began
        self.low_seen = 0       # seconds of it actually seen low
        self.in_range_since = None

    def room_level(self):
        """Room air: low in the readings while CO2 was absent (the tail of the last breath is
        still falling at the start of those), or None while too few are known."""
        if len(self.room) < 10:
            return None
        s = sorted(self.room)
        return s[len(s) // 5]

    def baselines(self, t):
        """(level, rate) baselines. While a fall is being timed or an advisory stands, they stay
        as they were when the fall began: the patient is compared with their own breathing before
        it, however long the fall lasts."""
        ref = t if self.low_since is None else self.low_since
        return self._base(self.level_base, ref), self._base(self.rate_base, ref)

    def _base(self, samples, ref):
        while samples and samples[0][0] < ref - BASE_S:
            samples.pop(0)
        if not samples or samples[-1][0] - samples[0][0] < BASE_MIN_S:
            return None
        return median([v for _, v in samples])

    def update(self, t, ppm, co2_state, rate):
        """Feed one reading, CR-1's state and the breathing rate (None: not resolved).
        Returns the ADVISORY reason while one stands, else None."""
        if co2_state != PRESENT or ppm is None or ppm <= FLOOR_PPM:
            if co2_state == ABSENT and ppm is not None and ppm > FLOOR_PPM:
                self.room = (self.room + [ppm])[-ROOM_KEEP:]
            if self.present_since is not None:      # CO2 lost (CR-2's alarm) or the sensor failed:
                self.level_base, self.rate_base = [], []    # breathing that comes back is a new
            self.readings = []                              # stretch, with its own baselines
            self._quiet()
            return None
        if self.present_since is None:
            self.present_since = t
        self.readings = (self.readings + [ppm])[-LEVEL_WINDOW_S:]
        if len(self.readings) >= LEVEL_WINDOW_S // 2:
            self.level = sum(self.readings) / len(self.readings)
        room = self.room_level() or FLOOR_PPM
        lbase, rbase = self.baselines(t)
        self.fall = None
        if self.level is not None and lbase is not None and lbase - room >= LEVEL_MIN_EXCESS:
            self.fall = (lbase - self.level) / (lbase - room)

        if rate is None:
            rate_is = UNKNOWN
        elif rate < RR_LOW or (rbase is not None and rate <= (1 - RR_FALL) * rbase):
            rate_is = LOW
        elif rate >= RR_LOW + 1 and (rbase is None or rate >= (1 - RR_CLEAR) * rbase):
            rate_is = OK
        else:
            rate_is = UNKNOWN   # between the alarm and the all-clear thresholds
        if self.fall is None:
            level_is = UNKNOWN
        elif self.fall >= LEVEL_FALL:
            level_is = LOW
        elif self.fall <= LEVEL_CLEAR:
            level_is = OK
        else:
            level_is = UNKNOWN

        # baseline samples every BASE_EVERY_S, only while all is well, from values near the baseline
        if (self.next_sample is None or t >= self.next_sample) and t - self.present_since >= SETTLE_S:
            self.next_sample = t + BASE_EVERY_S
            if self.advisory is None and self.low_since is None:
                if self.level is not None and (self.fall is None or self.fall < LEVEL_FALL / 2):
                    self.level_base.append((t, self.level))
                if rate is not None and (rbase is None or rate > (1 - RR_FALL / 2) * rbase):
                    self.rate_base.append((t, rate))

        low = LOW in (rate_is, level_is)
        if self.advisory is None:
            if low:
                if self.low_since is None:
                    self.low_since, self.low_seen = t, 0
                self.low_seen += 1
                if t - self.low_since >= SUSTAIN_S and self.low_seen >= SUSTAIN_S // 2:
                    self.causes = tuple(c for c, s in (("rate", rate_is), ("level", level_is)) if s == LOW)
                    self.advisory = self._reason(rate, rbase, lbase, rate_is == LOW, level_is == LOW)
                    self.in_range_since = None
            elif OK in (rate_is, level_is):
                self.low_since = None       # seen back in range: the fall did not last
            return self.advisory

        back = not low and all(s == OK for s in ((rate_is if "rate" in self.causes else OK),
                                                 (level_is if "level" in self.causes else OK)))
        if back:
            if self.in_range_since is None:
                self.in_range_since = t
            if t - self.in_range_since >= CLEAR_S:
                self.advisory, self.causes = None, ()
                self.low_since = self.in_range_since = None
        else:
            self.in_range_since = None
        return self.advisory

    def _reason(self, rate, rbase, lbase, rate_low, level_low):
        parts = []
        if rate_low:
            if rate < RR_LOW:
                parts.append("breathing rate %.0f/min, below %.0f/min" % (rate, RR_LOW))
            else:
                parts.append("breathing rate %.0f/min, down %.0f %% from %.0f/min"
                             % (rate, 100 * (1 - rate / rbase), rbase))
        if level_low:
            parts.append("CO2 down %.0f %% (%.0f -> %.0f ppm)" % (100 * self.fall, lbase, self.level))
        return "; ".join(parts) + ", for %d s" % SUSTAIN_S


class RateMonitor:
    """CR-4 for code.py: the breathing rate and the fall watch, fed one reading a second."""

    def __init__(self):
        self.breathing = BreathingRate()
        self.watch = FallWatch()
        self._had_rate = False

    @property
    def rate(self):
        return self.breathing.rate

    @property
    def advisory(self):
        return self.watch.advisory

    def restart(self):
        """Monitoring stopped with the button: forget the baselines."""
        self.watch.restart()

    def update(self, t, ppm, co2_state, idle=None):
        """Feed one reading and CR-1's state. Returns a banner when the rate appears or is lost.
        idle(): called now and then during the estimate, to keep the light, sound and button
        running on the Pico."""
        rate = self.breathing.update(t, ppm, co2_state, idle)
        self.watch.update(t, ppm, co2_state, rate)
        banner = None
        if rate is not None and not self._had_rate:
            banner = "CR-4 RATE: %.0f/min" % rate
        elif rate is None and self._had_rate and co2_state == PRESENT:
            banner = "CR-4 RATE: not resolved (%s)" % self.breathing.why
        self._had_rate = rate is not None
        return banner

    def shown(self):
        """The rate as printed on each line: e.g. 'RR 15.4' or 'RR --'."""
        r = self.breathing.rate
        return "RR --" if r is None else "RR %.1f" % r
