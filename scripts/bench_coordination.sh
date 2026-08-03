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
# bench_coordination.sh - Group 5: coordination overhead vs swarm size.
#
# The IET paper states that TB-CSPN has "sub-linear coordination overhead as
# swarm size increases", achieved by "hierarchical token routing and localised
# concurrency windows", but validates this analytically and in the PoC only --
# not on a physical-vehicle digital twin. This measures it on the twin.
#
# WHAT IS AND IS NOT MEASURED HERE
# ================================
# This measures COORDINATION overhead: the volume of coordination traffic the
# TB-CSPN layer emits to task a swarm of N vehicles. It is deliberately
# separate from bench_vehicles.sh, which measures the SIMULATION cost (the RTF
# drop as PX4/Gazebo instances are added in lockstep). The two are different
# axes: one is the architecture's protocol cost, the other is the simulator's
# physics cost. Conflating them would be wrong.
#
# The dispatch transition (T7) is run in ISOLATION, with a fleet of size N set
# purely by parameter (uav_systems / uav_pose_topics / uav_spawns). No Gazebo,
# no PX4: the coordination traffic is generated in the digital layer regardless
# of whether the physical vehicles exist, so the overhead can be measured for
# fleet sizes far beyond what the lockstep simulator could run. A fixed number
# of MissionTokens is injected; the VehicleTasks produced are recorded.
#
# The key structural fact (dispatch_transition_node.cpp, on_mission): each
# mission emits EXACTLY TWO tasks -- one intercept to the nearest UAV, one
# observe to the UGV -- independent of N. nearest_uav scans the fleet (O(N)
# compute) but publishes only to the winner (O(1) traffic). So the coordination
# message overhead per mission is constant in N; that is the sub-linearity.
#
# Usage:
#   ./scripts/bench_coordination.sh            # N = 1 2 4 8 16, 10 missions
#   MISSIONS=20 SIZES="1 2 4 8" ./scripts/bench_coordination.sh
# ==============================================================================
set -o pipefail

# awk formats numbers per the locale. Under it_IT the decimal separator is a
# comma, so "%.1f" of -40 prints "-40,0", which ROS2 then reads as two ints
# (-40 and 0) mixed with the doubles in the list -> "sequence should be of same
# type" and the dispatch never starts. Force the C locale so awk uses a point.
# (Same fix as bench_vehicles.sh.)
export LC_ALL=C

SIZES="${SIZES:-1 2 4 8 16}"
MISSIONS="${MISSIONS:-10}"
OUTDIR="${OUTDIR:-bags/coord}"

# Fleet geometry: vehicles are placed on a line so nearest_uav sees distinct
# distances. Spawn i sits at x = i*SPAWN_STEP_M + SPAWN_X0_M, y = SPAWN_Y_M.
SPAWN_STEP_M=20         # spacing between consecutive UAV spawns along x
SPAWN_X0_M=-40          # x of the first spawn
SPAWN_Y_M=-24.0         # y of every spawn (must carry a decimal point)

# Timing.
DISPATCH_SETTLE_BASE_S=3     # base wait for the dispatch to initialise
DISPATCH_SETTLE_PER_N=0.1    # extra wait per vehicle (one subscription each)
BAG_START_S=2               # let rosbag2 open the bag before the node starts
DRAIN_S=3                   # let the dispatch emit its tasks before closing
BAG_FLUSH_TRIES=20          # polls of 0.5 s each while the bag finalises

mkdir -p "$OUTDIR"

# Build the fleet parameter arrays for a given size N.
# Emits "ids|topics|spawns", each an SDF-style list literal. The pose topics are
# placeholders (never subscribed to when the dispatch runs in isolation). Every
# spawn value carries a decimal point: ROS2 rejects a parameter list that mixes
# int and double ("sequence should be of same type"), and awk prints an integer
# such as -40 without a trailing .0.
build_fleet_args() {
  local n="$1"
  local ids="[" topics="[" spawns="["
  for ((i=0; i<n; i++)); do
    local sysid=$((i+1))
    ids+="$sysid"
    topics+="'/fleet/uav_${i}/pose'"
    local x
    x=$(awk "BEGIN{printf \"%.1f\", $i*$SPAWN_STEP_M + $SPAWN_X0_M}")
    spawns+="${x}, ${SPAWN_Y_M}, 0.0"
    if [ $i -lt $((n-1)) ]; then ids+=", "; topics+=", "; spawns+=", "; fi
  done
  ids+="]"; topics+="]"; spawns+="]"
  echo "$ids|$topics|$spawns"
}

cleanup() {
  pkill -f "dispatch_transition_node" 2>/dev/null
  pkill -f "coord_mission_injector" 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "============================================================"
echo "[coord] Group 5 - coordination overhead vs swarm size"
echo "[coord] fleet sizes: ${SIZES}  |  missions per run: ${MISSIONS}"
echo "[coord] dispatch (T7) in isolation; no Gazebo/PX4"
echo "============================================================"

for N in $SIZES; do
  echo
  echo "[coord] === fleet size N=${N} ==="
  cleanup; sleep 1

  IFS='|' read -r IDS TOPICS SPAWNS <<< "$(build_fleet_args "$N")"
  BAG="${OUTDIR}/coord-N${N}"
  rm -rf "$BAG"

  ros2 bag record -o "$BAG" \
    /mission_tokens /vehicle_tasks \
    >/tmp/coord_bag_N${N}.log 2>&1 &
  BAGPID=$!
  sleep "$BAG_START_S"

  ros2 run guarded_swarms_tbcspn dispatch_transition_node --ros-args \
    -p uav_systems:="${IDS}" \
    -p uav_pose_topics:="${TOPICS}" \
    -p uav_spawns:="${SPAWNS}" \
    -p ugv_system:=$((N+1)) \
    >/tmp/coord_dispatch_N${N}.log 2>&1 &

  # Larger fleets take longer to initialise (one subscription per vehicle). The
  # injector also waits for the subscription, so this base-plus-per-vehicle
  # settle is belt-and-braces.
  sleep "$(awk "BEGIN{printf \"%.1f\", $DISPATCH_SETTLE_BASE_S + $N*$DISPATCH_SETTLE_PER_N}")"

  python3 scripts/coord_mission_injector.py "${MISSIONS}" \
    >/tmp/coord_inject_N${N}.log 2>&1
  sleep "$DRAIN_S"

  # Close the bag CLEANLY: SIGINT (not kill -9) lets rosbag2 flush and write
  # metadata.yaml. Without this the .db3 is left unfinalised and unreadable
  # ("disk I/O error", missing metadata). Wait for the process to actually exit
  # before moving on.
  kill -INT "$BAGPID" 2>/dev/null
  for _ in $(seq 1 "$BAG_FLUSH_TRIES"); do
    kill -0 "$BAGPID" 2>/dev/null || break
    sleep 0.5
  done

  pkill -f "dispatch_transition_node" 2>/dev/null
  pkill -f "coord_mission_injector" 2>/dev/null
  sleep 2

  if [ -f "${BAG}/metadata.yaml" ]; then
    echo "[coord] N=${N}: bag finalised at ${BAG}"
  else
    echo "[coord] N=${N}: WARNING bag not finalised (no metadata.yaml)"
  fi
done

echo
echo "[coord] all runs done. Analyse with:"
echo "  python3 scripts/metrics/metrics_scalability.py ${OUTDIR}"