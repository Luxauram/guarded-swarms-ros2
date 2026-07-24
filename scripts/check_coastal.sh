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
# @file check_coastal.sh
# Health check for a running coastal scenario. Prints PASS/FAIL per item.
#
# Written because the Gazebo GUI cannot be trusted as a diagnostic tool in this
# scenario: under load it renders a stale frame, so vehicles that are actually
# moving appear frozen at their spawn point. Ground truth comes from
# 'gz model -p' and from the PX4 shell clients, never from the viewport.
#
# Usage: bash scripts/check_coastal.sh
# Run it after 'make demo-coastal' has finished starting everything.
# ==============================================================================

WORLD="${WORLD:-coastal}"
PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
BUILD_DIR="$PX4_DIR/build/px4_sitl_default"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YEL=$'\033[1;33m'; NC=$'\033[0m'
FAILURES=0

pass() { echo "  ${GREEN}PASS${NC}  $1"; }
fail() { echo "  ${RED}FAIL${NC}  $1"; FAILURES=$((FAILURES + 1)); }
warn() { echo "  ${YEL}WARN${NC}  $1"; }
head() { echo; echo "== $1 =="; }

# Ground truth pose of a Gazebo model: "x y z".
# Warnings on stderr are discarded; they are harmless gz_frame_id notices.
model_pose() {
    gz model -m "$1" -p 2>/dev/null \
        | grep -A1 'Pose' | tail -1 | tr -d '[]' | awk '{print $1, $2, $3}'
}

# -----------------------------------------------------------------------------
head "Simulation"
# -----------------------------------------------------------------------------
RTF=$(gz topic -e -t "/world/$WORLD/stats" -n 1 2>/dev/null \
      | grep real_time_factor | awk '{print $2}')

if [ -z "$RTF" ]; then
    fail "no stats from world '$WORLD' (is Gazebo running?)"
else
    if awk "BEGIN{exit !($RTF > 0.3)}"; then
        pass "real time factor $RTF"
    else
        fail "real time factor $RTF (simulation is stalled)"
    fi
fi

# -----------------------------------------------------------------------------
head "uXRCE-DDS namespaces"
# -----------------------------------------------------------------------------
TOPICS=$(ros2 topic list 2>/dev/null)
for ns_pattern in '^/fmu' 'px4_1/fmu' 'px4_2/fmu'; do
    n=$(echo "$TOPICS" | grep -c "$ns_pattern")
    if [ "$n" -ge 60 ]; then
        pass "$ns_pattern -> $n topics"
    else
        fail "$ns_pattern -> $n topics (expected ~65)"
    fi
done

# -----------------------------------------------------------------------------
head "Vehicles"
# -----------------------------------------------------------------------------
check_vehicle() {
    local label="$1" instance="$2" model="$3" expect="$4"

    local state
    state=$(cd "$BUILD_DIR" && ./bin/px4-commander --instance "$instance" status 2>/dev/null)

    if echo "$state" | grep -q "Armed"; then
        pass "$label armed"
    else
        fail "$label NOT armed"
    fi

    if echo "$state" | grep -q "in failsafe: no"; then
        pass "$label no failsafe"
    else
        fail "$label IN FAILSAFE"
    fi

    local pose z
    pose=$(model_pose "$model")
    if [ -z "$pose" ]; then
        fail "$label model '$model' not found in Gazebo"
        return
    fi
    z=$(echo "$pose" | awk '{print $3}')
    echo "        pose (x y z): $pose"

    if [ "$expect" = "airborne" ]; then
        if awk "BEGIN{exit !($z > 2.0)}"; then
            pass "$label airborne (z = $z)"
        else
            fail "$label on the ground (z = $z)"
        fi
    fi
}

check_vehicle "UAV0" 0 "x500_lidar_front_0" airborne
check_vehicle "UAV1" 1 "x500_lidar_front_1" airborne
check_vehicle "UGV " 2 "r1_rover_2" ground

# -----------------------------------------------------------------------------
head "Safety layer"
# -----------------------------------------------------------------------------
for ns in "" "/px4_1" "/px4_2"; do
    label="${ns:-/root}"

    prox=$(timeout 5 ros2 topic echo "$ns/drone/proximity" --once 2>/dev/null \
           | grep -E '^range:' | awk '{print $2}')
    safe=$(timeout 5 ros2 topic echo "$ns/actuator_cmd_safe" --once 2>/dev/null \
           | grep -E '^data:' | awk '{print $2}')

    if [ -z "$prox" ]; then
        fail "$label proximity not published"
    else
        pass "$label proximity ${prox} m"
    fi

    if [ -z "$safe" ]; then
        fail "$label actuator_cmd_safe not published"
    else
        if awk "BEGIN{exit !($safe < 0.01)}"; then
            warn "$label actuator_cmd_safe ${safe} (VETO active)"
        else
            pass "$label actuator_cmd_safe ${safe}"
        fi
    fi
done

# -----------------------------------------------------------------------------
head "PX4 tree is pristine"
# -----------------------------------------------------------------------------
dirty=$(git -C "$PX4_DIR" status --short 2>/dev/null | wc -l)
if [ "$dirty" -eq 0 ]; then
    pass "no local changes in $PX4_DIR"
else
    fail "$dirty modified paths in $PX4_DIR"
    git -C "$PX4_DIR" status --short | sed 's/^/        /'
fi

# -----------------------------------------------------------------------------
echo
if [ "$FAILURES" -eq 0 ]; then
    echo "${GREEN}All checks passed.${NC}"
else
    echo "${RED}$FAILURES check(s) failed.${NC}"
fi
exit "$FAILURES"
