"""
Rules engine — implements the four-state alarm from the project card's Figure 3.

State       Light    Sound              Trigger
normal      green    silent             concentration / rate in range
advisory    amber    3-pulse            concentration or breathing rate falls past threshold (clears after 30 s back in range)
critical    red      10-pulse, latched  CO2 absent while the circuit reads connected
technical   cyan     short chirp        blocked / disconnected line, sensor fault, zero drift

Golden rule (CR-3): a blocked line / fault = technical, never presented as apnoea (critical).
This file is pure logic with no I/O, so it can be unit-tested with pytest (required by the project card).
"""

from dataclasses import dataclass
from enum import Enum


class State(Enum):
    NORMAL = "normal"
    ADVISORY = "advisory"
    CRITICAL = "critical"
    TECHNICAL = "technical"


@dataclass
class Rules:
    co2_absent_pct: float = 0.1
    advisory_fall_pct: float = 2.0
    return_to_range_s: float = 30.0
    critical_latched: bool = True

    # internal state
    _below_since: float | None = None
    _critical_latched: bool = False

    def update(self, co2_pct: float, circuit_connected: bool,
               line_fault: bool, now: float) -> State:
        """
        co2_pct             : current concentration (calibrated, in percent)
        circuit_connected   : whether the sampling circuit reports itself as connected
        line_fault          : whether a blocked / disconnected line, sensor fault or zero drift is detected
        now                 : monotonic clock seconds
        """
        # 1) technical fault has priority, and never counts as apnoea
        if line_fault or not circuit_connected:
            self._reset()
            return State.TECHNICAL

        # 2) CO2 present -> normal, reset the below-range timer, clear advisory
        if co2_pct >= self.advisory_fall_pct:
            self._below_since = None
            return State.NORMAL

        # 3) CO2 fully absent -> critical (latched)
        if co2_pct < self.co2_absent_pct:
            if self.critical_latched:
                self._critical_latched = True
            return State.CRITICAL

        # 4) below threshold but not absent -> time it; sustained -> advisory
        if self._below_since is None:
            self._below_since = now
        if now - self._below_since >= self.return_to_range_s:
            return State.ADVISORY
        return State.NORMAL

    def acknowledge(self):
        """Bedside ACK: silence for 2 minutes, keep the visual state, log who and when."""
        self._critical_latched = False

    def _reset(self):
        self._below_since = None
