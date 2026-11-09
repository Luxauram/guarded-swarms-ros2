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
# record_run.sh - record one coastal pipeline run into a rosbag for offline
#                 metric analysis.
#
# Records the full semantic chain (observations -> interpretations -> mission
# -> tasks), the authorisation, the simulation clock, and the vehicle poses,
# while a normal pipeline run executes. The resulting bag is what the metric
# scripts (metrics_chain.py, ...) read.
#
# This is deliberately SEPARATE from test_pipeline.sh: recording is its own
# concern. It reuses that script to drive the run, so the launch logic lives
# in one place only.
#
# Usage:
#     make demo-coastal                 # terminal 1: the scenario (GUI)
#     ./scripts/record/record_run.sh [name]    # terminal 2: run + record
#
# The bag is written to bags/<name>-<timestamp>/, or to BAG_DIR if set. If no
# name is given, the scenario name "coastal" is used.
#
# The run is not recorded if the scenario is down or an earlier run left
# processes behind (exit 2). A run stopped by a guard (exit 3) keeps its bag
# for inspection, but the bag must not be analysed (see run_guards.sh).
# ==============================================================================
set -o pipefail
cd "$(dirname "$0")/../.." || exit 1
source install/setup.bash
source scripts/pipeline/run_guards.sh

RECORDER_SETTLE_S=2   # let rosbag subscribe before the chain starts producing

# Refuse to record if the run cannot start clean. Checked before the recorder
# starts, so a refused run leaves no partial bag behind.
guard_scenario_running || exit 2
guard_no_leftovers || exit 2

RUN_NAME="${1:-coastal}"
STAMP="$(date +%Y%m%d-%H%M%S)"
# BAG_DIR can be set by the caller, as the campaign script does; by default the
# bag goes to bags/<name>-<timestamp>/. rosbag2 refuses an existing directory.
BAG_DIR="${BAG_DIR:-bags/${RUN_NAME}-${STAMP}}"
mkdir -p "$(dirname "$BAG_DIR")"

# Topics that carry the chain and everything a metric needs a timestamp for.
TOPICS=(
  /obs_tokens
  /interp_tokens
  /mission_tokens
  /vehicle_tasks
  /supervisor_auth
  /intruder/ground_truth
  /intruder/active
  /clock
  /fmu/out/vehicle_local_position_v1
  /px4_1/fmu/out/vehicle_local_position_v1
  /px4_2/fmu/out/vehicle_local_position_v1
  # The safety layer of each vehicle: the Safety Board's status and verdict,
  # and the lidar range it gates on; for the UAVs, the setpoint before and
  # after the safety gate.
  /safety_status
  /px4_1/safety_status
  /px4_2/safety_status
  /actuator_cmd_safe
  /px4_1/actuator_cmd_safe
  /px4_2/actuator_cmd_safe
  /drone/proximity
  /px4_1/drone/proximity
  /px4_2/drone/proximity
  /trajectory_setpoint_proposed
  /px4_1/trajectory_setpoint_proposed
  /fmu/in/trajectory_setpoint
  /px4_1/fmu/in/trajectory_setpoint
)

echo "[record] bag -> ${BAG_DIR}"
echo "[record] starting rosbag on ${#TOPICS[@]} topics..."
# Record with receive (wall-clock) timestamps. We deliberately do NOT pass
# --use-sim-time: ros2 bag record can stall on it if /clock is not yet stable
# at startup, producing an empty bag with a bogus timestamp. Relative chain
# latencies (token-to-token deltas) are correct on receive time, and /clock is
# recorded as a topic anyway if sim time is ever needed downstream.
ros2 bag record -o "${BAG_DIR}" "${TOPICS[@]}" \
  >/tmp/gs_rosbag.log 2>&1 &
BAG_PID=$!

cleanup() {
  # Ignore a second Ctrl-C: the script must wait for rosbag to close the bag.
  trap '' INT TERM
  echo
  echo "[record] stopping rosbag..."
  kill -INT "$BAG_PID" 2>/dev/null
  wait "$BAG_PID" 2>/dev/null
  echo "[record] bag saved to ${BAG_DIR}"
  echo "[record] inspect with:  ros2 bag info ${BAG_DIR}"
}
# The bag is closed once, on exit; Ctrl-C and SIGTERM only trigger the exit.
trap cleanup EXIT
trap 'exit 130' INT TERM

sleep "$RECORDER_SETTLE_S"

# Drive the actual run through the existing test script. It launches the
# intruder, sensing, TB-CSPN and the scripted supervisor, waits for a
# ConfirmedThreat, lets the supervisor decide, and reports. When it returns (or
# is interrupted), the trap stops the bag.
echo "[record] launching the pipeline via test_pipeline.sh..."
echo "============================================================"
# Settle the scenario knobs here, so that the run and the scenario line printed
# below use the same values: a value given in front of the command
# (`RF_LABEL=... ./record_run.sh`) is kept, an unset one takes the default of
# test_pipeline.sh, and an unset SEED is drawn here. Any variable given in
# front of the command also reaches test_pipeline.sh through the environment.
export SEED="${SEED:-$(( (RANDOM << 15 | RANDOM) + 1 ))}"
export DECISION="${DECISION:-authorise}"
export AUTH_DELAY_S="${AUTH_DELAY_S:-0}"
export AUTH_TTL_S="${AUTH_TTL_S:-15}"
export RF_LABEL="${RF_LABEL:-LikelyDroneLink}"
export EO_ENABLED="${EO_ENABLED:-true}"
export EO_DELAY_S="${EO_DELAY_S:-0}"
export ATTACK_VECTOR="${ATTACK_VECTOR:-frontal}"
export RADAR_ENABLED="${RADAR_ENABLED:-true}"
export RF_ENABLED="${RF_ENABLED:-true}"
export ACOUSTIC_ENABLED="${ACOUSTIC_ENABLED:-true}"
export INTRUDER_SPEED INTRUDER_DELAY THREAT_TIMEOUT

echo "[record] scenario: SEED=${SEED}, DECISION=${DECISION}, AUTH_DELAY_S=${AUTH_DELAY_S}, RF_LABEL=${RF_LABEL}, EO_ENABLED=${EO_ENABLED}, EO_DELAY_S=${EO_DELAY_S}, ATTACK_VECTOR=${ATTACK_VECTOR}"
./scripts/pipeline/test_pipeline.sh
rc=$?
# Reached when test_pipeline.sh ends on its own: with STAY_UP=0 after the
# report, or on an error. By default it stays up until Ctrl-C, which ends both
# scripts through their traps and closes the bag.
# Exit code 3 means a guard stopped a run whose data cannot be used: the bag is
# kept for inspection, but it must not be analysed.
if [ "$rc" -eq 3 ]; then
  echo "[record] WARNING: a guard stopped the run; do not analyse ${BAG_DIR}"
fi
exit "$rc"
