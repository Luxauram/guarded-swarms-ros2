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
# @file px4_configure.sh
# Applies SITL parameters to a running PX4 instance from an ordinary shell.
#
# PX4 SITL ships client binaries (px4-param, px4-commander, ...) that talk to a
# running instance over its working directory. This replaces driving the pxh>
# prompt with expect, which is fragile inside xterm inside make, and lets the
# whole demo stay scriptable and reproducible.
#
# Usage: px4_configure.sh <instance> <uav|ugv>
#
# UAV parameters disable the RC / data-link failsafes that would otherwise
# refuse arming with "no connection to the GCS" (VehicleCommandAck result 1),
# since offboard control is commanded from ROS 2 with no RC and no GCS.
#
# The UGV needs no parameters: PX4 defaults are correct for it. In particular
# never set SYS_HAS_MAG 0 on the rover — without a magnetometer its EKF never
# converges, local position stays invalid, and failsafe disarms it immediately.
# ==============================================================================
set -e

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
BUILD_DIR="$PX4_DIR/build/px4_sitl_default"

INSTANCE="${1:?usage: px4_configure.sh <instance> <uav|ugv>}"
VEHICLE="${2:?usage: px4_configure.sh <instance> <uav|ugv>}"

cd "$BUILD_DIR"
export PX4_SHELL_INSTANCE="$INSTANCE"

# px4-param targets the instance selected by PX4_SHELL_INSTANCE.
param() { ./bin/px4-param "$@"; }

case "$VEHICLE" in
    uav)
        echo "[px4_configure] instance $INSTANCE: UAV offboard parameters"
        param set COM_RC_IN_MODE 1
        param set NAV_RCL_ACT 0
        param set NAV_DLL_ACT 0
        param set COM_RCL_EXCEPT 4
        param set COM_ARM_WO_GPS 1
        param save
        ;;
    ugv)
        echo "[px4_configure] instance $INSTANCE: UGV uses PX4 defaults, nothing to do"
        ;;
    *)
        echo "ERROR: unknown vehicle type '$VEHICLE' (expected uav or ugv)"
        exit 1
        ;;
esac

echo "[px4_configure] done."