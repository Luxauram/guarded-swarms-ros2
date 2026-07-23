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
# @file gz_launch.sh
# Single point of truth for the Gazebo environment.
#
# Exports the Guarded Swarms asset paths FIRST, then sources PX4's generated
# gz_env.sh, which appends its own models/worlds and — critically — sets
# GZ_SIM_SYSTEM_PLUGIN_PATH and GZ_SIM_SERVER_CONFIG_PATH. Without the latter
# Gazebo loads no PX4 sensor systems and every preflight check fails
# (accel/gyro/baro/mag "missing").
#
# Because my paths come first, model:// and world lookups resolve to my
# versions: nothing is ever copied into the PX4 tree.
#
# Usage: gz_launch.sh <world_name> [--headless]
# ==============================================================================
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
GZ_ENV="$PX4_DIR/build/px4_sitl_default/rootfs/gz_env.sh"

WORLD="${1:?usage: gz_launch.sh <world_name> [--headless]}"
HEADLESS_FLAG=""
[ "${2:-}" = "--headless" ] && HEADLESS_FLAG="-s"

if [ ! -f "$GZ_ENV" ]; then
    echo "ERROR: $GZ_ENV not found."
    echo "Build PX4 first: cd $PX4_DIR && make px4_sitl_default"
    exit 1
fi

# Guarded Swarms assets first — they shadow PX4's stock ones.
export GZ_SIM_RESOURCE_PATH="$REPO_ROOT/src/guarded_swarms_gz/models:$REPO_ROOT/src/guarded_swarms_gz/worlds"

# PX4 env: appends its models/worlds, sets plugin path + server config.
# shellcheck disable=SC1090
source "$GZ_ENV"

# NVIDIA offload (harmless on non-NVIDIA systems)
export __NV_PRIME_RENDER_OFFLOAD=1
export __GLX_VENDOR_LIBRARY_NAME=nvidia
export MESA_GL_VERSION_OVERRIDE=4.5

echo "[gz_launch] world: $WORLD"
exec gz sim -r $HEADLESS_FLAG "${WORLD}.sdf"