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
# never set SYS_HAS_MAG 0 on the rover - without a magnetometer its EKF never
# converges, local position stays invalid, and failsafe disarms it immediately.
# ==============================================================================
set -e

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
BUILD_DIR="$PX4_DIR/build/px4_sitl_default"

INSTANCE="${1:?usage: px4_configure.sh <instance> <uav|ugv>}"
VEHICLE="${2:?usage: px4_configure.sh <instance> <uav|ugv>}"

# One uXRCE-DDS agent per instance, on its own UDP port.
# A single agent serving three PX4 instances saturates and blocks the clients
# in write. Because PX4 SITL runs in lockstep, a blocked client stalls Gazebo
# itself: the real-time factor collapses from 1.0 to ~0.0005, which looks like
# a frozen simulation rather than a bandwidth problem.
DDS_PORT=$((8888 + INSTANCE))

cd "$BUILD_DIR"

# The PX4 shell clients select the running instance with --instance N, which
# must come before the sub-command. There is no -i flag and the working
# directory is irrelevant: without --instance every client talks to instance 0,
# so a multi-vehicle setup silently configures the wrong vehicle.
param() { ./bin/px4-param --instance "$INSTANCE" "$@"; }

case "$VEHICLE" in
    uav)
        echo "[px4_configure] instance $INSTANCE: UAV offboard parameters"
        param set COM_RC_IN_MODE 1
        param set NAV_RCL_ACT 0
        param set NAV_DLL_ACT 0
        param set COM_RCL_EXCEPT 4
        param set COM_ARM_WO_GPS 1
        # The SITL battery drains over time; in a long demo session it eventually
        # trips a failsafe mid-flight. Disable it: this is a simulation scenario,
        # not an endurance test.
        param set COM_LOW_BAT_ACT 0
        param save
        ;;
    ugv)
        echo "[px4_configure] instance $INSTANCE: UGV parameters"
        param set COM_LOW_BAT_ACT 0
        param save
        ;;
    *)
        echo "ERROR: unknown vehicle type '$VEHICLE' (expected uav or ugv)"
        exit 1
        ;;
esac

if [ "$INSTANCE" != "0" ]; then
    echo "[px4_configure] instance $INSTANCE: uXRCE-DDS port $DDS_PORT"
    param set UXRCE_DDS_PRT "$DDS_PORT"
    param save
    # The client reads the port once, at startup, so it must be restarted for
    # the new value to take effect. PX4 restores the per-instance topic
    # namespace (px4_<N>) on its own when the client is started this way.
    ./bin/px4-uxrce_dds_client --instance "$INSTANCE" stop || true
    sleep 1
    ./bin/px4-uxrce_dds_client --instance "$INSTANCE" start -n "px4_$INSTANCE"
fi

echo "[px4_configure] done."