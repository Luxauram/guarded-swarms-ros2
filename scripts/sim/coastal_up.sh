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
# coastal_up.sh - start the coastal scenario unattended and wait until it is
# ready for a run.
#
# Same sequence and settings as 'make demo-coastal' (make/px4.mk), for scripts
# that run without a person at the keyboard, such as
# scripts/experiments/run_campaign.sh:
#
#   1. Gazebo with the coastal world, with its window or headless
#   2. three uXRCE-DDS agents, one UDP port per PX4 instance
#   3. PX4 instances 0 (UAV0), 1 (UAV1) and 2 (UGV), each configured by
#      scripts/sim/px4_configure.sh as in the demo
#   4. the ROS 2 side of the scenario (coastal_pipeline.launch.py)
#
# Unlike the demo it opens no terminals. Every component is detached from this
# terminal (setsid), so a Ctrl-C meant for a run never reaches the scenario,
# and logs to its own file in SIM_LOG_DIR. PX4 runs in daemon mode (-d),
# without its interactive shell, which would otherwise wait on a terminal and
# stall the lockstep simulation.
#
# The scenario is ready when /clock is published, both UAVs hover at their
# patrol altitude, the three PX4 instances are armed and not in failsafe (as
# scripts/world/check_coastal.sh checks them), and the three vehicles publish a
# proximity reading: without it there is no lidar, and the Safety Boards would
# veto every command.
#
# Usage:
#   ./scripts/sim/coastal_up.sh              # Gazebo with its window
#   HEADLESS=1 ./scripts/sim/coastal_up.sh   # Gazebo without its window
#
# VETO_BY and UAV_FAULT set the launch arguments veto_by (worker | gate) and
# uav_fault (none | obstacle) of coastal_pipeline.launch.py, for the
# fault-injection runs. By default they are those of 'make demo-coastal'
# (worker, none).
#
# Exit codes: 0 ready; 1 a scenario is already running, a component did not
# start, or the scenario was not ready within READY_TIMEOUT_S; 130 stopped
# with Ctrl-C. Whatever was started keeps running: stop it with
# scripts/sim/coastal_down.sh.
# ==============================================================================
set -o pipefail
cd "$(dirname "$0")/../.." || exit 1
REPO_ROOT="$(pwd)"
source install/setup.bash

HEADLESS="${HEADLESS:-0}"
SIM_LOG_DIR="${SIM_LOG_DIR:-/tmp/gs_sim}"
VETO_BY="${VETO_BY:-worker}"
UAV_FAULT="${UAV_FAULT:-none}"
PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
PX4_BUILD="$PX4_DIR/build/px4_sitl_default"

# Scenario, as in make/vars.mk: world, spawn poses (Gazebo ENU) and airframes.
WORLD=coastal
UAV0_POSE="-24,-24,0"
UAV1_POSE="24,-24,0"
UGV_POSE="-60,-14,0"
UAV_AIRFRAME=4017                # gz_x500_lidar_front
UGV_AIRFRAME=4009                # gz_r1_rover
GZ_RESOURCE_PATH="$REPO_ROOT/src/guarded_swarms_gz/models:$REPO_ROOT/src/guarded_swarms_gz/worlds"

# Hover altitudes of coastal_pipeline.launch.py (UAV0_HOVER_M, UAV1_HOVER_M).
# A UAV within HOVER_TOL_M of its altitude counts as hovering.
UAV0_HOVER_M=12.0
UAV1_HOVER_M=20.0
HOVER_TOL_M=1.0

# Waits. The fixed ones are those of demo-coastal.
GZ_BOOT_TIMEOUT_S="${GZ_BOOT_TIMEOUT_S:-60}"  # s for the world to publish stats
AGENT_SETTLE_S="${AGENT_SETTLE_S:-3}"         # s after starting the DDS agents
UAV_BOOT_WAIT_S="${UAV_BOOT_WAIT_S:-15}"      # s for PX4 instance 0 to boot
NEXT_BOOT_WAIT_S="${NEXT_BOOT_WAIT_S:-12}"    # s for instances 1 and 2
READY_TIMEOUT_S="${READY_TIMEOUT_S:-120}"     # s for the vehicles to be ready
READY_POLL_S="${READY_POLL_S:-5}"             # s between two readiness checks
ECHO_TIMEOUT_S=5                              # s for a single ros2 topic echo

