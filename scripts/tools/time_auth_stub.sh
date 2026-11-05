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
# time_auth_stub.sh - time the steps test_pipeline.sh runs between the first
#                     ConfirmedThreat and the authorisation.
#
# Reproduces those steps with the same commands: three `gz model` pose
# snapshots, then a `ros2 topic pub` with the same rate, count and QoS. A
# stand-in subscriber plays the part of T6: it is already running when the
# publisher starts, and the timing stops when it receives the first message.
# Everything goes on a dummy topic, so nothing is authorised and nothing moves
# in Gazebo: only the commands are timed.
#
# Needs `make demo-coastal` running. The sensing and TB-CSPN layers are not
# running here, so the machine is less loaded than in a real run and the
# figures are a lower bound.
#
# Usage:  ./scripts/tools/time_auth_stub.sh [repetitions]
# ==============================================================================
set -o pipefail
cd "$(dirname "$0")/../.." || exit 1
source install/setup.bash

REPS="${1:-5}"
STEP_TIMEOUT_S=60          # no step may hang the script
SUBSCRIBER_SETTLE_S=3      # let the stand-in subscriber come up (not timed)
TOPIC=/audit_dummy

pose() {
  timeout "$STEP_TIMEOUT_S" gz model -m "$1" -p 2>/dev/null \
    | grep -A1 Pose | tail -1 | tr -d ' []'
}
now() { date +%s.%N; }
elapsed() { awk -v a="$1" -v b="$2" 'BEGIN { printf "%.2f", b - a }'; }

echo "Timing ${REPS} repetitions; each takes about 10-20 s."
echo "Nothing happens in Gazebo: only the commands are timed."
echo

ROWS=()
for i in $(seq 1 "$REPS"); do
  # Stand-in for T6: exits on the first message it receives.
  timeout "$STEP_TIMEOUT_S" ros2 topic echo --once "$TOPIC" \
    std_msgs/msg/Empty >/dev/null 2>&1 &
  sub_pid=$!
  sleep "$SUBSCRIBER_SETTLE_S"

  echo "[rep ${i}] 3 x gz model (pose snapshots)..."
  t0=$(now)
  p0=$(pose x500_lidar_front_0)
  p1=$(pose x500_lidar_front_1)
  p2=$(pose r1_rover_2)
  t1=$(now)
  if [ -z "${p0}${p1}${p2}" ]; then
    echo "[rep ${i}]   warning: gz model returned no pose (is demo-coastal up?)"
  fi

  echo "[rep ${i}] ros2 topic pub, until the stand-in receives the first message..."
  timeout "$STEP_TIMEOUT_S" ros2 topic pub --rate 5 --times 10 \
    --qos-durability transient_local "$TOPIC" std_msgs/msg/Empty "{}" \
    >/dev/null 2>&1 &
  pub_pid=$!
  wait "$sub_pid"; sub_rc=$?
  t2=$(now)
  wait "$pub_pid"
  t3=$(now)

  delivered=$(elapsed "$t1" "$t2")
  [ "$sub_rc" -eq 124 ] && delivered="timeout"
  ROWS+=("$(printf "%3d  %15s  %19s  %9s  %16s" "$i" \
    "$(elapsed "$t0" "$t1")" "$delivered" "$(elapsed "$t0" "$t2")" \
    "$(elapsed "$t1" "$t3")")")
  echo "[rep ${i}] done"
done

echo
echo "rep  gz model x3 [s]  pub -> received [s]  total [s]  pub lifetime [s]"
printf "%s\n" "${ROWS[@]}"