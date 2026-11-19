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
# @file kill_all.sh
# Guarded Swarms - kill all simulation and ROS 2 processes.
#
# Terminates the whole stack cleanly: the PX4 SITL build/run processes, Gazebo,
# the uXRCE-DDS agent, every Guarded Swarms ROS 2 node, and the shared memory
# and temporary files left behind.
#
# Kept as a script (not inline in the Makefile) on purpose: an inline
# 'pkill make' inside a recipe would also kill the make process running it.
#
# Every kill uses '|| true': pkill returns non-zero when it matches no
# process, which is normal here and must not abort the shutdown. For the same
# reason this script does NOT use 'set -e'.
#
# Node names are matched with 'pkill -f' against the full command line, since
# ROS 2 executable names exceed pkill's ~15-character process-name limit.
#
# Usage:
#   ./scripts/kill_all.sh
#   make kill-all
#
# @author Luca D'Aurizio
# ==============================================================================

echo "Shutting down all processes..."

# PX4 build/run wrappers first, so they do not respawn the simulator.
pkill -9 -f "make.*px4_sitl" 2>/dev/null || true
pkill -9 -f "cmake.*px4_sitl" 2>/dev/null || true
sleep 1

# Simulator, Gazebo, and the PX4<->ROS 2 transport.
pkill -9 -x px4 2>/dev/null || true
pkill -9 -f "gz sim" 2>/dev/null || true
pkill -9 -f "px4-gz_bri" 2>/dev/null || true
pkill -9 -f "gz_sim_serv" 2>/dev/null || true
pkill -9 gzserver 2>/dev/null || true
pkill -9 gzclient 2>/dev/null || true
pkill -9 MicroXRCEAgent 2>/dev/null || true

# Analog safety layer.
pkill -9 -f "safety_board_node" 2>/dev/null || true
pkill -9 -f "px4_safety_bridge_node" 2>/dev/null || true
pkill -9 -f "mock_sensor_publisher" 2>/dev/null || true

# Sensor consultant agents (upstream of T1).
pkill -9 -f "radar_agent_node" 2>/dev/null || true
pkill -9 -f "rf_agent_node" 2>/dev/null || true
pkill -9 -f "acoustic_agent_node" 2>/dev/null || true
pkill -9 -f "eo_agent_node" 2>/dev/null || true

# TB-CSPN coordination transitions (T1-T7).
pkill -9 -f "interpretation_node" 2>/dev/null || true
pkill -9 -f "candidate_transition_node" 2>/dev/null || true
pkill -9 -f "mission_transition_node" 2>/dev/null || true
pkill -9 -f "dispatch_transition_node" 2>/dev/null || true

# Supervisor side of T6: the scripted supervisor and the console bridge.
pkill -9 -f "scripted_supervisor_node" 2>/dev/null || true
pkill -9 -f "console_bridge_node" 2>/dev/null || true

# Worker agents and the intruder.
pkill -9 -f "uav_worker_node" 2>/dev/null || true
pkill -9 -f "ugv_worker_node" 2>/dev/null || true
pkill -9 -f "px4_safety_gate_node" 2>/dev/null || true
pkill -9 -f "intruder_node" 2>/dev/null || true

# Gazebo <-> ROS 2 topic bridges.
pkill -9 -f "parameter_bridge" 2>/dev/null || true

rm -rf /tmp/.gazebo* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null || true
echo "All processes terminated."