log() { echo "[coastal_up] $*"; }
fail() {
  log "FAILED: $*"
  log "logs in ${SIM_LOG_DIR}/; stop what was started with ./scripts/sim/coastal_down.sh"
  exit 1
}

# Ctrl-C stops the start-up. Without this trap it could be lost: a 'timeout'
# runs in its own process group, does not see the Ctrl-C, and bash then
# carries on. With it, the start-up stops as soon as the command in progress
# ends, within a few seconds.
interrupted() {
  log "interrupted: stop what was started with ./scripts/sim/coastal_down.sh"
  exit 130
}
trap interrupted INT TERM

# The processes of a running scenario: PX4 and the DDS agents by process name,
# Gazebo and the scenario launch by command line (so that an editor open on the
# launch file does not count). A zombie (<defunct>) has already exited and only
# waits to be reaped: it does not count either.
scenario_processes() {
  { pgrep -ax px4; pgrep -ax MicroXRCEAgent
    pgrep -af -- "gz sim|gz_sim_serv|ros2 launch guarded_swarms_bringup coastal_pipeline\.launch"
  } 2>/dev/null | grep -v '<defunct>'
}

# Ground-truth z of a Gazebo model, or empty if not found.
model_z() {
  gz model -m "$1" -p 2>/dev/null | grep -A1 Pose | tail -1 | tr -d '[]' \
    | awk '{ if (NF >= 3) print $3 }'
}

# True if a UAV hovers within HOVER_TOL_M of its altitude.
hovering() {
  local z
  z=$(model_z "$1")
  [ -n "$z" ] && LC_ALL=C awk -v z="$z" -v h="$2" -v t="$HOVER_TOL_M" \
    'BEGIN { exit !(z > h - t && z < h + t) }'
}

# True if a topic delivers a message within ECHO_TIMEOUT_S.
publishing() {
  timeout "$ECHO_TIMEOUT_S" ros2 topic echo --once "$1" >/dev/null 2>&1
}

# True if a PX4 instance is armed and not in failsafe, read from its commander
# as scripts/world/check_coastal.sh does.
armed() {
  local state
  state=$(cd "$PX4_BUILD" && \
    timeout "$ECHO_TIMEOUT_S" ./bin/px4-commander --instance "$1" status 2>/dev/null)
  grep -q "Armed" <<< "$state" && grep -q "in failsafe: no" <<< "$state"
}

# Starts one PX4 instance in daemon mode, detached, as demo-coastal does.
start_px4() {
  local instance="$1" airframe="$2" model="$3" pose="$4"
  ( cd "$PX4_BUILD" && \
    PX4_GZ_STANDALONE=1 PX4_GZ_NO_FOLLOW=1 \
    PX4_SYS_AUTOSTART="$airframe" PX4_SIM_MODEL="$model" \
    PX4_GZ_WORLD="$WORLD" PX4_GZ_MODEL_POSE="$pose" \
    GZ_SIM_RESOURCE_PATH="$GZ_RESOURCE_PATH" \
    setsid -f ./bin/px4 -i "$instance" -d \
      > "$SIM_LOG_DIR/px4_$instance.log" 2>&1 < /dev/null )
}

# Configures a running PX4 instance (parameters, DDS port), as in the demo.
configure_px4() {
  bash scripts/sim/px4_configure.sh "$1" "$2" \
    >> "$SIM_LOG_DIR/px4_configure.log" 2>&1 \
    || fail "px4_configure.sh $1 $2 (see px4_configure.log)"
}

# --- checks --------------------------------------------------------------------
[ -x "$PX4_BUILD/bin/px4" ] || fail "PX4 not built: $PX4_BUILD/bin/px4 is missing"
case "$VETO_BY" in
  worker|gate) ;;
  *) fail "VETO_BY must be 'worker' or 'gate', not '$VETO_BY'" ;;
esac
case "$UAV_FAULT" in
  none|obstacle) ;;
  *) fail "UAV_FAULT must be 'none' or 'obstacle', not '$UAV_FAULT'" ;;
esac
running=$(scenario_processes)
if [ -n "$running" ]; then
  log "a scenario is already running:"
  while IFS= read -r line; do log "  $line"; done <<< "$running"
  log "stop it first: ./scripts/sim/coastal_down.sh"
  exit 1
fi

