#!/bin/bash
# Team 6 - live view of the Pico's readings in Terminal, saved to data/raw/ as they arrive.
#
#   bash tools/live_co2.sh        (from the repository folder)
#
# Each line gets the Mac's clock time in front of it. Stop with Ctrl-C.
# Only one program can hold the Pico's serial port: close Thonny/Mu and tools/dashboard.sh first.
# Firmware v0.5 also prints one JSON line per reading for the dashboard: it is saved in the log but
# not shown here.
cd "$(dirname "$0")/.." || exit 1

PORT=$(ls /dev/cu.usbmodem* 2>/dev/null | head -n 1)
if [ -z "$PORT" ]; then
  echo "No Pico found. Is the USB cable plugged in?"
  exit 1
fi

mkdir -p data/raw
LOG="data/raw/co2_$(date +%Y-%m-%d_%H%M%S).log"

if ! exec 3<>"$PORT"; then
  echo "Could not open $PORT. Is another program (the dashboard, Thonny, Mu, screen) using it?"
  exit 1
fi
stty -f "$PORT" raw -echo 2>/dev/null   # pass bytes through untouched; never echo back to the Pico

echo "Reading the Pico on $PORT"
echo "Saving to $LOG"
echo "Press Ctrl-C to stop."
echo

while IFS= read -r line <&3; do
  line=${line%$'\r'}
  printf '%s  %s\n' "$(date +%H:%M:%S)" "$line"
done | tee -a "$LOG" | grep --line-buffered -v '^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]  {'

