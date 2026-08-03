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
# @file launch_ugv_swarm.sh
# Spawn a single rover (UGV) PX4 instance attached to a running Gazebo world.
#
# Standalone helper: it attaches one rover instance to a Gazebo server that is
# already up (PX4_GZ_STANDALONE=1). The multi-vehicle demos (make demo-swarm,
# make demo-coastal) spawn their vehicles inline and are the supported path;
# this script is a lower-level helper for launching one rover by hand.
#
# Usage:
#   INSTANCE=1 UGV_POSE=10,10 ./scripts/launch_ugv_swarm.sh
#
# Environment:
#   INSTANCE  PX4 instance index (default 1); sets MAV_SYS_ID = INSTANCE + 1.
#   UGV_POSE  spawn pose "x,y" in Gazebo ENU metres (default 10,10).
#   WORLD     Gazebo world name (default urban_ugv).
# ==============================================================================
set -e

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

INSTANCE="${INSTANCE:-1}"
UGV_POSE="${UGV_POSE:-10,10}"
WORLD="${WORLD:-urban_ugv}"

# PX4_SYS_AUTOSTART 4009 is the stock rover airframe. Guarded Swarms assets are
# resolved via GZ_SIM_RESOURCE_PATH, so nothing is copied into the PX4 tree.
cd "$PX4_DIR/build/px4_sitl_default" && \
  PX4_GZ_STANDALONE=1 \
  PX4_SYS_AUTOSTART=4009 \
  PX4_SIM_MODEL=gz_r1_rover \
  PX4_GZ_WORLD="$WORLD" \
  PX4_GZ_MODEL_POSE="$UGV_POSE" \
  GZ_SIM_RESOURCE_PATH="$REPO_ROOT/src/guarded_swarms_gz/models:$REPO_ROOT/src/guarded_swarms_gz/worlds" \
  ./bin/px4 -i "$INSTANCE"