rm -rf "$SIM_LOG_DIR"
mkdir -p "$SIM_LOG_DIR"
# A fresh start for every instance, as in demo-coastal: no stale parameters.
bash scripts/sim/gz_kill.sh > "$SIM_LOG_DIR/gz_kill.log" 2>&1
rm -rf "$PX4_BUILD/rootfs/1" "$PX4_BUILD/rootfs/2"

START=$SECONDS

# --- 1. Gazebo -----------------------------------------------------------------
if [ "$HEADLESS" = "1" ]; then
  log "[1/4] Gazebo, world '$WORLD', headless"
  setsid -f bash scripts/sim/gz_launch.sh "$WORLD" --headless \
    > "$SIM_LOG_DIR/gazebo.log" 2>&1 < /dev/null
else
  log "[1/4] Gazebo, world '$WORLD', with its window"
  setsid -f bash scripts/sim/gz_launch.sh "$WORLD" \
    > "$SIM_LOG_DIR/gazebo.log" 2>&1 < /dev/null
fi
deadline=$((SECONDS + GZ_BOOT_TIMEOUT_S))
until timeout 2 gz topic -e -t "/world/$WORLD/stats" -n 1 >/dev/null 2>&1; do
  [ "$SECONDS" -lt "$deadline" ] || fail "Gazebo did not start within ${GZ_BOOT_TIMEOUT_S}s"
  sleep 1
done

# --- 2. DDS agents ---------------------------------------------------------------
log "[2/4] uXRCE-DDS agents on UDP 8888, 8889, 8890"
for port in 8888 8889 8890; do
  setsid -f MicroXRCEAgent udp4 -p "$port" \
    > "$SIM_LOG_DIR/dds_agent_$port.log" 2>&1 < /dev/null
done
sleep "$AGENT_SETTLE_S"

# --- 3. PX4 ----------------------------------------------------------------------
log "[3/4] PX4: UAV0 (instance 0), UAV1 (instance 1), UGV (instance 2)"
start_px4 0 "$UAV_AIRFRAME" gz_x500_lidar_front "$UAV0_POSE"
sleep "$UAV_BOOT_WAIT_S"
configure_px4 0 uav
start_px4 1 "$UAV_AIRFRAME" gz_x500_lidar_front "$UAV1_POSE"
sleep "$NEXT_BOOT_WAIT_S"
configure_px4 1 uav
start_px4 2 "$UGV_AIRFRAME" gz_r1_rover "$UGV_POSE"
sleep "$NEXT_BOOT_WAIT_S"
configure_px4 2 ugv

# --- 4. ROS 2 side ---------------------------------------------------------------
log "[4/4] ROS 2 side of the scenario (coastal_pipeline.launch.py," \
    "veto_by=$VETO_BY, uav_fault=$UAV_FAULT)"
# A fresh ROS 2 daemon, as in demo-coastal: no stale entries in the graph.
ros2 daemon stop > /dev/null 2>&1
ros2 daemon start > /dev/null 2>&1
setsid -f ros2 launch guarded_swarms_bringup coastal_pipeline.launch.py \
  veto_by:="$VETO_BY" uav_fault:="$UAV_FAULT" \
  > "$SIM_LOG_DIR/coastal_pipeline.log" 2>&1 < /dev/null

# --- wait until ready ------------------------------------------------------------
log "waiting for the vehicles (up to ${READY_TIMEOUT_S}s)..."
deadline=$((SECONDS + READY_TIMEOUT_S))
while :; do
  missing=()
  publishing /clock || missing+=("/clock")
  hovering x500_lidar_front_0 "$UAV0_HOVER_M" || missing+=("UAV0 hover")
  hovering x500_lidar_front_1 "$UAV1_HOVER_M" || missing+=("UAV1 hover")
  for instance in 0 1 2; do
    armed "$instance" || missing+=("PX4 $instance armed")
  done
  for ns in "" /px4_1 /px4_2; do
    publishing "$ns/drone/proximity" || missing+=("$ns/drone/proximity")
  done
  if [ "${#missing[@]}" -eq 0 ]; then
    log "ready in $((SECONDS - START))s"
    exit 0
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    printf -v list '%s, ' "${missing[@]}"
    fail "not ready within ${READY_TIMEOUT_S}s; missing: ${list%, }"
  fi
  sleep "$READY_POLL_S"
done
