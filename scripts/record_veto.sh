#!/usr/bin/env bash
#
# Copyright 2026 Luca D'Aurizio
# Licensed under the Apache License, Version 2.0 (the "License").
#
# record_veto.sh - exercise the analog Safety Board in isolation and record a
# bag for the Group 6 (veto) metrics.
#
# The Virtual Safety Board of the IEEE paper is an ANALOG enforcement layer that
# runs INDEPENDENTLY of the digital coordination system: it clamps or vetoes
# actuator commands from raw sensor readings alone, before they reach the ESCs.
# We measure it exactly as the paper frames it -- on its own, with NO TB-CSPN
# layer and NO Gazebo/PX4 running. That the board vetoes correctly while fully
# isolated from the digital system IS the paper's independence guarantee.
#
# Three processes:
#   1. safety_board_node    - the board under test (subscribes sensors + raw,
#                             publishes actuator_cmd_safe + safety_status)
#   2. mock_sensor_publisher - cycles the six scripted scenarios (nominal,
#                             proximity, attitude, battery, altitude, recovery),
#                             10 s each, exercising every veto type
#   3. a raw-command stream  - a constant actuator_cmd_raw > 0 at 10 Hz, so the
#                             board's veto action (safe -> 0) is observable, not
#                             just its status flag
#
# Usage:  ./scripts/record_veto.sh [tag]
#
set -o pipefail

TAG="${1:-veto}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BAG="bags/${TAG}-${STAMP}"

# One full pass through the six 10 s scenarios is 60 s; record a little longer
# so the closing recovery scenario is captured in full.
DURATION_S="${DURATION_S:-66}"
RAW_THRUST="${RAW_THRUST:-0.7}"   # the "go" command the board must clamp

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
  # the raw-command publisher is a ros2 topic pub child; make sure it goes too
  pkill -f "actuator_cmd_raw" 2>/dev/null
  pkill -f "mock_sensor_publisher" 2>/dev/null
  pkill -f "safety_board_node" 2>/dev/null
  echo "[veto] done."
}
trap cleanup EXIT INT TERM

echo "============================================================"
echo "[veto] bag -> ${BAG}"
echo "[veto] recording the analog Safety Board in ISOLATION"
echo "[veto]   (no TB-CSPN, no Gazebo -- this is the independence claim)"
echo "[veto] duration ${DURATION_S}s, raw thrust ${RAW_THRUST}"
echo "============================================================"

echo "[veto] starting rosbag on ${#TOPICS[@]} topics..."
ros2 bag record -o "${BAG}" "${TOPICS[@]}" >/tmp/gs_veto_bag.log 2>&1 &
PIDS+=($!)
sleep 2

echo "[veto] launching the safety board (rover tuning: altitude disabled)..."
# Rover tuning: an UGV lives at ground level, so the altitude envelope is opened
# up (as in demo-safety-board-rover) to leave proximity/attitude/battery as the
# meaningful vetoes on the ground. The mock still drives altitude=60 in its
# altitude scenario, which with the default 50 m cap would also trip; keeping
# the default cap here lets that scenario fire too, so we KEEP defaults to
# exercise all five. (Override with SAFETY_ARGS if you want rover tuning.)
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
# cleanup() runs on EXIT
echo "[veto] bag saved to ${BAG}"
echo "[veto] inspect with:  ros2 bag info ${BAG}"
