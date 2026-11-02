"""Serial ingest (interface IF-6): the USB link to the Pico, and the raw log of everything it says.

The board appears on the laptop as a serial port: /dev/cu.usbmodem... on a Mac, /dev/ttyACM... on
Linux, COM... on Windows. The port is found by itself, and found again if the cable is pulled and
plugged back in. Every line is saved to data/raw/co2_<date>_<time>.log with the laptop's clock in
front of it, exactly like tools/live_co2.sh, so the raw logs stay the evidence for the
verification report.

pyserial is used when it is installed (it is in requirements.txt). Without it, a Mac or Linux
laptop reads the port with the standard library (termios), as the shell tools do.
"""
from __future__ import annotations

import glob
import os
import select
import sys
import threading
import time

try:
    import serial                      # pyserial
    import serial.tools.list_ports
except Exception:                      # not installed, or a version this Python cannot load:
    serial = None                      # the standard-library fallback works on Mac and Linux

PICO_VIDS = (0x239A, 0x2E8A)           # Adafruit (CircuitPython) and Raspberry Pi USB vendor ids


def find_port() -> str | None:
    """The Pico's serial port, or None if it is not plugged in."""
    if serial is not None:
        try:
            for p in serial.tools.list_ports.comports():
                if p.vid in PICO_VIDS:
                    return p.device
        except Exception:              # the port list can fail on some systems; the patterns below still work
            pass
    for pattern in ("/dev/cu.usbmodem*", "/dev/ttyACM*"):
        found = sorted(glob.glob(pattern))
        if found:
            return found[0]
    return None


class PortBusy(Exception):
    pass


def _exclusive(fd: int) -> None:
    """Stop other programs (live_co2.sh, screen) opening the port while the service reads it:
    two readers would each get half of every line."""
    try:
        import fcntl
        import termios
        req = getattr(termios, "TIOCEXCL", None)
        if req is not None:
            fcntl.ioctl(fd, req)
    except (OSError, ImportError):
        pass


class _TermiosPort:
    """Minimal serial port on the standard library: raw mode, no echo, reads with a timeout."""

    def __init__(self, path: str):
        import termios
        import tty
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as e:
            raise PortBusy(str(e)) from e
        try:
            tty.setraw(self.fd)
            attrs = termios.tcgetattr(self.fd)
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        except termios.error:
            pass                                       # a pseudo-terminal in the tests
        _exclusive(self.fd)

    def read(self, timeout: float) -> bytes:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return b""
        try:
            data = os.read(self.fd, 4096)
        except BlockingIOError:
            return b""
        if not data:
            raise OSError("the port closed")
        return data

    def write(self, data: bytes) -> None:
        os.write(self.fd, data)

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


class _PyserialPort:
    def __init__(self, path: str):
        try:
            self.ser = serial.Serial(path, 115200, timeout=0, exclusive=True)
        except (serial.SerialException, OSError) as e:
            raise PortBusy(str(e)) from e
        try:
            _exclusive(self.ser.fileno())
        except Exception:
            pass

    def read(self, timeout: float) -> bytes:
        end = time.monotonic() + timeout
        while True:
            waiting = self.ser.in_waiting
            if waiting:
                return self.ser.read(waiting)
            if time.monotonic() >= end:
                return b""
            time.sleep(0.02)

    def write(self, data: bytes) -> None:
        self.ser.write(data)
        self.ser.flush()

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass


def open_port(path: str, backend: str | None = None):
    """backend "pyserial" or "termios"; by default pyserial when it is installed."""
    backend = backend or os.environ.get("CO2_SERIAL_BACKEND") or ("pyserial" if serial is not None else "termios")
    if backend == "pyserial":
        return _PyserialPort(path)
    return _TermiosPort(path)


class _LinkError(Exception):
    pass


class RawLog:
    """data/raw/co2_<date>_<time>.log, one line per line received, the laptop's clock in front.

    The file is created with the first line, so a session that receives nothing leaves no empty log
    among the evidence."""

    def __init__(self, folder: str, prefix: str = "co2"):
        self.folder = folder
        self.path = os.path.join(folder, "%s_%s.log" % (prefix, time.strftime("%Y-%m-%d_%H%M%S")))
        self._f = None
        self._closed = False
        self._lock = threading.Lock()

    def write(self, line: str, now: float | None = None) -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime(now if now is not None else time.time()))
        with self._lock:
            if self._closed:
                return
            if self._f is None:
                os.makedirs(self.folder, exist_ok=True)
                self._f = open(self.path, "a", buffering=1, encoding="utf-8")
            self._f.write("%s  %s\n" % (stamp, line))

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._f is not None:
                self._f.close()
                self._f = None


