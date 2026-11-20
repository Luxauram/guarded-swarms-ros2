#!/usr/bin/env bash
# ==============================================================================
# Copyright 2026 Luca D'Aurizio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

# ==============================================================================
# run_clock_bench.sh - a campaign of Safety Board runs under clock denial.
#
# The board is run in isolation (no Gazebo, no PX4,
# no coordination layer): scripts/pipeline/publish_sensors.py feeds it healthy,
# safe readings and a constant "go" command, scripts/pipeline/publish_clock.py
# is the source of its simulated clock, and the run is recorded. The board's
# value limits are set permissive here, so the only thing that can make it veto
# is its judgement of sensor freshness, which reads the clock.
#
# Two arms, with the same healthy sensors throughout; only the clock differs:
#   clock-ok    the clock advances normally -> the board trusts the fresh
#               sensors and clears the command: the vehicle operates.
#   clock-dos   the board's clock is denied (held at zero, the use_sim_time
#               stall) -> the board cannot vouch for freshness and fails safe,
#               vetoing every command although the sensors are healthy: the
#               vehicle is blocked. This is the denial-of-service effect.
#
# Runs alternate between the arms, RUNS each. Every run records every topic to
# its own bag; the manifest names the commit. Read the bags with
# scripts/metrics/analyze_clock.py.
#
# Usage:
#   ./scripts/experiments/run_clock_bench.sh <campaign>
#   RUNS=10 ./scripts/experiments/run_clock_bench.sh clock
#
# Variables: RUNS (default 10), DURATION (default 40), STALENESS_S (5, the
# board's window). Exit codes: 0 done, 1 cannot start, 130 Ctrl-C.
# ==============================================================================
set -o pipefail
cd "$(dirname "$0")/../.." || exit 1
source install/setup.bash

RUNS="${RUNS:-10}"
DURATION="${DURATION:-40}"
STALENESS_S="${STALENESS_S:-5}"
BENCH_DIR="bags/clock-bench"

ARMS=(clock-ok clock-dos)

log() { echo "[clock-bench] $*"; }
die() { log "$*"; exit 1; }

[ $# -ge 1 ] || die "usage: $0 <campaign>   (e.g. clock)"
CAMPAIGN="$1"
[[ "$CAMPAIGN" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "bad campaign name."
[[ "$RUNS" =~ ^[1-9][0-9]*$ ]] || die "RUNS must be a positive integer."

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  git status --short --untracked-files=no | sed 's/^/[clock-bench]   /'
  die "commit the changes first: the manifest must name the code of the runs."
fi
COMMIT=$(git rev-parse --short=12 HEAD)
HOST=$(hostname)

OUT="$BENCH_DIR/$CAMPAIGN"
mkdir -p "$OUT"
MANIFEST="$OUT/manifest.csv"
[ -f "$MANIFEST" ] || echo "campaign,arm,run,commit,host,started_utc,duration_s,folder" > "$MANIFEST"
{ echo "COMMIT=$COMMIT"; echo "DURATION=$DURATION"; echo "STALENESS_S=$STALENESS_S"; } > "$OUT/campaign.env"

# The board's value limits, permissive, so the only thing that can make it veto
# is sensor staleness, the check that reads the clock.
BOARD_PARAMS=(
  -p use_sim_time:=true
  -p "sensor_staleness_s:=${STALENESS_S}.0"
  -p min_proximity_m:=0.1 -p proximity_release_m:=0.2
  -p max_pitch_deg:=89.0 -p max_roll_deg:=89.0
  -p min_battery_percent:=0.0
  -p min_altitude_m:=-1000000.0 -p max_altitude_m:=1000000.0
)

PIDS=()
REC_PID=""
cleanup_run() {
  # Finalise the bag first (SIGINT lets rosbag2 close it cleanly), then the rest.
  [ -n "$REC_PID" ] && kill -INT "$REC_PID" 2>/dev/null
  sleep 2
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null; done
  sleep 1
  for pid in "${PIDS[@]}"; do kill -9 "$pid" 2>/dev/null; done
  wait 2>/dev/null
  PIDS=(); REC_PID=""
}
INTERRUPTED=0
on_int() { INTERRUPTED=1; }
trap on_int INT TERM
trap 'cleanup_run' EXIT

arm_args() {   # sets CLOCK_ARGS for the arm; the sensors are healthy in both
  case "$1" in
    clock-ok)  CLOCK_ARGS=() ;;
    clock-dos) CLOCK_ARGS=(--freeze-at 0) ;;
  esac
}

one_run() {
  local arm="$1" run="$2" folder bag started
  folder="$OUT/$arm/$(printf 'run-%02d' "$run")"
  if [ -d "$folder" ]; then log "$arm run $run already done, skipping."; return; fi
  mkdir -p "$folder"
  bag="$folder/bag"
  started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  arm_args "$arm"

  log "$arm, run $run/$RUNS: recording ${DURATION}s..."
  ros2 bag record -a -o "$bag" >"$folder/rosbag.log" 2>&1 &
  REC_PID=$!
  sleep 1
  python3 scripts/pipeline/publish_clock.py "${CLOCK_ARGS[@]}" \
    >"$folder/clock.log" 2>&1 &
  PIDS+=($!)
  sleep 1
  ros2 run guarded_swarms_safety safety_board_node --ros-args \
    "${BOARD_PARAMS[@]}" >"$folder/board.log" 2>&1 &
  PIDS+=($!)
  python3 scripts/pipeline/publish_sensors.py >"$folder/sensors.log" 2>&1 &
  PIDS+=($!)

  SECONDS=0
  while [ "$SECONDS" -lt "$DURATION" ]; do
    [ "$INTERRUPTED" = 1 ] && break
    sleep 1
  done
  cleanup_run
  if [ "$INTERRUPTED" = 1 ]; then
    rm -rf "$folder"
    log "$arm, run $run/$RUNS: interrupted; it will be redone next time."
    return
  fi
  printf '%s,%s,%s,%s,%s,%s,%s,%s\n' "$CAMPAIGN" "$arm" "$run" "$COMMIT" \
    "$HOST" "$started" "$DURATION" "$folder" >> "$MANIFEST"
  log "$arm, run $run/$RUNS: done -> $folder"
}

log "campaign '$CAMPAIGN': ${#ARMS[@]} arms x $RUNS runs, commit $COMMIT"
for run in $(seq 1 "$RUNS"); do
  for arm in "${ARMS[@]}"; do
    [ "$INTERRUPTED" = 1 ] && break 2
    one_run "$arm" "$run"
  done
done

if [ "$INTERRUPTED" = 1 ]; then
  log "stopped with Ctrl-C. Run the same command to continue."
  exit 130
fi
log "done. Analyse with: python3 scripts/metrics/analyze_clock.py $OUT"
exit 0
