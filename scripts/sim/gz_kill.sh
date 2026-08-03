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
# Guarded Swarms - Gazebo + PX4 process cleanup.
#
# Terminates all Gazebo and PX4 SITL processes and clears the shared memory
# and temporary files they leave behind. Run before launching a new Gazebo
# session to guarantee a clean slate; a stale gzserver or leftover parameter
# file is a common cause of a simulation that starts but never arms.
#
# Every kill is followed by '|| true': pkill returns non-zero when it matches
# no process, which is the normal case here (nothing to kill), and must not
# abort the cleanup. For the same reason this script does NOT use 'set -e'.
#
# Usage:
#   ./scripts/sim/gz_kill.sh
#   make px4-kill
#
# @author Luca D'Aurizio
# ==============================================================================

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"

# Terminate the simulator and every helper process it spawns.
pkill -9 -x px4 2>/dev/null || true
pkill -9 -f "gz sim --verbose" 2>/dev/null || true
pkill -9 -f "px4-gz_bri" 2>/dev/null || true
pkill -9 -f "gz_sim_serv" 2>/dev/null || true
pkill -9 gzserver 2>/dev/null || true
pkill -9 gzclient 2>/dev/null || true

# Give the processes time to release their handles before we delete the
# shared-memory segments and parameter files they were using.
sleep 3

rm -rf /tmp/.gazebo* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null || true
find "$PX4_DIR/build/px4_sitl_default" -name 'parameters*.bson' -delete 2>/dev/null || true