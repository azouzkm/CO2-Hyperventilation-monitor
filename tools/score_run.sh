#!/bin/bash
# Team 6 - score one scripted run log against the draft CR-1 requirements.
#
#   bash tools/score_run.sh data/raw/run_2026-10-23_141502_lung15.log [ER1_BREATHS] [ER2_SECONDS]
#
# ER-1: "CO2 PRESENT" shown within ER1_BREATHS breaths of the first cue   (default 3)
# ER-2: "CO2 ABSENT"  shown within ER2_SECONDS seconds of the STOP cue    (default 30)
# Reads the marks written by scripted_run.sh (## CUE n, ## STOP) and the board's state banners
# (>>> CO2 PRESENT ..., >>> CO2 ABSENT ..., >>> SENSOR FAULT ...). Times are the Mac clock, 1 s
# resolution. Prints a summary and appends one row to data/runs/results.csv.
# Plain bash + awk (works with the versions that ship with macOS).

LOG="$1"
ER1=${2:-3}
ER2=${3:-30}
if [ ! -f "$LOG" ]; then
  echo "usage: bash tools/score_run.sh <run log> [er1_breaths] [er2_seconds]"
  exit 1
fi
cd "$(dirname "$0")/.." || exit 1
case "$LOG" in /*) ;; *) LOG="$OLDPWD/$LOG" ;; esac

ROW=$(awk -v er1="$ER1" -v er2="$ER2" '
function secs(c,   a) { split(c, a, ":"); return a[1] * 3600 + a[2] * 60 + a[3] }
{ t = secs($1) }
/## RUN START/  { label = $0; sub(/.*label=/, "", label); sub(/ .*/, "", label)
                  rate = $0; sub(/.*rate=/, "", rate); sub(/ .*/, "", rate) }
/## CUE /       { n_cue++; cue[n_cue] = t; if (n_cue == 1) t_first = t }
/## STOP/       { t_stop = t }
/>>> CO2 PRESENT/ { if (t_first != "" && t_present == "" && t >= t_first) t_present = t
                    if (t_first != "" && t >= t_first && t_stop == "") presents++ }
/>>> CO2 ABSENT/  { if (t_present != "" && t_stop == "") dropouts++
                    if (t_stop != "" && t_absent == "") t_absent = t }
/>>> SENSOR FAULT/ { if (t_first != "") fault = 1 }
/  t= *[0-9]+ s  CO2 / { if (t_first != "" && (t_absent == "" || t <= t_absent)) {
                         v = $0; sub(/.*CO2 +/, "", v); sub(/ ppm.*/, "", v); v += 0
                         if (v > peak) peak = v } }
END {
  if (t_first == "") { print "ERROR no cues found in the log"; exit }
  breaths = ""
  if (t_present != "") { breaths = 0; for (i = 1; i <= n_cue; i++) if (cue[i] <= t_present) breaths++ }
  pres_s = (t_present == "") ? "" : t_present - t_first
  abs_s  = (t_absent == "" || t_stop == "") ? "" : t_absent - t_stop
  r1 = (breaths != "" && breaths <= er1) ? "PASS" : "FAIL"
  r2 = (abs_s != "" && abs_s <= er2) ? "PASS" : "FAIL"
  valid = fault ? "invalid (sensor fault during run)" : "valid"
  printf "%s|%s|%d|%s|%s|%s|%s|%s|%s|%d|%d|%s\n", label, rate, n_cue, pres_s, breaths, r1, abs_s, r2, peak, dropouts, presents, valid
}' "$LOG")

case "$ROW" in ERROR*) echo "${ROW#ERROR }"; exit 1 ;; esac
IFS='|' read -r LABEL RATE CUES PRES_S BREATHS R1 ABS_S R2 PEAK DROPS PRES VALID <<EOF
$ROW
EOF

echo
echo "================ run result: ${LABEL:-unlabelled} ================"
echo "  cues given        : $CUES at $RATE per minute"
if [ -n "$PRES_S" ]; then
  echo "  CO2 PRESENT shown : ${PRES_S} s after the first cue, during breath ${BREATHS}   ER-1 (<= $ER1 breaths): $R1"
else
  echo "  CO2 PRESENT shown : never                                   ER-1 (<= $ER1 breaths): $R1"
fi
if [ -n "$ABS_S" ]; then
  echo "  CO2 ABSENT shown  : ${ABS_S} s after the stop cue                  ER-2 (<= $ER2 s): $R2"
else
  echo "  CO2 ABSENT shown  : not within the run                       ER-2 (<= $ER2 s): $R2"
fi
echo "  peak reading      : $PEAK ppm"
echo "  drop-outs         : $DROPS time(s) ABSENT while breathing"
echo "  run               : $VALID"
echo

mkdir -p data/runs
RES=data/runs/results.csv
[ -f "$RES" ] || echo "date,time,label,rate_per_min,cues,present_s,present_breath,er1,absent_s,er2,peak_ppm,dropouts,valid,log" > "$RES"
echo "$(date +%Y-%m-%d),$(date +%H:%M:%S),$LABEL,$RATE,$CUES,$PRES_S,$BREATHS,$R1,$ABS_S,$R2,$PEAK,$DROPS,$VALID,${LOG##*/}" >> "$RES"
echo "Saved to $RES"
