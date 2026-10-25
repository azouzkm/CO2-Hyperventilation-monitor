"""Laptop-side tests for firmware/lib/mhz19c.py, using fake CircuitPython modules.

Run from the repository root:   python -m pytest tests/
(or without pytest:              python tests/test_mhz19c.py)
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

READ_CMD = bytes([0xFF, 0x01, 0x86, 0, 0, 0, 0, 0, 0x79])


def reply(ppm):
    r = bytearray([0xFF, 0x86, ppm >> 8, ppm & 0xFF, 0x47, 0, 0, 0, 0])
    r[8] = (0xFF - (sum(r[1:8]) & 0xFF) + 1) & 0xFF
    return bytes(r)


class FakeSensor:
    """Answers on whichever orientation it is wired for; None = not answering."""
    wiring = None
    ppm = 612
    sent = []


class FakeUART:
    def __init__(self, tx, rx, **kw):
        assert (tx, rx) == ("GP0", "GP1")
        self.buf = b""

    def reset_input_buffer(self):
        pass

    def write(self, b):
        FakeSensor.sent.append(bytes(b))
        if FakeSensor.wiring == "normal" and bytes(b) == READ_CMD:
            self.buf = reply(FakeSensor.ppm)

    @property
    def in_waiting(self):
        return len(self.buf)

    def read(self, n):
        out, self.buf = self.buf[:n], self.buf[n:]
        return out or None

    def deinit(self):
        pass


_rx_fifo = []


class FakeStateMachine:
    def __init__(self, prog, **kw):
        self.is_rx = "first_in_pin" in kw
        if self.is_rx:
            assert kw["first_in_pin"] == "GP0"
        else:
            assert kw["first_out_pin"] == "GP1"

    def clear_rxfifo(self):
        _rx_fifo.clear()

    def write(self, b):
        FakeSensor.sent.append(bytes(b))
        if FakeSensor.wiring == "swapped" and bytes(b) == READ_CMD:
            # a stray byte first, then the reply, each as a 32-bit FIFO word (data in bits 31:24)
            _rx_fifo.extend(x << 24 for x in b"\x00" + reply(FakeSensor.ppm))

    @property
    def in_waiting(self):
        return len(_rx_fifo)

    def readinto(self, buf):
        buf[0] = _rx_fifo.pop(0)

    def deinit(self):
        pass


sys.modules["board"] = types.SimpleNamespace(GP0="GP0", GP1="GP1", LED="LED")
sys.modules["busio"] = types.SimpleNamespace(UART=FakeUART)
sys.modules["rp2pio"] = types.SimpleNamespace(StateMachine=FakeStateMachine)

import mhz19c  # noqa: E402


def test_read_command_bytes():
    assert mhz19c._command(0x86) == READ_CMD


def test_probe_normal_wiring():
    FakeSensor.wiring, FakeSensor.ppm = "normal", 612
    assert mhz19c.probe() == ("normal", 612)


def test_probe_swapped_wiring():
    FakeSensor.wiring, FakeSensor.ppm = "swapped", 733
    assert mhz19c.probe() == ("swapped", 733)


def test_probe_no_sensor():
    FakeSensor.wiring = None
    assert mhz19c.probe() == (None, None)


def test_no_answer_keeps_calling_idle_while_it_waits():
    # 25 Oct: with a data wire pulled the reads waited 1.5 s per second and the ring froze
    FakeSensor.wiring = None
    calls = []
    assert mhz19c.probe(idle=calls.append) == (None, None)
    assert len(calls) > 20                      # both orientations, the whole wait
    assert calls[-1] - calls[0] > 0.8


def test_bad_checksum_rejected():
    bad = bytearray(reply(500))
    bad[8] ^= 0xFF
    assert mhz19c._find_reply(bytes(bad), 0x86) is None


def test_self_calibration_off_command():
    FakeSensor.sent.clear()
    mhz19c.set_self_calibration("normal", False)
    pkt = FakeSensor.sent[-1]
    assert pkt[:4] == bytes([0xFF, 0x01, 0x79, 0x00]) and pkt[8] == 0x86


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
