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
# run_guards.sh - checks shared by the scripts that drive a pipeline run.
#
# Sourced, not executed: test_pipeline.sh and record_run.sh source it from the
# repository root, after install/setup.bash. It defines:
#
#   guard_scenario_running      the coastal scenario is up (/clock is published)
#   guard_no_leftovers          no process of an earlier run is still alive
#   guard_single_ground_truth   the intruder's ground truth has one source only
#   guard_ground_truth_flowing  the intruder's ground truth is arriving
#   stop_pipeline_processes     stops every process of a run, and checks it
#
# The guards print what is wrong and return 1; the caller decides how to stop.
#
# Why they exist: two runs of an earlier campaign recorded the ground truth of
# two intruders at once, because an intruder from an earlier run was still
# alive. Nothing checked for it, and the mixed trajectories went into the data.
# In a later campaign the nodes of one run received no /clock: the run recorded
# nothing of the chain, and it was counted as a run without a threat.
# ==============================================================================

CLOCK_TIMEOUT_S=10      # s to wait for /clock before declaring the scenario down
GT_CHECK_TIMEOUT_S=15   # s to wait for the intruder's ground-truth publisher
GT_SETTLE_S=2           # s to let every ground-truth publisher be discovered
GT_FLOW_TIMEOUT_S=15    # s to wait for a ground-truth message
TEARDOWN_TIMEOUT_S=5    # s to wait for the processes of a run to exit

# The processes a run starts, matched on their full command line: the node
# executables (install/<pkg>/lib/<pkg>/<node>) and the launch files. Matching
# the executable path rather than the bare node name keeps, for example, an
# editor with radar_agent_node.cpp open from being taken for a running node.
# The scenario's own nodes (vehicle workers, safety boards, bridges) belong to
# demo-coastal and are deliberately not in this list.
PIPELINE_NODES="radar_agent_node|rf_agent_node|acoustic_agent_node"
PIPELINE_NODES+="|eo_agent_node|interpretation_node|candidate_transition_node"
PIPELINE_NODES+="|mission_transition_node|dispatch_transition_node"
PIPELINE_NODES+="|scripted_supervisor_node|intruder_node"
PIPELINE_PROCESSES="lib/guarded_swarms_[a-z]+/(${PIPELINE_NODES})( |\$)"
PIPELINE_PROCESSES+="|ros2 launch guarded_swarms_[a-z]+"
PIPELINE_PROCESSES+=" (sensing|tbcspn|supervisor|intruder)\.launch"

# Prints each line of $1 with the [guard] prefix.
_guard_list() {
  local line
  while IFS= read -r line; do
    echo "[guard]   ${line}"
  done <<< "$1"
}

# The scenario must be running: without /clock every use_sim_time node stays
# frozen, and a run would only time out waiting for a threat.
guard_scenario_running() {
  if ! timeout "$CLOCK_TIMEOUT_S" ros2 topic echo --once /clock \
       >/dev/null 2>&1; then
    echo "[guard] no /clock within ${CLOCK_TIMEOUT_S}s: start the scenario" \
         "first (make demo-coastal)."
    return 1
  fi
}

# A run must start from a clean slate: a process left over from an earlier run
# (a second intruder, a duplicated sensing chain) silently corrupts the data.
guard_no_leftovers() {
  local leftovers
  leftovers=$(pgrep -fa -- "$PIPELINE_PROCESSES")
  if [ -n "$leftovers" ]; then
    echo "[guard] processes of an earlier run are still alive:"
    _guard_list "$leftovers"
    echo "[guard] stop them (Ctrl-C the run that started them, or" \
         "pkill -f <name>) and retry."
    return 1
  fi
}

# Exactly one source of intruder ground truth. Waits for the first publisher,
# lets discovery settle, then counts again.
guard_single_ground_truth() {
  local count=0
  for _ in $(seq 1 "$GT_CHECK_TIMEOUT_S"); do
    count=$(ros2 topic info /intruder/ground_truth 2>/dev/null \
              | awk '/Publisher count:/ { print $3 }')
    [ "${count:-0}" -ge 1 ] && break
    sleep 1
  done
  if [ "${count:-0}" -ge 1 ]; then
    sleep "$GT_SETTLE_S"
    count=$(ros2 topic info /intruder/ground_truth 2>/dev/null \
              | awk '/Publisher count:/ { print $3 }')
  fi
  if [ "${count:-0}" -ne 1 ]; then
    echo "[guard] /intruder/ground_truth has ${count:-0} publisher(s)," \
         "expected exactly 1."
    return 1
  fi
}

# The intruder's ground truth must arrive. The intruder publishes it on every
# tick of a timer on simulated time, also before its ingress starts, so a
# message shows that /clock reaches the nodes of the run, not only the
# scenario check. Without /clock the whole chain stays frozen, and the run
# would end as a run without a threat. The message type is given so that the
# guard always waits for a message: without it, ros2 topic echo stops at once
# when the topic is not yet in the ROS graph.
guard_ground_truth_flowing() {
  if ! timeout "$GT_FLOW_TIMEOUT_S" ros2 topic echo --once \
       /intruder/ground_truth geometry_msgs/msg/PoseStamped \
       >/dev/null 2>&1; then
    echo "[guard] no message on /intruder/ground_truth within" \
         "${GT_FLOW_TIMEOUT_S}s: the simulated time does not reach the run," \
         "or the intruder has stopped."
    return 1
  fi
}

# Stops every process of a run: SIGTERM first, SIGKILL for whatever is still
# alive after TEARDOWN_TIMEOUT_S, with a warning that names it.
stop_pipeline_processes() {
  pkill -f -- "$PIPELINE_PROCESSES" 2>/dev/null
  for _ in $(seq 1 "$TEARDOWN_TIMEOUT_S"); do
    pgrep -f -- "$PIPELINE_PROCESSES" >/dev/null || return 0
    sleep 1
  done
  echo "[guard] still alive after SIGTERM, killing:"
  _guard_list "$(pgrep -fa -- "$PIPELINE_PROCESSES")"
  pkill -9 -f -- "$PIPELINE_PROCESSES" 2>/dev/null
}
