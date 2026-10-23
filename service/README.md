# Service (laptop)

Skeleton from the team's first commit: a FastAPI app, serial ingest into SQLite, and the four-state
rules engine. It is not connected to the board yet.

| File | What it does now |
| --- | --- |
| `main.py` | FastAPI app with `/` (placeholder), `/api/latest` (placeholder reading) and `/api/ack` |
| `logger.py` | Reads one JSON line per sample from the serial port; creates the `readings` table in SQLite (WAL mode) |
| `rules_engine.py` | The four alarm states (Normal, Advisory, Critical, Technical) as pure Python, so it can be unit-tested |

Run it from the repository folder:

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn service.main:app --reload
```

Then open <http://localhost:8000/docs> to see and try the endpoints.

## Still to do

- Read the board: firmware v0.3 prints text lines, while the logger expects one JSON line per sample.
  The serial port also needs finding automatically (`COM3` is a Windows name; on a Mac it is
  `/dev/cu.usbmodem…`).
- The alarms, acknowledgements, calibrations and users tables (users opt in, with the consent
  timestamp stored).
- Load the thresholds from `config.json`, the file the firmware uses too.
- Notifier to registered, opted-in course participants. No patient identifiers in any message.
- Tests for the rules engine in `tests/`.

Secrets such as messaging API keys go in a local `.env` file, which git ignores.
