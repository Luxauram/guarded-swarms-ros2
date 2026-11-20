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
# record_veto.sh - exercise the analog Safety Board in isolation and record a
# bag of its verdicts.
#
# The Safety Board decides from the sensor readings alone, independently of the
# coordination layer: it forwards each proposed command, or replaces it with
# 0.0 while a limit is violated. It is measured here on its own, with no
# TB-CSPN layer and no Gazebo or PX4 running, so its verdicts can depend on
# nothing else.
#
# Three processes:
#   1. safety_board_node    - the board under test (subscribes sensors + raw,
#                             publishes actuator_cmd_safe + safety_status)
#   2. mock_sensor_publisher - cycles the six scripted scenarios (nominal,
#                             proximity, attitude, battery, altitude, recovery),
#                             10 s each, exercising every value check
#   3. a raw-command stream  - a constant actuator_cmd_raw > 0 at 10 Hz, so the
#                             board's veto action (safe -> 0) is observable, not
#                             just its status flag
#
# Usage:  ./scripts/record/record_veto.sh [tag]
#         from the root of the repository: the bag goes to bags/<tag>-<time>.
# ==============================================================================
set -o pipefail

TAG="${1:-veto}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BAG="bags/${TAG}-${STAMP}"

# One full pass through the six 10 s scenarios is 60 s; record a little longer
# so the closing recovery scenario is captured in full.
DURATION_S="${DURATION_S:-66}"
RAW_THRUST="${RAW_THRUST:-0.7}"   # the "go" command, forwarded or vetoed

# Topics that tell the whole veto story: the command before and after the
# board, every sensor that can trip it, and the board's own status flag.
TOPICS=(
  /actuator_cmd_raw
  /actuator_cmd_safe
  /drone/proximity
  /drone/imu
  /drone/battery
  /drone/altitude
  /safety_status
)

PIDS=()
cleanup() {
  echo "[veto] tearing down..."
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
  pkill -f "actuator_cmd_raw" 2>/dev/null
  pkill -f "mock_sensor_publisher" 2>/dev/null
  pkill -f "safety_board_node" 2>/dev/null
  echo "[veto] done."
}
trap cleanup EXIT INT TERM

echo "============================================================"
echo "[veto] bag -> ${BAG}"
echo "[veto] recording the analog Safety Board in ISOLATION"
echo "[veto]   (no TB-CSPN, no Gazebo, no PX4)"
echo "[veto] duration ${DURATION_S}s, raw thrust ${RAW_THRUST}"
echo "============================================================"

echo "[veto] starting rosbag on ${#TOPICS[@]} topics..."
ros2 bag record -o "${BAG}" "${TOPICS[@]}" >/tmp/gs_veto_bag.log 2>&1 &
PIDS+=($!)
sleep 2

echo "[veto] launching the safety board..."
# The mock drives altitude=60 in its altitude scenario, which trips the default
# 50 m cap, so the default tuning here exercises all four value checks.
# Override with SAFETY_ARGS for rover tuning (altitude envelope opened, as for
# the rover in coastal_pipeline.launch.py), leaving proximity/attitude/battery
# as the ground vetoes.
ros2 run guarded_swarms_safety safety_board_node ${SAFETY_ARGS:-} \
  >/tmp/gs_veto_board.log 2>&1 &
PIDS+=($!)
sleep 2

echo "[veto] launching the mock sensor publisher (6 scripted scenarios)..."
ros2 run guarded_swarms_safety mock_sensor_publisher \
  >/tmp/gs_veto_mock.log 2>&1 &
PIDS+=($!)
sleep 1

echo "[veto] streaming a constant raw command (${RAW_THRUST}) at 10 Hz..."
ros2 topic pub -r 10 /actuator_cmd_raw std_msgs/msg/Float32 \
  "{data: ${RAW_THRUST}}" >/tmp/gs_veto_raw.log 2>&1 &
PIDS+=($!)

echo "[veto] running for ${DURATION_S}s (watch /tmp/gs_veto_board.log for VETO lines)..."
sleep "${DURATION_S}"

echo "[veto] stopping..."
echo "[veto] bag saved to ${BAG}"
echo "[veto] inspect with:  ros2 bag info ${BAG}"