"""
FastAPI service: serial ingest thread + REST endpoints + serves the dashboard page.
Run with: uvicorn service.main:app --reload
"""

from fastapi import FastAPI
from fastapi.responses import FileResponse

from . import logger

app = FastAPI(title="Project 6 — Exhaled CO2 monitor")


@app.get("/")
def dashboard():
    """Serve the dashboard HTML."""
    # TODO: point at dashboard/index.html
    return {"msg": "dashboard served here"}


@app.get("/api/latest")
def latest():
    """Return the latest reading."""
    # TODO: query the latest row from SQLite
    return {"co2_pct": 0.0, "state": "normal"}


@app.post("/api/ack")
def acknowledge():
    """Acknowledge the alarm from the bedside/UI, recording who + when."""
    # TODO: write to the acks table
    return {"ack": True}


# TODO: start a background thread read_serial_lines -> logger.init_db to write to the DB
