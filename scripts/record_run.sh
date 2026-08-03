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
#     ./scripts/record_run.sh [name]    # terminal 2: run + record
#
# The bag is written to bags/<name>-<timestamp>/. If no name is given, the
# scenario name "coastal" is used.
# ==============================================================================
set -o pipefail
cd "$(dirname "$0")/.." || exit 1
source install/setup.bash

RECORDER_SETTLE_S=2   # let rosbag subscribe before the chain starts producing

RUN_NAME="${1:-coastal}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BAG_DIR="bags/${RUN_NAME}-${STAMP}"
mkdir -p bags

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
  echo
  echo "[record] stopping rosbag..."
  kill -INT "$BAG_PID" 2>/dev/null
  wait "$BAG_PID" 2>/dev/null
  echo "[record] bag saved to ${BAG_DIR}"
  echo "[record] inspect with:  ros2 bag info ${BAG_DIR}"
}
trap cleanup EXIT INT TERM

sleep "$RECORDER_SETTLE_S"

# Drive the actual run through the existing test script. It launches the
# intruder, sensing and TB-CSPN, waits for a ConfirmedThreat, authorises, and
# reports. When it returns (or is interrupted), the trap stops the bag.
echo "[record] launching the pipeline via test_pipeline.sh..."
echo "============================================================"
# Propagate the scenario knobs to the child process. A variable set as
# `RF_LABEL=... ./record_run.sh` is NOT exported, so test_pipeline.sh (a
# separate process) would otherwise fall back to its own defaults. Export the
# ones a counterfactual run needs to override; any left unset are exported
# empty and test_pipeline.sh applies its own default via ${VAR:-default}.
export DECISION="${DECISION:-authorise}"
export RF_LABEL="${RF_LABEL:-LikelyDroneLink}"
export EO_ENABLED="${EO_ENABLED:-true}"
export EO_DELAY_S="${EO_DELAY_S:-0}"
export ATTACK_VECTOR="${ATTACK_VECTOR:-frontal}"
export RADAR_ENABLED="${RADAR_ENABLED:-true}"
export RF_ENABLED="${RF_ENABLED:-true}"
export ACOUSTIC_ENABLED="${ACOUSTIC_ENABLED:-true}"
export INTRUDER_SPEED INTRUDER_DELAY THREAT_TIMEOUT AUTH_TARGET SUPERVISOR

echo "[record] scenario: DECISION=${DECISION}, RF_LABEL=${RF_LABEL}, EO_ENABLED=${EO_ENABLED}, EO_DELAY_S=${EO_DELAY_S}, ATTACK_VECTOR=${ATTACK_VECTOR}"
./scripts/test_pipeline.sh
# test_pipeline.sh ends with `wait` (it stays up until Ctrl-C). When the user
# interrupts it, the trap above stops the bag cleanly.