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
# Terminates the whole stack with SIGKILL: the PX4 SITL build/run processes,
# Gazebo, the uXRCE-DDS agents, every Guarded Swarms ROS 2 node, and the shared
# memory and temporary files left behind.
#
# Kept as a script (not inline in the Makefile) on purpose: an inline
# 'pkill make' inside a recipe would also kill the make process running it.
#
# Every kill uses '|| true': pkill returns non-zero when it matches no
# process, which is normal here and must not abort the shutdown. For the same
# reason this script does NOT use 'set -e'.
#
# The nodes are matched with 'pkill -f' on the path of their executable, since
# ROS 2 executable names exceed the 15 characters pkill compares otherwise. A
# process that only names a node, such as an editor open on its source file,
# does not match.
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

# Every node of the packages, mock_sensor_publisher included, by the path of
# its executable: install/<package>/lib/<package>/<node>.
pkill -9 -f 'lib/guarded_swarms_[a-z0-9_]+/([a-z0-9_]+_node|mock_sensor_publisher)( |$)' 2>/dev/null || true

# The console bridge, which runs from the source tree with python3.
pkill -9 -f 'python3 [^ ]*console_bridge_node\.py( |$)' 2>/dev/null || true

# Gazebo <-> ROS 2 topic bridges.
pkill -9 -f 'lib/ros_gz_bridge/parameter_bridge( |$)' 2>/dev/null || true

rm -rf /tmp/.gazebo* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null || true
echo "All processes terminated."
