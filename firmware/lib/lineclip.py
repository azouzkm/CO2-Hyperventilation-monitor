"""The safety clip on the sampling line (CR-3): is the tube connected?

A plug taped to the tube sits in a socket fixed to the box, next to the SAMPLE barb. The two make a
loop from GP21 to GND. The pin is read with the Pico's internal pull-up:
    loop closed (tube on)          -> GP21 reads low  -> connected
    loop open (tube pulled off)    -> GP21 reads high -> LINE OFF
A broken wire or a plug that falls out also reads LINE OFF: the clip fails safe, towards a
TECHNICAL alarm, never towards a silent one.

The pin is read every pass of the display loop (every 20 ms or so), and a change counts only once it
has held for DEBOUNCE_S, so a wiggle of the plug does not flash the alarm.
Pure logic in LineClip; the pin itself is read in code.py, so the laptop tests need no hardware.
"""
DEBOUNCE_S = 0.3


class LineClip:
    def __init__(self, debounce_s=DEBOUNCE_S):
        self.debounce_s = debounce_s
        self.connected = True       # until the first readings say otherwise
        self._raw = None
        self._since = None
        self.changes = 0            # changes not yet reported (take_change)

    def sample(self, now, pin_high):
        """One reading of the pin: pin_high True = loop open."""
        raw = not pin_high
        if raw != self._raw:
            self._raw, self._since = raw, now
        elif raw != self.connected and now - self._since >= self.debounce_s:
            self.connected = raw
            self.changes += 1

    def take_change(self):
        """True if the state changed since the last call."""
        c = self.changes > 0
        self.changes = 0
        return c
