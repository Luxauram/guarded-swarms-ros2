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
# @file record_demo.sh
#
# Guarded Swarms - demo recording script for the safety-layer scenarios.
#
# Records the safety-board and vehicle topics during a UAV, UGV or mock demo
# session to a bag file for later replay.
#
# NOTE: this records the safety-layer / vehicle topics only. To record the full
# TB-CSPN coastal pipeline for metric analysis, use scripts/record_run.sh
# instead, which captures the semantic chain (observations -> interpretations
# -> mission -> tasks).
#
# Output: bags/guarded_swarms_<scenario>_<timestamp>/
#
# Usage:
#   ./scripts/record_demo.sh uav    # record UAV scenario (R1)
#   ./scripts/record_demo.sh ugv    # record UGV scenario (R2)
#   ./scripts/record_demo.sh mock   # record mock pipeline (no PX4)
#
# The bag can later be replayed with:
#   ros2 bag play bags/<bag_name>
#
# @author Luca D'Aurizio
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
BAGS_DIR="$REPO_DIR/bags"

SCENARIO="${1:-uav}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BAG_NAME="guarded_swarms_${SCENARIO}_${TIMESTAMP}"
BAG_PATH="$BAGS_DIR/$BAG_NAME"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${BLUE}[record]${NC} $1"; }
ok()   { echo -e "${GREEN}[ok]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }

# Topics common to all scenarios: the analog safety board's command pipeline
# and status.
COMMON_TOPICS=(
    /actuator_cmd_raw
    /actuator_cmd_safe
    /safety_status
    /supervisor_auth
)

case "$SCENARIO" in
    uav)
        EXTRA_TOPICS=(
            /drone/proximity
            /drone/altitude
            /drone/battery
            /drone/imu
            /fmu/out/vehicle_local_position_v1
            /fmu/out/vehicle_attitude
            /fmu/out/battery_status_v1
        )
        SCENARIO_LABEL="UAV (R1)"
        ;;
    ugv)
        EXTRA_TOPICS=(
            /drone/proximity
            /drone/battery
            /drone/imu
            /fmu/out/vehicle_local_position_v1
            /fmu/out/vehicle_attitude
            /fmu/out/battery_status_v1
        )
        SCENARIO_LABEL="UGV (R2)"
        ;;
    mock)
        EXTRA_TOPICS=(
            /drone/proximity
            /drone/altitude
            /drone/battery
            /drone/imu
        )
        SCENARIO_LABEL="Mock Pipeline"
        ;;
    *)
        echo "Usage: $0 [uav|ugv|mock]"
        exit 1
        ;;
esac

ALL_TOPICS=("${COMMON_TOPICS[@]}" "${EXTRA_TOPICS[@]}")

mkdir -p "$BAGS_DIR"

echo ""
echo "============================================================"
log "Guarded Swarms - Demo Recording"
echo "============================================================"
log "Scenario:  $SCENARIO_LABEL"
log "Output:    $BAG_PATH"
log "Topics:"
for t in "${ALL_TOPICS[@]}"; do
    echo "           $t"
done
echo "============================================================"
echo ""
warn "Press Ctrl+C to stop recording."
echo ""

source /opt/ros/humble/setup.bash
if [ -f "$REPO_DIR/install/setup.bash" ]; then
    source "$REPO_DIR/install/setup.bash"
fi

ros2 bag record \
    --output "$BAG_PATH" \
    --storage sqlite3 \
    "${ALL_TOPICS[@]}"

echo ""
ok "Recording saved to: $BAG_PATH"
echo ""
echo "Replay with:"
echo "  ros2 bag play $BAG_PATH"
echo ""
echo "Inspect with:"
echo "  ros2 bag info $BAG_PATH"
echo ""