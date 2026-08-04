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
# @file launch_uav_swarm.sh
# Spawn a single UAV (x500 + lidar) PX4 instance in a Gazebo world.
#
# Standalone helper: it launches one x500 quadcopter with the front lidar via
# PX4's own make target. The multi-vehicle demos (make demo-swarm, make
# demo-coastal) spawn their vehicles inline and are the supported path; this
# script is a lower-level helper for launching one UAV by hand.
#
# Usage:
#   ./scripts/sim/launch_uav_swarm.sh                       # default resource path
#   GZ_RESOURCE_PATH=/my/models ./scripts/sim/launch_uav_swarm.sh
#
# Environment:
#   WORLD             Gazebo world name (default urban_uav).
#   GZ_RESOURCE_PATH  colon-separated model/world search path (default: the
#                     Guarded Swarms models and worlds).
# ==============================================================================
set -e

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

WORLD="${WORLD:-urban_uav}"
GZ_RESOURCE_PATH="${GZ_RESOURCE_PATH:-$REPO_ROOT/src/guarded_swarms_gz/models:$REPO_ROOT/src/guarded_swarms_gz/worlds}"

# NVIDIA PRIME render offload so Gazebo uses the discrete GPU (required for
# lidar rendering); harmless on non-NVIDIA systems. MESA_GL_VERSION_OVERRIDE
# forces an OpenGL 4.5 context, which Gazebo Harmonic needs on some drivers.
cd "$PX4_DIR" && \
  __NV_PRIME_RENDER_OFFLOAD=1 \
  __GLX_VENDOR_LIBRARY_NAME=nvidia \
  MESA_GL_VERSION_OVERRIDE=4.5 \
  PX4_GZ_WORLD="$WORLD" \
  GZ_SIM_RESOURCE_PATH="$GZ_RESOURCE_PATH" \
  make px4_sitl gz_x500_lidar_front