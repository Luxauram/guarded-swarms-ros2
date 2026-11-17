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
#   2. one uXRCE-DDS agent per PX4 instance, each on its own UDP port
#   3. PX4 instances 0 (UAV0), 1 (UAV1) and 2 (UGV), then one more for each
#      UAV past the first two, each configured by scripts/sim/px4_configure.sh
#      as in the demo
#   4. the ROS 2 side of the scenario (coastal_pipeline.launch.py)
#
# Unlike the demo it opens no terminals. Every component is detached from this
# terminal (setsid), so a Ctrl-C meant for a run never reaches the scenario,
# and logs to its own file in SIM_LOG_DIR. PX4 runs in daemon mode (-d),
# without its interactive shell, which would otherwise wait on a terminal and
# stall the lockstep simulation.
#
# The scenario is ready when /clock is published, every UAV hovers at its
# patrol altitude, every PX4 instance is armed and not in failsafe (as
# scripts/world/check_coastal.sh checks them), and every vehicle publishes a
# proximity reading: without it there is no lidar, and the Safety Boards would
# veto every command.
#
# Usage:
#   ./scripts/sim/coastal_up.sh              # Gazebo with its window
#   HEADLESS=1 ./scripts/sim/coastal_up.sh   # Gazebo without its window
#   N_UAVS=8 READY_TIMEOUT_S=600 ./scripts/sim/coastal_up.sh   # eight UAVs
#
# VETO_BY and UAV_FAULT set the launch arguments veto_by (worker | gate) and
# uav_fault (none | obstacle) of coastal_pipeline.launch.py, for the
# fault-injection runs. By default they are those of 'make demo-coastal'
# (worker, none). The faults are those of the first two UAVs, so UAV_FAULT
# needs N_UAVS=2.
#
# N_UAVS is the number of UAVs: 2 by default, as in 'make demo-coastal', up to
# the number in src/guarded_swarms_bringup/config/coastal_fleet.yaml, which
# gives the PX4 instance, spawn pose and hover altitude of every vehicle.
# coastal_pipeline.launch.py reads N_UAVS and the same file, and so does
# tbcspn.launch.py for the dispatch transition: run the chain with the same
# N_UAVS. With more UAVs the simulation runs slower than real time and the
# vehicles take longer to be ready, so READY_TIMEOUT_S, in real seconds, must
# grow with them.
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
# Exported, because coastal_pipeline.launch.py reads it from the environment.
export N_UAVS="${N_UAVS:-2}"
PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
PX4_BUILD="$PX4_DIR/build/px4_sitl_default"

# Scenario, as in make/vars.mk: world and airframes. The vehicles (PX4
# instance, spawn pose in Gazebo ENU, hover altitude of a UAV) come from the
# fleet file, the installed copy that coastal_pipeline.launch.py reads too.
WORLD=coastal
UAV_AIRFRAME=4017                # gz_x500_lidar_front
UGV_AIRFRAME=4009                # gz_r1_rover
GZ_RESOURCE_PATH="$REPO_ROOT/src/guarded_swarms_gz/models:$REPO_ROOT/src/guarded_swarms_gz/worlds"
FLEET_FILE="$(ros2 pkg prefix guarded_swarms_bringup 2>/dev/null)/share/guarded_swarms_bringup/config/coastal_fleet.yaml"

# A UAV within HOVER_TOL_M of its hover altitude counts as hovering.
HOVER_TOL_M=1.0

# Waits. The fixed ones are those of demo-coastal.
GZ_BOOT_TIMEOUT_S="${GZ_BOOT_TIMEOUT_S:-60}"  # s for the world to publish stats
AGENT_SETTLE_S="${AGENT_SETTLE_S:-3}"         # s after starting the DDS agents
UAV_BOOT_WAIT_S="${UAV_BOOT_WAIT_S:-15}"      # s for PX4 instance 0 to boot
NEXT_BOOT_WAIT_S="${NEXT_BOOT_WAIT_S:-12}"    # s for each later instance
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

