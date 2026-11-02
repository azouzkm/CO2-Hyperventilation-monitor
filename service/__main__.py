"""Start the service:  python3 -m service      (from the repository folder; tools/dashboard.sh does it)

    --port /dev/cu.usbmodem1101   use this serial port instead of finding the Pico by itself
    --replay data/raw/x.log       play a recorded session instead of reading the board
    --speed 5                     replay 5 times faster than real time
    --loop                        start the replay again at the end
    --http-port 8001              if 8000 is taken
    --lan                         let other devices on the same Wi-Fi open the dashboard
                                  (a phone or tablet at the bench); the default is this laptop only
    --db data/other.sqlite        another database file (a replay uses data/replay.sqlite, so
                                  replays never mix with the real readings in data/co2monitor.sqlite)
    --no-messages                 send no phone messages at all (for bench tests that pull wires);
                                  a replay never sends alarm messages, only sign-up test messages

Exit codes: 0 stopped on purpose (Ctrl-C, closing the window), 3 the web port is taken,
anything else an error. tools/dashboard.sh starts the service again after an error, not after 0 or 3.
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import signal
import socket
import sys
import time

PORT_TAKEN = 3

from .core import ROOT, Service, load_config
from .logger import RawLog, ReplaySource, SerialSource
from .main import create_app


def lan_address() -> str | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))           # no packet is sent; this only picks the outgoing interface
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def port_free(host: str, port: int) -> bool:
    """True if the web server can take this port (checked the way the server binds it)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main(argv=None) -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(prog="python3 -m service", description="Team 6 CO2 monitor: laptop service")
    ap.add_argument("--port", help="serial port of the Pico (found by itself if left out)")
    ap.add_argument("--replay", help="play a recorded log from data/raw/ instead of reading the board")
    ap.add_argument("--speed", type=float, default=1.0, help="replay speed (1 = real time)")
    ap.add_argument("--loop", action="store_true", help="start the replay again when it ends")
    ap.add_argument("--http-port", type=int, default=cfg["http_port"])
    ap.add_argument("--lan", action="store_true", help="serve the dashboard to other devices on this network")
    ap.add_argument("--db", help="SQLite file (default data/co2monitor.sqlite; data/replay.sqlite for a replay)")
    ap.add_argument("--no-messages", action="store_true", help="send no phone messages at all")
    args = ap.parse_args(argv)

    def say(text: str) -> None:
        print(text, flush=True)

    if args.db:
        cfg["db_path"] = os.path.abspath(args.db)
    elif args.replay:                          # replays never mix with the real readings,
        cfg["people_db"] = cfg["db_path"]      # but they share the people signed up for messages
        cfg["db_path"] = os.path.join(ROOT, "data", "replay.sqlite")
    if args.replay and not os.path.isfile(args.replay):
        say("No such recording: %s" % args.replay)
        logs = sorted(glob.glob(os.path.join(cfg["raw_log_dir"], "*.log")))[-5:]
        if logs:
            say("The most recent ones in data/raw/:")
            for p in logs:
                say("  " + os.path.relpath(p, ROOT))
        return 2
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    if not port_free(host, args.http_port):
        say("Port %d is taken: is the dashboard already running in another Terminal window?" % args.http_port)
        say("Use that window, close it first (Ctrl-C), or start this one with --http-port 8001.")
        return PORT_TAKEN
    if args.replay:
        def source(on_line, on_status):
            return ReplaySource(args.replay, on_line, on_status, speed=args.speed, loop=args.loop)
        raw_log = None                         # a replay is not new evidence
    else:
        def source(on_line, on_status):
            return SerialSource(on_line, on_status, port=args.port)
        raw_log = RawLog(cfg["raw_log_dir"])

    messages = "--no-messages" if args.no_messages else ("replay" if args.replay else None)
    service = Service(cfg, source, raw_log=raw_log, echo=say, preload=not args.replay, messages=messages)
    app = create_app(service)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)      # no line per dashboard request
    try:
        import flask.cli
        flask.cli.show_server_banner = lambda *a, **k: None    # the lines below say what matters
    except (ImportError, AttributeError):
        pass

    say("")
    say("Team 6 CO2 monitor: dashboard service")
    say("Dashboard:  http://localhost:%d" % args.http_port)
    if args.lan:
        ip = lan_address()
        say("On this Wi-Fi: http://%s:%d   (anyone on this network can open it)" % (ip or "<this laptop's address>",
                                                                                  args.http_port))
    say("Database:   %s" % os.path.relpath(cfg["db_path"], ROOT))
    if raw_log is not None:
        say("Raw log:    %s" % os.path.relpath(raw_log.path, ROOT))
    signed_up = sum(1 for u in service.store.users() if u.get("active"))
    if messages == "--no-messages":
        say("Phones:     off (--no-messages)")
    elif messages == "replay":
        say("Phones:     a replay sends no alarm messages (sign-up test messages still go)")
    else:
        say("Phones:     %d %s signed up for alarm messages; sign up at http://localhost:%d/register"
            % (signed_up, "person" if signed_up == 1 else "people", args.http_port))
    say("Stop with Ctrl-C. The monitor keeps alarming on its own without this service.")
    say("")

    def stop_on_signal(signum, frame):
        raise KeyboardInterrupt            # the same clean stop as Ctrl-C: open alarm records are closed
    for name in ("SIGTERM", "SIGHUP"):     # kill, or the Terminal window closed
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop_on_signal)

    service.start()
    try:
        app.run(host=host, port=args.http_port, threaded=True, use_reloader=False)
    except OSError as e:
        say("")
        say("Could not start the web server on port %d (%s)." % (args.http_port, e))
        say("Is the dashboard already running in another Terminal window? Close it, or add --http-port 8001.")
        return PORT_TAKEN
    except SystemExit as e:                # the web server gives up this way if the port went in the meantime
        if e.code not in (None, 0):
            say("Is the dashboard already running in another Terminal window? Close it, or add --http-port 8001.")
            return PORT_TAKEN
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()
        say("")
        say("Stopped at %s." % time.strftime("%H:%M:%S"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
