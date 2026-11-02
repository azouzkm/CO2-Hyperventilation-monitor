"""Shows the monitor's state on the Pico's LED and on the light ring (NeoPixel Ring 16, D16 / GP16).

Alarm states (lib/alarm.py), what code.py shows from v0.4 on; flash rates follow IEC 60601-1-8:
    STANDBY       white, one light circling       not monitoring yet
    NORMAL        green, steady
    ADVISORY      amber, slow flash (0.6 Hz)
    CRITICAL      red, fast flash (2 Hz)
    CRITICAL ACK  red, steady (acknowledged, sound off)
    CRITICAL BACK red and green in turn, 1 s each: CO2 is back, press the button to clear
    TECHNICAL     cyan, steady, with the Pico LED flickering
CR-1 states (monitor v0.3, kept for reference): PRESENT green, ABSENT red, WARMING UP amber,
FAULT cyan blinking.
Brightness is capped: 16 LEDs at full white would draw about 1 A from the USB port.
"""
import time
import digitalio

RING_PIXELS = 16
RING_BRIGHTNESS = 0.08      # 8 %: plenty indoors, about 0.1 A for the whole ring
RING_BPP = 3                # 3 for an RGB ring (GRB order), 4 for an RGBW ring

GREEN, RED, AMBER, CYAN, WHITE = (0, 255, 0), (255, 0, 0), (255, 110, 0), (0, 200, 255), (200, 200, 200)
DISPLAY = {                 # state: (colour, pattern)
    "STANDBY": (WHITE, "spin"),
    "NORMAL": (GREEN, "steady"),
    "ADVISORY": (AMBER, "slow"),
    "CRITICAL": (RED, "fast"),
    "CRITICAL ACK": (RED, "steady"),
    "CRITICAL BACK": (RED, "alternate"),   # red, then green: see ring_frame
    "TECHNICAL": (CYAN, "steady"),
    "LAMP GREEN": (GREEN, "steady"),     # power-up lamp test
    "LAMP AMBER": (AMBER, "steady"),
    "LAMP RED": (RED, "steady"),
    "LAMP CYAN": (CYAN, "steady"),
    "PRESENT": (GREEN, "steady"),
    "ABSENT": (RED, "steady"),
    "WARMING UP": (AMBER, "steady"),
    "FAULT": (CYAN, "blink"),
}
COLOURS = {k: v[0] for k, v in DISPLAY.items()}


def lit(pattern, now):
    if pattern == "slow":
        return (now % 1.6) < 0.8
    if pattern == "fast":
        return (now % 0.5) < 0.25
    if pattern == "blink":
        return (now % 0.2) < 0.1
    return True


def led_on(state, now):
    """Whether the Pico LED is lit for `state` at time `now` (seconds)."""
    if state in ("PRESENT", "NORMAL", "CRITICAL ACK", "CRITICAL BACK"):
        return True
    if state == "ABSENT":
        return (now % 2.0) < 0.12
    if state in ("WARMING UP", "STANDBY"):
        return (now % 1.0) < 0.5
    if state in ("FAULT", "TECHNICAL"):
        return (now % 0.2) < 0.1
    return lit(DISPLAY.get(state, (None, "steady"))[1], now)


def _pixel(colour):
    r, g, b = colour
    k = RING_BRIGHTNESS
    return [int(g * k), int(r * k), int(b * k)] + ([0] if RING_BPP == 4 else [])


def ring_frame(state, now):
    colour, pattern = DISPLAY.get(state, ((0, 0, 0), "steady"))
    off = _pixel((0, 0, 0))
    if pattern == "alternate":
        return bytearray(_pixel(colour if (now % 2.0) < 1.0 else GREEN) * RING_PIXELS)
    if pattern == "spin":
        k = int(now / 0.12) % RING_PIXELS
        px = []
        for i in range(RING_PIXELS):
            px += _pixel(colour) if i == k else off
        return bytearray(px)
    return bytearray((_pixel(colour) if lit(pattern, now) else off) * RING_PIXELS)


class Indicator:
    def __init__(self, led_pin, ring_pin=None):
        self.led = digitalio.DigitalInOut(led_pin)
        self.led.direction = digitalio.Direction.OUTPUT
        self.ring = None
        if ring_pin is not None:
            import neopixel_write
            self._write = neopixel_write.neopixel_write
            self.ring = digitalio.DigitalInOut(ring_pin)
            self.ring.direction = digitalio.Direction.OUTPUT
        self.state = "STANDBY"
        self._shown = None

    def show(self, state):
        self.state = state

    def tick(self, now):
        """Bring the LED and the ring up to date (the ring is written only when it changes)."""
        self.led.value = led_on(self.state, now)
        if self.ring is not None:
            frame = ring_frame(self.state, now)
            if frame != self._shown:
                self._write(self.ring, frame)
                self._shown = frame

    def wait(self, seconds, also=None):
        """Wait `seconds` while animating the LED and the ring. `also(now)` is called on every
        pass, for the speaker and the button."""
        end = time.monotonic() + seconds
        while True:
            now = time.monotonic()
            if also is not None:
                also(now)
            if now >= end:
                return
            self.tick(now)
            time.sleep(min(0.02, end - now))
