# Project 6 — Exhaled CO2 monitor — Pico 2 W firmware (CircuitPython)
# Runs on the board: read sensor -> local rules -> light/speaker -> print one JSON line per sample
# Key: the board alarms on its own, so a dead laptop/service cannot silence it (matches failure mode FM-5 thinking)

import board
import time
import json

# --- Config (keep consistent with the config.json the service reads; values need calibration) ---
SAMPLE_INTERVAL_S = 0.2        # 200 ms = 5 Hz; adjust to your sensor's real rate
CO2_ABSENT_PCT = 0.1           # below this = "no CO2"
ADVISORY_FALL_PCT = 2.0        # concentration falls below this -> advisory
RETURN_TO_RANGE_S = 30.0       # seconds back in range before advisory clears

# --- Hardware init (TODO: swap in the real drivers) ---
# ring = neopixel.NeoPixel(board.GP0, 16)          # three-colour indicator ring
# tone = ...                                        # PAM8302 + speaker
# ack_button = digitalio.DigitalInOut(board.GP3)    # bedside acknowledge button
# sensor = ...                                      # NDIR CO2 module (UART/I2C)

def read_co2_pct():
    """Read the raw sensor -> apply calibration (m*x+b) -> return concentration in percent."""
    # TODO: read the raw value, apply the calibration constants
    return 0.0


def apply_rules(co2_pct, state, below_since):
    """
    Four-state machine (same logic as service/rules_engine.py).
    Returns (state, below_since).
    """
    now = time.monotonic()
    # TODO: complete the normal / advisory / critical / technical transition logic
    # critical must latch; technical must never become apnoea (critical)
    return "normal", below_since


def show(state):
    """Map state to light colour + sound."""
    # TODO: normal=green silent / advisory=amber 3-pulse / critical=red 10-pulse latched / technical=cyan chirp
    pass


state = "normal"
below_since = None

while True:
    t = time.monotonic()
    co2 = read_co2_pct()

    state, below_since = apply_rules(co2, state, below_since)
    show(state)

    # one JSON line per sample (serial -> the service's logger consumes it)
    print(json.dumps({
        "t": round(t, 3),
        "co2_pct": round(co2, 2),
        "state": state,
    }))
    time.sleep(SAMPLE_INTERVAL_S)
