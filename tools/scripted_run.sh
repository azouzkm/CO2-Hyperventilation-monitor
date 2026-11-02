#!/bin/bash
# Team 6 - one scripted verification run for CR-1, with spoken cues.
#
#   bash tools/scripted_run.sh        (from the repository folder)
#   bash tools/scripted_run.sh --rate 20 --breaths 20 --label lung-20bpm-run03 --cue squeeze
#
# The Mac speaks: "Stand back" ... "Get ready, three, two, one" ... "breathe" on every beat ...
# "Stop, step back" ... "Run complete". Every cue is written into the same log as the Pico's
# readings, then the run is scored (tools/score_run.sh) for
#   ER-1  CO2 PRESENT shown within 3 breaths of the first cue
#   ER-2  CO2 ABSENT  shown within 30 s of the stop cue
# and appended to data/runs/results.csv.
#
# Before you start: the board is plugged in and past warm-up (the ring circles white and the
# line shows ABSENT), the test lung is ready, and nobody is within 1 m of the sensor. Close the
# dashboard, live_co2.sh, Thonny or Mu first: only one program can hold the serial port.

RATE=15          # breaths per minute
BREATHS=15       # cues to give
REST=120         # seconds of recovery recorded after the stop cue
SETTLE=20        # seconds of quiet before the countdown
CUE="breathe"    # word spoken on each beat ("squeeze" for the test lung bag)
LABEL=""
ER1=3
ER2=30
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --rate) RATE="$2"; shift 2 ;;
    --breaths) BREATHS="$2"; shift 2 ;;
    --rest) REST="$2"; shift 2 ;;
    --settle) SETTLE="$2"; shift 2 ;;
    --cue) CUE="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    --er1) ER1="$2"; shift 2 ;;
    --er2) ER2="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown option $1 (try --help)"; exit 1 ;;
  esac
done

cd "$(dirname "$0")/.." || exit 1
PORT=$(ls /dev/cu.usbmodem* 2>/dev/null | head -n 1)
if [ -z "$PORT" ]; then
  echo "No Pico found. Is the USB cable plugged in?"
  exit 1
fi
mkdir -p data/raw data/runs
LOG="data/raw/run_$(date +%Y-%m-%d_%H%M%S)${LABEL:+_$LABEL}.log"
PERIOD=$(awk -v r="$RATE" 'BEGIN { printf "%.3f", 60 / r }')

now() { perl -MTime::HiRes=time -e 'printf("%.3f\n", time)' 2>/dev/null || date +%s; }
sleep_until() { local d; d=$(awk -v a="$1" -v b="$(now)" 'BEGIN { x = a - b; if (x < 0) x = 0; printf "%.3f", x }'); sleep "$d"; }
mark() { printf '%s  ## %s\n' "$(date +%H:%M:%S)" "$*" >> "$LOG"; }
speak() { (say "$*" >/dev/null 2>&1 || afplay /System/Library/Sounds/Tink.aiff >/dev/null 2>&1) & }
state_now() { grep -E '^[0-9:]+  t= *[0-9]+ s ' "$LOG" | tail -n 1 | sed -nE 's/.*\| +(WARMING UP|ABSENT|PRESENT|FAULT).*/\1/p'; }

if ! exec 3<>"$PORT"; then
  echo "Could not open $PORT. Is another program (the dashboard, live_co2.sh, Thonny, Mu) using it?"
  exit 1
fi
stty -f "$PORT" raw -echo 2>/dev/null

( while IFS= read -r line <&3; do printf '%s  %s\n' "$(date +%H:%M:%S)" "${line%$'\r'}"; done >> "$LOG" ) &
READER=$!
touch "$LOG"
tail -n +1 -f "$LOG" &
TAILER=$!
cleanup() { kill "$READER" "$TAILER" 2>/dev/null; exec 3>&- 2>/dev/null; }
trap 'cleanup; echo; echo "Run stopped."; exit 1' INT TERM

echo "Scripted run: $BREATHS cues at $RATE per minute, then $REST s of recovery. Log: $LOG"
mark "RUN START label=${LABEL:-none} rate=$RATE breaths=$BREATHS rest=$REST cue=$CUE"
speak "Scripted run. Stand back and stay still."
sleep "$SETTLE"

STATE=$(state_now)
if [ "$STATE" != "ABSENT" ] && [ "$FORCE" -eq 0 ]; then
  mark "RUN ABORTED: board state was ${STATE:-unknown}, not ABSENT"
  speak "Not ready. The monitor must show absent first."
  cleanup
  echo
  echo "Not started: the board shows '${STATE:-no readings}', not ABSENT."
  echo "Wait for steady room air (or warm-up to finish) and run again, or add --force."
  exit 1
fi

speak "Get ready. Three. Two. One."
sleep 4
T0=$(now)
i=1
while [ "$i" -le "$BREATHS" ]; do
  sleep_until "$(awk -v t="$T0" -v p="$PERIOD" -v k="$i" 'BEGIN { printf "%.3f", t + (k - 1) * p }')"
  speak "$CUE"
  mark "CUE $i"
  i=$((i + 1))
done
sleep_until "$(awk -v t="$T0" -v p="$PERIOD" -v k="$BREATHS" 'BEGIN { printf "%.3f", t + k * p }')"
speak "Stop. Step back."
mark "STOP"

T1=$(now)
for left in 90 60 30; do
  if [ "$REST" -gt "$left" ]; then
    sleep_until "$(awk -v t="$T1" -v r="$REST" -v l="$left" 'BEGIN { printf "%.3f", t + r - l }')"
    speak "$left seconds"
  fi
done
sleep_until "$(awk -v t="$T1" -v r="$REST" 'BEGIN { printf "%.3f", t + r }')"
mark "RUN END"
speak "Run complete."
cleanup
trap - INT TERM

bash tools/score_run.sh "$LOG" "$ER1" "$ER2"
