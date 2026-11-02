#!/bin/bash
# Team 6 - one paced-breathing run for CR-4 (breathing rate, and the advisory on slow breathing),
# with spoken cues.
#
#   bash tools/rate_run.sh                                     (from the repository folder)
#   bash tools/rate_run.sh --plan 12:120,6:150,12:120 --cue squeeze --label lung-run01
#
# The plan is a list of phases, "breaths per minute:seconds", run one after the other. The Mac says
# the cue word once per breath at each phase's rate (the first cue of a slower phase says "slower",
# of a faster one "faster"). Breathe out, or squeeze the test-lung bag, on every cue. Then "Stop.
# Step back." and REST seconds of recovery. Every cue is written into the same log as the Pico's
# readings, and the run is scored by tools/score_rate_run.py for
#   ER-7  the breathing rate shown matches each phase's paced rate
#   ER-8  slowing below 8/min raises the ADVISORY in time, and steady breathing never does
# and appended to data/runs/rate_results.csv.
#
# Before you start: the board runs the firmware with CR-4 (its lines end in "RR ..."), is past
# warm-up and shows ABSENT, air moves through the flow-cell (in a sealed cell the breaths pile up
# and no rate can be read), and nobody is within 1 m of the sensor. Close live_co2.sh,
# dashboard.sh, Thonny or Mu first: only one program can hold the serial port.

PLAN="15:150,6:150,15:120"   # 15/min for 150 s, slow to 6/min for 150 s, back to 15/min for 120 s
CUE="breathe"                # word spoken on each breath ("squeeze" for the test-lung bag)
REST=60                      # seconds recorded after the stop cue
SETTLE=20                    # seconds of quiet before the countdown
LABEL=""
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --plan) PLAN="$2"; shift 2 ;;
    --cue) CUE="$2"; shift 2 ;;
    --rest) REST="$2"; shift 2 ;;
    --settle) SETTLE="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) sed -n '2,23p' "$0"; exit 0 ;;
    *) echo "Unknown option $1 (try --help)"; exit 1 ;;
  esac
done

# the plan: rates and durations, checked before anything starts
RATES=()
SECS=()
NUM='^[0-9]+([.][0-9]+)?$'
INT='^[0-9]+$'
IFS=',' read -r -a PHASES <<< "$PLAN"
for p in "${PHASES[@]}"; do
  r=${p%%:*}
  d=${p##*:}
  if ! [[ $r =~ $NUM && $d =~ $INT ]] || [ "$p" = "$r" ]; then
    echo "Bad plan '$PLAN': write it as rate:seconds,rate:seconds (e.g. 15:150,6:150,15:120)"
    exit 1
  fi
  if ! awk -v r="$r" 'BEGIN { exit !(r >= 2 && r <= 40) }'; then
    echo "Bad plan: $r breaths per minute (use 2 to 40)"
    exit 1
  fi
  RATES+=("$r")
  SECS+=("$d")
done
TOTAL=0
for d in "${SECS[@]}"; do TOTAL=$((TOTAL + d)); done

cd "$(dirname "$0")/.." || exit 1
PORT=${PICO_PORT:-$(ls /dev/cu.usbmodem* 2>/dev/null | head -n 1)}   # PICO_PORT: another port, e.g. for a test
if [ -z "$PORT" ]; then
  echo "No Pico found. Is the USB cable plugged in?"
  exit 1
fi
mkdir -p data/raw data/runs
LOG="data/raw/rate_$(date +%Y-%m-%d_%H%M%S)${LABEL:+_$LABEL}.log"

now() { perl -MTime::HiRes=time -e 'printf("%.3f\n", time)' 2>/dev/null || date +%s; }
sleep_until() { local d; d=$(awk -v a="$1" -v b="$(now)" 'BEGIN { x = a - b; if (x < 0) x = 0; printf "%.3f", x }'); sleep "$d"; }
mark() { printf '%s  ## %s\n' "$(date +%H:%M:%S)" "$*" >> "$LOG"; }
speak() { (say "$*" >/dev/null 2>&1 || afplay /System/Library/Sounds/Tink.aiff >/dev/null 2>&1) & }
state_now() { grep -E '^[0-9:]+  t= *[0-9]+ s ' "$LOG" | tail -n 1 | sed -nE 's/.*\| +(WARMING UP|ABSENT|PRESENT|FAULT).*/\1/p'; }

if ! exec 3<>"$PORT"; then
  echo "Could not open $PORT. Is another program (live_co2.sh, dashboard.sh, Thonny, Mu) using it?"
  exit 1
fi
stty -f "$PORT" raw -echo 2>/dev/null

( while IFS= read -r line <&3; do printf '%s  %s\n' "$(date +%H:%M:%S)" "${line%$'\r'}"; done >> "$LOG" ) &
READER=$!
touch "$LOG"
tail -n +1 -f "$LOG" | grep --line-buffered -v '^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]  {' &
TAILER=$!
cleanup() { kill "$READER" "$TAILER" 2>/dev/null; pkill -P $$ tail 2>/dev/null; exec 3>&- 2>/dev/null; }
trap 'cleanup; echo; echo "Run stopped."; exit 1' INT TERM

echo "Paced run: $PLAN (rate per minute:seconds), $TOTAL s of breathing, then $REST s of recovery."
echo "Log: $LOG"
mark "RUN START label=${LABEL:-none} plan=$PLAN cue=$CUE rest=$REST"
speak "Paced breathing run. Stand back and stay still."
sleep "$SETTLE"

STATE=$(state_now)
if [ -z "$(grep -E '  t= *[0-9]+ s .* RR ' "$LOG" | tail -n 1)" ] && [ "$FORCE" -eq 0 ]; then
  mark "RUN ABORTED: the board's lines show no breathing rate (RR): load the firmware with CR-4"
  speak "Not ready. Load the new firmware first."
  cleanup
  echo
  echo "Not started: the board's lines have no 'RR' column. Load the firmware with CR-4 first."
  exit 1
fi
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
START=$T0
n=0
for i in "${!RATES[@]}"; do
  r=${RATES[$i]}
  d=${SECS[$i]}
  word=$CUE
  if [ "$i" -gt 0 ]; then
    word=$(awk -v a="$r" -v b="${RATES[$((i - 1))]}" -v c="$CUE" 'BEGIN { print (a < b) ? "slower" : (a > b) ? "faster" : c }')
  fi
  END=$(awk -v s="$START" -v d="$d" 'BEGIN { printf "%.3f", s + d }')
  sleep_until "$START"
  mark "PHASE $((i + 1)) rate=$r seconds=$d"
  k=0
  while :; do
    at=$(awk -v s="$START" -v r="$r" -v k="$k" 'BEGIN { printf "%.3f", s + k * 60 / r }')
    if awk -v a="$at" -v e="$END" 'BEGIN { exit !(a >= e - 0.05) }'; then
      break
    fi
    sleep_until "$at"
    if [ "$k" -eq 0 ]; then speak "$word"; else speak "$CUE"; fi
    n=$((n + 1))
    mark "CUE $n"
    k=$((k + 1))
  done
  START=$END
done
sleep_until "$START"
speak "Stop. Step back."
mark "STOP"

T1=$(now)
sleep_until "$(awk -v t="$T1" -v r="$REST" 'BEGIN { printf "%.3f", t + r }')"
mark "RUN END"
speak "Run complete."
cleanup
trap - INT TERM

python3 tools/score_rate_run.py "$LOG"
