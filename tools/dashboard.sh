#!/bin/bash
# Team 6 - the dashboard: starts the laptop service and opens the dashboard in the browser.
#
#   bash tools/dashboard.sh                    read the Pico over USB (from the repository folder)
#   bash tools/dashboard.sh --replay data/raw/co2_2026-10-25_011421.log --speed 5
#                                              play a recorded session instead (no board needed)
#   bash tools/dashboard.sh --lan              also let a phone or tablet on the same Wi-Fi open it
#   bash tools/dashboard.sh --no-messages      no messages to phones (bench tests that pull wires)
#
# Phone alerts: sign up at http://localhost:8000/register (see dashboard/README.md).
# The first run sets up Python packages (Flask, pyserial, certifi) in .venv/ inside this folder; it
# needs the internet once. Stop with Ctrl-C. The monitor keeps alarming on its own without this.
# If the service stops on an error, this script starts it again after 2 s (failure mode FM-5).
cd "$(dirname "$0")/.." || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. On a Mac, run: xcode-select --install   (or get it from python.org)"
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "This needs Python 3.9 or newer; this Mac has $(python3 --version 2>&1). Get a newer one from python.org."
  exit 1
fi

if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c 'import flask, serial, certifi' >/dev/null 2>&1; then
  echo "Setting up the dashboard's Python packages (Flask, pyserial, certifi) in .venv/ ..."
  if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv || { echo "Could not create .venv/ in this folder."; exit 1; }
  fi
  .venv/bin/python -m pip install --quiet --upgrade pip >/dev/null 2>&1
  if ! .venv/bin/python -m pip install --quiet flask pyserial certifi; then
    echo "Could not install the packages. Is the laptop online?"
    exit 1
  fi
  echo "Done."
fi

case " $* " in
  *" --replay "*) ;;
  *)
    if pgrep -f "tools/live_co2.sh|tools/scripted_run.sh" >/dev/null 2>&1; then
      echo "live_co2.sh or scripted_run.sh is still running in another Terminal window."
      echo "Stop it first (Ctrl-C in that window): only one program can read the Pico at a time."
      exit 1
    fi
    ;;
esac

HTTP_PORT=8000
prev=""
for a in "$@"; do
  [ "$prev" = "--http-port" ] && HTTP_PORT="$a"
  prev="$a"
done
( sleep 2; command -v open >/dev/null 2>&1 && open "http://localhost:$HTTP_PORT" ) >/dev/null 2>&1 &

# Keep the service running. Exit codes that mean "stop for good": 0 stopped on purpose (Ctrl-C or
# the window closed), 2 wrong options or no such recording, 3 the web port is taken, 129/130/143
# stopped by a signal. Anything else is a crash: start again, but give up after 3 crashes in a row
# that each came within 30 s of starting (something is wrong that a restart will not fix).
quick=0
while true; do
  started=$(date +%s)
  .venv/bin/python -m service "$@"
  code=$?
  case $code in
    0|2|3|129|130|143) exit $code ;;
  esac
  if [ $(( $(date +%s) - started )) -lt 30 ]; then quick=$((quick + 1)); else quick=1; fi
  if [ "$quick" -ge 3 ]; then
    echo
    echo "The service stopped with an error 3 times in a row (exit code $code). Not starting it again;"
    echo "the messages above say why. The monitor keeps alarming on its own."
    exit "$code"
  fi
  echo
  echo "The service stopped with an error (exit code $code). Starting it again in 2 s..."
  echo "The monitor kept alarming on its own; the dashboard reconnects by itself."
  sleep 2
done
