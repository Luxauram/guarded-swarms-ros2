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
# Guarded Swarms - Kill All Processes
#
# Terminates all simulation and ROS2 processes cleanly.
# Called by: make kill-all
#
# NOTE: kept separate from Makefile because inline pkill commands
# can accidentally kill the make process itself.
# ==============================================================================

echo "Shutting down all processes..."
pkill -9 -f "make.*px4_sitl" 2>/dev/null; true
pkill -9 -f "cmake.*px4_sitl" 2>/dev/null; true
sleep 1
pkill -9 -x px4 2>/dev/null; true
pkill -9 -x gz 2>/dev/null; true
pkill -9 -f "px4-gz_bri" 2>/dev/null; true
pkill -9 -f "gz_sim_serv" 2>/dev/null; true
pkill -9 gzserver 2>/dev/null; true
pkill -9 gzclient 2>/dev/null; true
pkill -9 MicroXRCEAgent 2>/dev/null; true
pkill -9 -f "safety_board" 2>/dev/null; true
pkill -9 -f "command_brid" 2>/dev/null; true
pkill -9 -f "coordinator_" 2>/dev/null; true
pkill -9 -f "agent_node" 2>/dev/null; true
pkill -9 -f "px4_safety_b" 2>/dev/null; true
pkill -9 -f "offboard_con" 2>/dev/null; true
pkill -9 -f "parameter_br" 2>/dev/null; true
rm -rf /tmp/.gazebo* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null; true
echo "All processes terminated."