# True once the world publishes its statistics, that is once Gazebo is up.
# 'gz topic -i' lists the publishers of the topic without subscribing to it.
# 'gz topic -e' would subscribe, and while the server is still starting it can
# crash with a segmentation fault.
world_up() {
  timeout 5 gz topic -i -t "/world/$WORLD/stats" 2>/dev/null | awk '
    /^Publishers/ { pub = 1; next }
    /^Subscribers/ { pub = 0 }
    pub && /WorldStatistics/ { found = 1 }
    END { exit !found }'
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

# The number of UAVs in the fleet file.
fleet_size() {
  python3 -c 'import sys, yaml; print(len(yaml.safe_load(open(sys.argv[1]))["uavs"]))' \
    "$FLEET_FILE" 2>/dev/null
}

# The vehicles of the run: the UGV and the first N_UAVS UAVs of the fleet file,
# one line each, "instance kind x y hover_m" (hover_m 0 for the UGV), in
# instance order, the order in which they start.
read_fleet() {
  python3 - "$FLEET_FILE" "$N_UAVS" <<'EOF'
import sys
import yaml

with open(sys.argv[1]) as f:
    fleet = yaml.safe_load(f)
vehicles = [dict(fleet["ugv"], kind="ugv", hover_m=0)]
vehicles += [dict(u, kind="uav") for u in fleet["uavs"][: int(sys.argv[2])]]
for v in sorted(vehicles, key=lambda v: v["instance"]):
    print(v["instance"], v["kind"], f"{v['x']:g}", f"{v['y']:g}",
          f"{v['hover_m']:g}")
EOF
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
[ -f "$FLEET_FILE" ] || fail "fleet file not found: $FLEET_FILE (built and sourced?)"
max_uavs=$(fleet_size)
[[ "$N_UAVS" =~ ^[0-9]+$ ]] && [ "$N_UAVS" -ge 2 ] && [ "$N_UAVS" -le "${max_uavs:-0}" ] \
  || fail "N_UAVS must be a whole number from 2 to ${max_uavs:-?}, not '$N_UAVS'"
[ "$UAV_FAULT" = none ] || [ "$N_UAVS" -eq 2 ] \
  || fail "UAV_FAULT=$UAV_FAULT needs N_UAVS=2: the faults are those of the first two UAVs"
mapfile -t VEHICLES < <(read_fleet)
[ "${#VEHICLES[@]}" -eq $((N_UAVS + 1)) ] || fail "cannot read the fleet from $FLEET_FILE"
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
for vehicle in "${VEHICLES[@]}"; do
  read -r instance _ <<< "$vehicle"
  [ "$instance" -eq 0 ] || rm -rf "$PX4_BUILD/rootfs/$instance"
done

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
until world_up; do
  [ "$SECONDS" -lt "$deadline" ] || fail "Gazebo did not start within ${GZ_BOOT_TIMEOUT_S}s"
  sleep 1
done

# --- 2. DDS agents ---------------------------------------------------------------
# One agent per instance, on the port px4_configure.sh gives it: 8888 + instance.
ports=()
for vehicle in "${VEHICLES[@]}"; do
  read -r instance _ <<< "$vehicle"
  ports+=($((8888 + instance)))
done
printf -v list '%s, ' "${ports[@]}"
log "[2/4] uXRCE-DDS agents on UDP ${list%, }"
for port in "${ports[@]}"; do
  setsid -f MicroXRCEAgent udp4 -p "$port" \
    > "$SIM_LOG_DIR/dds_agent_$port.log" 2>&1 < /dev/null
done
sleep "$AGENT_SETTLE_S"

# --- 3. PX4 ----------------------------------------------------------------------
log "[3/4] PX4: $N_UAVS UAVs and the UGV (instance 2), instances 0 to $N_UAVS"
wait_s="$UAV_BOOT_WAIT_S"
for vehicle in "${VEHICLES[@]}"; do
  read -r instance kind x y _ <<< "$vehicle"
  if [ "$kind" = ugv ]; then
    start_px4 "$instance" "$UGV_AIRFRAME" gz_r1_rover "$x,$y,0"
  else
    start_px4 "$instance" "$UAV_AIRFRAME" gz_x500_lidar_front "$x,$y,0"
  fi
  sleep "$wait_s"
  configure_px4 "$instance" "$kind"
  wait_s="$NEXT_BOOT_WAIT_S"
done

# --- 4. ROS 2 side ---------------------------------------------------------------
log "[4/4] ROS 2 side of the scenario (coastal_pipeline.launch.py," \
    "N_UAVS=$N_UAVS, veto_by=$VETO_BY, uav_fault=$UAV_FAULT)"
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
  for vehicle in "${VEHICLES[@]}"; do
    read -r instance kind _ _ hover <<< "$vehicle"
    ns=""
    [ "$instance" -eq 0 ] || ns="/px4_$instance"
    if [ "$kind" = uav ]; then
      hovering "x500_lidar_front_$instance" "$hover" \
        || missing+=("x500_lidar_front_$instance hover")
    fi
    armed "$instance" || missing+=("PX4 $instance armed")
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
