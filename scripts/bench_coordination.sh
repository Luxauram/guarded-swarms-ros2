#!/usr/bin/env bash
#
# Copyright 2026 Luca D'Aurizio
# Licensed under the Apache License, Version 2.0 (the "License").
#
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
#
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
mkdir -p "$OUTDIR"

# Build the fleet parameter arrays for a given size N.
# system IDs 1..N ; pose topics (placeholder, never subscribed to in isolation);
# spawns on a line so nearest_uav has distinct distances.
build_fleet_args() {
  local n="$1"
  local ids="[" topics="[" spawns="["
  for ((i=0; i<n; i++)); do
    local sysid=$((i+1))
    ids+="$sysid"
    topics+="'/fleet/uav_${i}/pose'"
    # spawn on a line: x = i*20 - 40, y = -24, z = 0. Force a decimal point
    # on every value: ROS2 rejects a parameter list that mixes int and double
    # ("sequence should be of same type"), and awk prints -40 (no .0) for x.
    local x=$(awk "BEGIN{printf \"%.1f\", $i*20 - 40}")
    spawns+="${x}, -24.0, 0.0"
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

  # record the coordination topics
  ros2 bag record -o "$BAG" \
    /mission_tokens /vehicle_tasks \
    >/tmp/coord_bag_N${N}.log 2>&1 &
  BAGPID=$!
  sleep 2

  # launch the dispatch node with a fleet of size N
  ros2 run guarded_swarms_tbcspn dispatch_transition_node --ros-args \
    -p uav_systems:="${IDS}" \
    -p uav_pose_topics:="${TOPICS}" \
    -p uav_spawns:="${SPAWNS}" \
    -p ugv_system:=$((N+1)) \
    >/tmp/coord_dispatch_N${N}.log 2>&1 &
  # Larger fleets take longer to initialise (one subscription per vehicle); give
  # the node a base 3 s plus a little per vehicle before the injector runs. The
  # injector also waits for the subscription, so this is belt-and-braces.
  sleep $(awk "BEGIN{printf \"%.1f\", 3 + $N*0.1}")

  # inject MISSIONS mission tokens, each with a distinct target position so
  # nearest_uav has something to discriminate. Published on /mission_tokens.
  python3 scripts/coord_mission_injector.py "${MISSIONS}" \
    >/tmp/coord_inject_N${N}.log 2>&1

  sleep 3   # let the dispatch drain the tasks

  # Close the bag CLEANLY: SIGINT (not kill -9) lets rosbag2 flush and write
  # metadata.yaml. Without this the .db3 is left unfinalised and unreadable
  # ("disk I/O error", missing metadata). Wait for the process to actually
  # exit before moving on.
  kill -INT "$BAGPID" 2>/dev/null
  for _ in $(seq 1 20); do
    kill -0 "$BAGPID" 2>/dev/null || break
    sleep 0.5
  done

  # now stop the dispatch and injector for this N
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