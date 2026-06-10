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
# @file gz_kill.sh
#
# Guarded Swarms - Gazebo + PX4 Process Cleanup
#
# Terminates all Gazebo and PX4 SITL processes and cleans up shared
# memory and temporary files. Called before launching a new Gazebo
# session to ensure a clean state.
#
# Usage:
#   ./scripts/gz_kill.sh
#   make px4-kill
#
# @author Luca D'Aurizio
# ==============================================================================

pkill -9 -x px4 2>/dev/null; true
pkill -9 -f "gz sim --verbose" 2>/dev/null; true
pkill -9 -f "px4-gz_bri" 2>/dev/null; true
pkill -9 -f "gz_sim_serv" 2>/dev/null; true
pkill -9 gzserver 2>/dev/null; true
pkill -9 gzclient 2>/dev/null; true
sleep 3
rm -rf /tmp/.gazebo* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null; true
find ~/PX4-Autopilot/build/px4_sitl_default -name 'parameters*.bson' -delete 2>/dev/null; true