class SerialSource(threading.Thread):
    """Reads the board line by line and hands each line to `on_line(text, now)`.

    Keeps going when the cable is pulled: it reports the problem through `on_status(text)` and
    tries the port again every 2 s. `send(text)` writes a command to the board (e.g. "ACK\\n").
    """

    def __init__(self, on_line, on_status, port: str | None = None):
        super().__init__(daemon=True, name="serial-ingest")
        self.on_line, self.on_status = on_line, on_status
        self.fixed_port = port
        self.port = None
        self._io = None
        self._io_lock = threading.Lock()
        self._stop = threading.Event()

    def send(self, text: str) -> bool:
        with self._io_lock:
            if self._io is None:
                return False
            try:
                self._io.write(text.encode("ascii"))
                return True
            except OSError:
                return False

    def stop(self) -> None:
        self._stop.set()

    def _deliver(self, text: str) -> None:
        try:
            self.on_line(text, time.time())
        except Exception:                              # a bug downstream must not stop the reading
            import traceback
            self.on_status("Error while handling a line from the Pico:\n" + traceback.format_exc())

    def run(self) -> None:
        said = None
        while not self._stop.is_set():
            path = self.fixed_port or find_port()
            if path is None:
                if said != "missing":
                    self.on_status("No Pico found. Is the USB cable plugged in? Still looking...")
                    said = "missing"
                self._stop.wait(2.0)
                continue
            try:
                io = open_port(path)
            except PortBusy as e:
                if said != "busy":
                    self.on_status("Could not open %s (%s). Close Thonny, Mu, screen or tools/live_co2.sh: "
                                   "only one program can read the Pico at a time. Still trying..." % (path, e))
                    said = "busy"
                self._stop.wait(2.0)
                continue
            with self._io_lock:
                self._io, self.port = io, path
            self.on_status("Reading the Pico on %s" % path)
            said = None
            buf = b""
            try:
                while not self._stop.is_set():
                    try:
                        buf += io.read(0.5)
                    except Exception as e:             # pulled cable: OSError or serial.SerialException
                        raise _LinkError(e)
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        text = raw.decode("utf-8", errors="replace").strip("\r")
                        if text.strip():
                            self._deliver(text)
                    if len(buf) > 65536:
                        buf = b""
            except _LinkError as e:
                self.on_status("Lost the Pico on %s (%s). Plug it back in; looking again..." % (path, e.args[0]))
            finally:
                with self._io_lock:
                    self._io = None
                io.close()
                self.port = None
            self._stop.wait(1.0)


class ReplaySource(threading.Thread):
    """Plays a recorded log (data/raw/*.log) into the service as if the board were sending it.

    For demonstrations without the board, and for testing. `speed` 1 = real time.
    """

    def __init__(self, path: str, on_line, on_status, speed: float = 1.0, loop: bool = False):
        super().__init__(daemon=True, name="replay")
        self.path, self.on_line, self.on_status = path, on_line, on_status
        self.speed, self.loop = max(speed, 0.01), loop
        self.port = "replay of %s" % os.path.basename(path)
        self._stop = threading.Event()

    def send(self, text: str) -> bool:
        return False                                   # nobody to send to: acks stay local

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        from .parse import strip_clock
        while not self._stop.is_set():
            self.on_status("Replaying %s at %gx speed" % (self.path, self.speed))
            with open(self.path, encoding="utf-8", errors="replace") as f:
                lines = [ln.rstrip("\n") for ln in f]
            prev = None
            for raw in lines:
                if self._stop.is_set():
                    return
                stamp = raw[:8] if len(raw) > 10 and raw[2] == ":" and raw[5] == ":" else None
                if stamp is not None and prev is not None and stamp != prev:
                    h1, m1, s1 = (int(x) for x in prev.split(":"))
                    h2, m2, s2 = (int(x) for x in stamp.split(":"))
                    gap = ((h2 - h1) * 3600 + (m2 - m1) * 60 + (s2 - s1)) % 86400
                    self._stop.wait(min(gap, 10) / self.speed)
                if stamp is not None:
                    prev = stamp
                text = strip_clock(raw)
                if text.strip():
                    try:
                        self.on_line(text, time.time())
                    except Exception:                  # a bug downstream must not stop the replay
                        import traceback
                        self.on_status("Error while handling a recorded line:\n" + traceback.format_exc())
            if not self.loop:
                self.on_status("Replay finished; the dashboard now shows the link as lost.")
                return
