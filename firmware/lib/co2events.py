"""Spot CO2 events and measure how fast the sensor followed them.

An event is a rise of at least `rise_ppm` above the room level (for example a breath
toward the sensor). It ends when the reading is back within 10 % of the rise, or after
`max_event_s`. For each event the summary gives the room level, the peak, the 10-90 %
rise time and the 90-10 % fall time (linear interpolation between 1 s readings).

Pure Python with no CircuitPython imports, so the same file runs on the Pico and in the
laptop tests (tests/test_co2events.py).
"""

TOP_PPM = 5000  # top of our MH-Z19C's range (label: 400-5000 ppm); readings stop here


def _interp(t0, p0, t1, p1, level):
    if p1 == p0:
        return t1
    return t0 + (level - p0) * (t1 - t0) / (p1 - p0)


class EventDetector:
    def __init__(self, rise_ppm=300, room_window=30, max_event_s=900, stable_ppm=80, max_slope=0.5):
        self.rise_ppm = rise_ppm
        self.room_window = room_window
        self.max_event_s = max_event_s
        self.stable_ppm = stable_ppm  # max spread over the window to count as steady
        self.max_slope = max_slope    # max drift, ppm per second, over the window
        self.recent = []    # (t, ppm) readings outside events: room level and event lead-in
        self.event = None   # (t, ppm) readings while an event is open
        self.armed = None   # last steady room level; events are detected against it
        self.room = None    # room level used for the open (or last) event
        self.count = 0

    def reset(self):
        """Forget the room level and any open event (e.g. after a sensor fault)."""
        self.recent = []
        self.event = None
        self.armed = None

    def room_level(self):
        """Median of the last `room_window` readings outside events, or None while there are
        too few of them or they are still moving (e.g. the tail of the last event, or the top
        of a breath if the program started during one). Events are only detected against a
        level that was steady like this."""
        if len(self.recent) < (2 * self.room_window) // 3:
            return None
        pts = self.recent[-self.room_window:]
        window = [p for _, p in pts]
        if max(window) - min(window) > self.stable_ppm:
            return None
        if max(window) >= TOP_PPM:            # pinned at the top of the scale: not a room level
            return None
        # least-squares slope over the window: a slow tail can look flat over a few seconds
        n = len(pts)
        mt = sum(t for t, _ in pts) / n
        mp = sum(window) / n
        stt = sum((t - mt) * (t - mt) for t, _ in pts)
        slope = sum((t - mt) * (p - mp) for t, p in pts) / stt if stt else 0.0
        if abs(slope) > self.max_slope:
            return None
        window.sort()
        return window[len(window) // 2]

    def room_seconds(self):
        """How many readings the room level is based on."""
        return min(len(self.recent), self.room_window)

    def update(self, t, ppm):
        """Feed one reading. Returns "start", a summary dict when an event ends, or None."""
        if self.event is None:
            level = self.room_level()
            if level is not None:
                self.armed = level
            if self.armed is not None and ppm >= self.armed + self.rise_ppm:
                self.room = self.armed
                # keep every recent reading as lead-in: on a slow, small rise the 10 % point
                # can come well before the reading clears the event threshold
                self.event = self.recent[:] + [(t, ppm)]
                self.count += 1
                return "start"
            self.recent.append((t, ppm))
            if len(self.recent) > 2 * self.room_window:
                self.recent.pop(0)
            return None

        self.event.append((t, ppm))
        peak = max(p for _, p in self.event)
        back = ppm <= self.room + 0.1 * (peak - self.room)
        timed_out = t - self.event[0][0] > self.max_event_s
        if back or timed_out:
            summary = self._summarise(returned=back)
            self.event = None
            self.armed = None         # wait for a steady room level before the next event
            self.recent = [(t, ppm)]
            return summary
        return None

    def _summarise(self, returned):
        ev = self.event
        room = self.room
        i_peak = 0
        for i in range(len(ev)):
            if ev[i][1] > ev[i_peak][1]:
                i_peak = i
        t_peak, peak = ev[i_peak]
        span = peak - room
        lo = room + 0.1 * span
        hi = room + 0.9 * span

        # rise: first reading at or above 90 %, then the last reading below 10 % before it
        t90 = t10 = None
        i90 = None
        for i in range(1, i_peak + 1):
            if ev[i][1] >= hi > ev[i - 1][1]:
                i90 = i
                t90 = _interp(ev[i - 1][0], ev[i - 1][1], ev[i][0], ev[i][1], hi)
                break
        if i90 is not None:
            for j in range(i90 - 1, -1, -1):
                if ev[j][1] < lo:
                    t10 = _interp(ev[j][0], ev[j][1], ev[j + 1][0], ev[j + 1][1], lo)
                    break

        # fall: first reading at or below 90 % after the peak, then at or below 10 %
        f90 = f10 = None
        k90 = None
        for k in range(i_peak + 1, len(ev)):
            if ev[k][1] <= hi < ev[k - 1][1]:
                k90 = k
                f90 = _interp(ev[k - 1][0], ev[k - 1][1], ev[k][0], ev[k][1], hi)
                break
        if k90 is not None:
            for m in range(k90, len(ev)):
                if ev[m][1] <= lo < ev[m - 1][1]:
                    f10 = _interp(ev[m - 1][0], ev[m - 1][1], ev[m][0], ev[m][1], lo)
                    break

        return {
            "n": self.count,
            "room": room,
            "peak": peak,
            "t_peak": t_peak,
            "rise_s": None if t10 is None or t90 is None else t90 - t10,
            "fall_s": None if f90 is None or f10 is None else f10 - f90,
            "duration_s": ev[-1][0] - ev[0][0],
            "capped": peak >= TOP_PPM,
            "returned": returned,
        }


def describe(s):
    """Human-readable lines for one event summary."""
    top = " (top of range)" if s["capped"] else ""
    lines = ["=== CO2 event %d: room %d ppm -> peak %d ppm%s ===" % (s["n"], s["room"], s["peak"], top)]

    def sec(x):
        return "n/a" if x is None else "%.0f s" % x

    lines.append("    rise 10->90 %%: %s    fall 90->10 %%: %s    lasted %s"
                 % (sec(s["rise_s"]), sec(s["fall_s"]), sec(s["duration_s"])))
    if s["capped"]:
        lines.append("    note: the reading hit the sensor's ceiling, so the true peak was higher"
                     " and these times describe the clipped curve")
    if not s["returned"]:
        lines.append("    note: the reading did not return to the room level before the time limit")
    return lines
