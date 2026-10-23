"""Winsen MH-Z19C NDIR CO2 sensor driver for CircuitPython 9 on the Pico 2 W.

UART, 9600 baud, 8N1, 3.3 V logic. The sensor needs 5 V power (VBUS).
Datasheet: Winsen MH-Z19C pins & terminal type manual, ver 1.2.

The two data wires sit on GP0 and GP1. On our cable the blue/green colours did not
match the datasheet pin order, so the driver works with the wires either way round:
  NORMAL  : Pico TX GP0 -> sensor RX,  sensor TX -> Pico RX GP1   (hardware UART)
  SWAPPED : Pico TX GP1 -> sensor RX,  sensor TX -> Pico RX GP0   (PIO UART)
"""
import time
import array
import board
import busio
import rp2pio

NORMAL = "normal"
SWAPPED = "swapped"
BAUD = 9600

_CMD_READ_CO2 = 0x86
_CMD_SELF_CAL = 0x79  # 0xA0 = on (factory default, re-zeroes every 24 h), 0x00 = off

# PIO programs from the Raspberry Pi pico-examples (uart_tx, uart_rx_mini), pre-assembled.
_TX_PROG = array.array("H", [0x9FA0, 0xF727, 0x6001, 0x0642])
_RX_PROG = array.array("H", [0x2020, 0xEA27, 0x4001, 0x0642])


def _checksum(pkt):
    return (0xFF - (sum(pkt[1:8]) & 0xFF) + 1) & 0xFF


def _command(cmd, b3=0):
    pkt = bytearray([0xFF, 0x01, cmd, b3, 0, 0, 0, 0, 0])
    pkt[8] = _checksum(pkt)
    return bytes(pkt)


def _find_reply(data, cmd):
    """The first valid 9-byte reply to `cmd` in `data`, or None."""
    if not data:
        return None
    for i in range(0, len(data) - 8):
        if data[i] == 0xFF and data[i + 1] == cmd:
            pkt = data[i:i + 9]
            if _checksum(pkt) == pkt[8]:
                return pkt
    return None


def _transact_normal(pkt, cmd, timeout):
    uart = busio.UART(board.GP0, board.GP1, baudrate=BAUD, timeout=timeout)
    try:
        uart.reset_input_buffer()
        uart.write(pkt)
        data = uart.read(9)
        if data and len(data) < 9:
            more = uart.read(9 - len(data))
            if more:
                data = data + more
        return _find_reply(data, cmd)
    finally:
        uart.deinit()


def _transact_swapped(pkt, cmd, timeout):
    rx = rp2pio.StateMachine(
        _RX_PROG, frequency=8 * BAUD, first_in_pin=board.GP0, pull_in_pin_up=1,
        auto_push=True, push_threshold=8, in_shift_right=True)
    try:
        tx = rp2pio.StateMachine(
            _TX_PROG, frequency=8 * BAUD, first_out_pin=board.GP1,
            first_sideset_pin=board.GP1, sideset_enable=True,
            initial_out_pin_state=1, initial_out_pin_direction=1,
            initial_sideset_pin_state=1, initial_sideset_pin_direction=1,
            out_shift_right=True)
        try:
            rx.clear_rxfifo()
            tx.write(pkt)
            data = bytearray()
            word = array.array("L", [0])
            t0 = time.monotonic()
            while len(data) < 18 and time.monotonic() - t0 < timeout:
                if rx.in_waiting:
                    rx.readinto(word)
                    data.append((word[0] >> 24) & 0xFF)  # 8 bits shifted in from the right
                    if len(data) >= 9 and _find_reply(bytes(data), cmd):
                        break
            return _find_reply(bytes(data), cmd)
        finally:
            tx.deinit()
    finally:
        rx.deinit()


def _transact(orientation, pkt, cmd, timeout=0.5):
    if orientation == NORMAL:
        return _transact_normal(pkt, cmd, timeout)
    return _transact_swapped(pkt, cmd, timeout)


def read_co2(orientation):
    """CO2 in ppm, or None if the sensor did not answer."""
    reply = _transact(orientation, _command(_CMD_READ_CO2), _CMD_READ_CO2)
    return None if reply is None else reply[2] * 256 + reply[3]


def set_self_calibration(orientation, on):
    """Turn the sensor's 24 h automatic baseline correction on or off."""
    _transact(orientation, _command(_CMD_SELF_CAL, 0xA0 if on else 0x00), _CMD_SELF_CAL, 0.3)


def probe():
    """Try both wire orientations. Returns (orientation, ppm) or (None, None)."""
    for orientation in (NORMAL, SWAPPED):
        try:
            ppm = read_co2(orientation)
        except Exception as e:
            print("mhz19c", orientation, "error:", e)
            ppm = None
        if ppm is not None:
            return orientation, ppm
    return None, None
