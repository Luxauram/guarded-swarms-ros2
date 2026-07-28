#!/usr/bin/env bash
# =============================================================================
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
# =============================================================================
set -o pipefail

cd "$(dirname "$0")/.." || exit 1
source install/setup.bash

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

# Give the recorder a moment to subscribe before the chain starts producing.
sleep 2

# Drive the actual run through the existing test script. It launches the
# intruder, sensing and TB-CSPN, waits for a ConfirmedThreat, authorises, and
# reports. When it returns (or is interrupted), we stop the bag.
echo "[record] launching the pipeline via test_pipeline.sh..."
echo "============================================================"
./scripts/test_pipeline.sh

# test_pipeline.sh ends with `wait` (it stays up until Ctrl-C). When the user
# interrupts it, the trap above stops the bag cleanly.