"""
Serial ingest -> SQLite. The firmware prints one JSON line per sample; this consumes them
and writes them to the database.

Table structure (matches the worked example report's Section 7 data model; adjust as needed):
  readings(ts_utc, co2_pct, state, quality)
  alarms(alarm_id, priority, ts_raised, ts_cleared, value_at_raise)
  acks(alarm_id, ts, user_id, method)
  calibrations(device_id, ts, slope, intercept, reference, operator, rms_resid)
"""

import json
import sqlite3
import serial  # pyserial


DB_PATH = "co2monitor.sqlite"


def init_db(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            ts_utc   TEXT PRIMARY KEY,
            co2_pct  REAL,
            state    TEXT,
            quality  INTEGER
        )""")
    # TODO: add the alarms / acks / calibrations tables
    return conn


def read_serial_lines(port: str = "COM3", baud: int = 115200):
    """Read the serial port line by line, yielding parsed dicts."""
    with serial.Serial(port, baud, timeout=1) as ser:
        for raw in ser:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # skip bad lines; don't let one bad line kill the whole service
