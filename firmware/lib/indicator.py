"""Shows the CR-1 state on the Pico's LED now, and on the light ring once it is soldered.

Pico LED (one green LED):
    PRESENT     steady on
    ABSENT      one short blink every 2 s
    WARMING UP  slow even blink (0.5 s on, 0.5 s off)
    FAULT       fast blink, 5 per second
Light ring (NeoPixel Ring 16 on the D16 socket, GP16), colours chosen so no two states
look alike, brightness capped (16 LEDs at full white would draw about 1 A):
    PRESENT green · ABSENT red · WARMING UP amber · FAULT cyan, blinking
"""
import time
import digitalio

RING_PIXELS = 16
RING_BRIGHTNESS = 0.08      # 8 %: plenty indoors, about 0.1 A for the whole ring
RING_BPP = 3                # 3 for an RGB ring (GRB order), 4 for an RGBW ring
COLOURS = {
    "PRESENT": (0, 255, 0),
    "ABSENT": (255, 0, 0),
    "WARMING UP": (255, 110, 0),
    "FAULT": (0, 200, 255),
}


def led_on(state, now):
    """Whether the Pico LED is lit for `state` at time `now` (seconds)."""
    if state == "PRESENT":
        return True
    if state == "ABSENT":
        return (now % 2.0) < 0.12
    if state == "WARMING UP":
        return (now % 1.0) < 0.5
    return (now % 0.2) < 0.1            # FAULT


def ring_frame(state, lit):
    r, g, b = COLOURS.get(state, (0, 0, 0)) if lit else (0, 0, 0)
    k = RING_BRIGHTNESS
    px = [int(g * k), int(r * k), int(b * k)] + ([0] if RING_BPP == 4 else [])
    return bytearray(px * RING_PIXELS)


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
        self.state = "WARMING UP"
        self._shown = None

    def show(self, state):
        self.state = state

    def wait(self, seconds):
        """Wait `seconds` while animating the LED (and the ring, if fitted)."""
        end = time.monotonic() + seconds
        while True:
            now = time.monotonic()
            if now >= end:
                return
            lit = led_on(self.state, now)
            self.led.value = lit
            if self.ring is not None:
                ring_lit = lit if self.state == "FAULT" else True
                if (self.state, ring_lit) != self._shown:
                    self._write(self.ring, ring_frame(self.state, ring_lit))
                    self._shown = (self.state, ring_lit)
            time.sleep(min(0.05, end - now))
