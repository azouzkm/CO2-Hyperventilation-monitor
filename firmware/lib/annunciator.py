"""Speaker and acknowledge button.

Speaker: driven by PWM from one pin. For now it hangs straight off the pin through a 220-470 ohm
resistor (quiet); with the PAM8302 amplifier soldered in, the same pin feeds the amplifier's A+
input and the tones are loud. Nothing else changes.
Button: between its pin and GND, read with the internal pull-up, so pressed = pin reads low.
A press is counted when the button is let go; holding it HOLD_S counts as a hold instead.

Sounds are queued and played in the background: call service(now) every few tens of ms (the
display's wait loop does), so a beep never stops the readings. The alarm sounds follow the pattern
of medical alarms (IEC 60601-1-8): 10 pulses for high priority, 3 for medium, a chirp for low.
"""
import digitalio

DEBOUNCE_S = 0.04
HOLD_S = 3.0


def _pulses(groups, on, off, gap, freq):
    """Pulses in groups, e.g. (3, 2, 3, 2): returns [(start, length, frequency), ...]."""
    out, t = [], 0.0
    for g in groups:
        for _ in range(g):
            out.append((t, on, freq))
            t += on + off
        t += gap
    return out


SOUNDS = {
    "start": [(0.0, 0.08, 1800), (0.08, 0.08, 2600)],                      # rising chirp at power-up
    "critical": _pulses((3, 2, 3, 2), 0.15, 0.10, 0.25, 2400),          # 10 pulses
    "advisory": _pulses((3,), 0.20, 0.15, 0.0, 1800),                     # 3 pulses
    "technical": [(0.0, 0.06, 3000), (0.08, 0.06, 2400)],                 # chirp
    "ack": [(0.0, 0.06, 2000)],                                           # button click
    "stop": [(0.0, 0.10, 2400), (0.14, 0.12, 1600)],                      # falling: monitoring stopped
}


class Annunciator:
    def __init__(self, speaker_pin=None, button_pin=None):
        self.pwm = None
        if speaker_pin is not None:
            import pwmio
            self.pwm = pwmio.PWMOut(speaker_pin, frequency=2400, duty_cycle=0, variable_frequency=True)
        self.button = None
        if button_pin is not None:
            self.button = digitalio.DigitalInOut(button_pin)
            self.button.direction = digitalio.Direction.INPUT
            self.button.pull = digitalio.Pull.UP
        self.queue = []            # (start, stop, frequency), times in seconds
        self.presses = 0           # short presses not yet reported
        self.holds = 0             # holds not yet reported
        self._down_since = None
        self._held = False
        self._hold_fired = False
        self._sounding = 0          # the PWM starts silent

    # -- sound --------------------------------------------------------------------------------
    def play(self, now, name):
        """Queue a named sound after whatever is already queued."""
        start = max([now] + [e for _, e, _ in self.queue])
        for off, length, freq in SOUNDS[name]:
            self.queue.append((start + off, start + off + length, freq))

    def beep(self, now, seconds=0.12, freq=2400, after=0.0):
        start = max([now + after] + [e for _, e, _ in self.queue])
        self.queue.append((start, start + seconds, freq))

    def cancel(self):
        self.queue = []

    def _sound(self, freq):
        if self.pwm is None or freq == self._sounding:
            return
        if freq:
            self.pwm.frequency = freq
            self.pwm.duty_cycle = 32768
        else:
            self.pwm.duty_cycle = 0
        self._sounding = freq

    # -- called every few tens of ms -----------------------------------------------------------
    def service(self, now):
        self.queue = [q for q in self.queue if q[1] > now]
        playing = [f for s, e, f in self.queue if s <= now < e]
        self._sound(playing[0] if playing else 0)
        if self.button is None:
            return
        down = not self.button.value
        if down:
            if self._down_since is None:
                self._down_since = now
            elif now - self._down_since >= DEBOUNCE_S:
                self._held = True
                if not self._hold_fired and now - self._down_since >= HOLD_S:
                    self._hold_fired = True
                    self.holds += 1
        else:
            if self._held and not self._hold_fired:
                self.presses += 1
            self._down_since = None
            self._held = self._hold_fired = False

    def take_presses(self):
        """(short presses, holds) since the last call."""
        p, h = self.presses, self.holds
        self.presses = self.holds = 0
        return p, h
