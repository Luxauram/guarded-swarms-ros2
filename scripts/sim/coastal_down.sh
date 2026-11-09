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
# coastal_down.sh - stop the coastal scenario and check that nothing is left.
#
# Stops a scenario started by scripts/sim/coastal_up.sh or by
# 'make demo-coastal', together with any process of a pipeline run that is
# still alive (stop_pipeline_processes, scripts/pipeline/run_guards.sh):
#
#   1. what is left of the last run, if anything;
#   2. the ROS 2 side of the scenario, with SIGINT, so that its nodes shut
#      down cleanly;
#   3. PX4, the DDS agents, Gazebo, and any node still alive, with SIGKILL;
#   4. the shared memory left behind (as kill_all.sh does) and the ROS 2
#      daemon, so that the next scenario starts from an empty graph.
#
# The processes are matched precisely: PX4 and the DDS agents by process name,
# the rest by command line (Gazebo, the scenario launch, the node executables
# install/<pkg>/lib/<pkg>/<node>, the ros_gz bridges). scripts/kill_all.sh
# matches bare node names anywhere in a command line, so it would also kill an
# editor open on a node's source file; between the runs of a campaign the code
# may well be open.
#
# Usage:  ./scripts/sim/coastal_down.sh
#
# Exit codes: 0 nothing is left; 1 some process survived (it is listed).
# ==============================================================================
cd "$(dirname "$0")/../.." || exit 1
source install/setup.bash
source scripts/pipeline/run_guards.sh

# The teardown must complete: a second Ctrl-C is ignored.
trap '' INT

SCENARIO_LAUNCH="ros2 launch guarded_swarms_bringup coastal_pipeline\.launch"
LAUNCH_EXIT_TIMEOUT_S=15   # s for the scenario launch to stop its nodes

# Gazebo, the scenario launch, every Guarded Swarms node and the ros_gz
# bridges, by command line. Package and node names may contain digits
# (px4_safety_bridge_node).
SCENARIO_PROCESSES="gz sim|gz_sim_serv|${SCENARIO_LAUNCH}"
SCENARIO_PROCESSES+="|lib/guarded_swarms_[a-z0-9_]+/[a-z0-9_]+_node( |\$)"
SCENARIO_PROCESSES+="|lib/ros_gz_bridge/parameter_bridge( |\$)"

log() { echo "[coastal_down] $*"; }

# What is still alive of a scenario or of a run. A zombie (<defunct>) has
# already exited and only waits to be reaped: it does not count.
leftovers() {
  { pgrep -ax px4; pgrep -ax MicroXRCEAgent
    pgrep -af -- "$SCENARIO_PROCESSES"
    pgrep -af -- "$PIPELINE_PROCESSES"; } 2>/dev/null | grep -v '<defunct>'
}

log "stopping what is left of the last run, if anything..."
stop_pipeline_processes

log "stopping the ROS 2 side of the scenario..."
pkill -INT -f -- "$SCENARIO_LAUNCH" 2>/dev/null
for _ in $(seq 1 "$LAUNCH_EXIT_TIMEOUT_S"); do
  pgrep -f -- "$SCENARIO_LAUNCH" > /dev/null || break
  sleep 1
done

log "stopping PX4, the DDS agents and Gazebo..."
pkill -9 -x px4 2>/dev/null
pkill -9 -x MicroXRCEAgent 2>/dev/null
pkill -9 -f -- "$SCENARIO_PROCESSES" 2>/dev/null
sleep 1

# Shared memory left by Gazebo and Fast DDS, as kill_all.sh and gz_kill.sh
# clear it.
rm -rf /tmp/.gazebo* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null
ros2 daemon stop > /dev/null 2>&1

left=$(leftovers)
if [ -n "$left" ]; then
  log "still alive:"
  while IFS= read -r line; do log "  $line"; done <<< "$left"
  exit 1
fi
log "done: nothing left."
