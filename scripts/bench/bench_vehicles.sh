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
# @file bench_vehicles.sh
# Measures how the real-time factor degrades as PX4 instances are added.
#
# This decides how large the final scenario can be. PX4 SITL runs in lockstep
# with Gazebo, so every added instance is a synchronisation point: the cost is
# not a simple sum of per-vehicle work, and it has to be measured rather than
# estimated.
#
# The script cleans up before and after. Earlier manual attempts were polluted
# by leftover instances holding the shell lock, which silently invalidated the
# numbers, so cleanup is not optional here.
#
# Two knobs matter for the result:
#   MODEL     gz_x500_lidar_front carries a 640-ray GPU lidar; gz_x500 does
#             not. Comparing the two separates sensor cost from vehicle cost.
#   HEADLESS  the Gazebo GUI alone was measured at ~193% CPU, so metric
#             campaigns are meant to run headless and the GUI kept for video.
#
# Usage:
#   bash scripts/bench_vehicles.sh                  # 6 lidar UAVs, headless
#   MODEL=gz_x500 bash scripts/bench_vehicles.sh    # same without lidar
#   HEADLESS=0 MAX=4 bash scripts/bench_vehicles.sh # with GUI, up to 4
# ==============================================================================
set -u

# awk formats and parses numbers according to the locale. Under it_IT the
# decimal separator is a comma, so a value printed as "0,987" is read back as
# 987 on the next iteration and the running average explodes.
export LC_ALL=C

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
BUILD_DIR="$PX4_DIR/build/px4_sitl_default"

WORLD="${WORLD:-coastal}"
MODEL="${MODEL:-gz_x500_lidar_front}"
AUTOSTART="${AUTOSTART:-4017}"
MAX="${MAX:-6}"
HEADLESS="${HEADLESS:-1}"
SETTLE_S="${SETTLE_S:-15}"      # time for an instance to boot and stabilise
SAMPLES="${SAMPLES:-5}"          # RTF samples averaged per data point

# Fleet geometry: instance i spawns on a line at x = i*SPAWN_STEP_M + SPAWN_X0_M.
SPAWN_STEP_M=15
SPAWN_X0_M=-40
SPAWN_Y_M=-40

GZ_BOOT_S=12         # wait for Gazebo to come up before the first measurement
RTF_SAMPLE_TIMEOUT_S=10  # per-sample timeout when reading the world stats

RESULTS=()

cleanup() {
    echo
    echo "Cleaning up..."
    pkill -9 -f 'bin/px4 -i' 2>/dev/null
    pkill -9 -x px4 2>/dev/null
    bash "$REPO_ROOT/scripts/sim/gz_kill.sh" 2>/dev/null
    sleep 2
}
trap cleanup EXIT

# Average several RTF samples: a single reading swings by tens of percent.
measure_rtf() {
    local total=0 n=0 v
    for _ in $(seq 1 "$SAMPLES"); do
        v=$(timeout "$RTF_SAMPLE_TIMEOUT_S" gz topic -e -t "/world/$WORLD/stats" -n 1 2>/dev/null \
            | grep real_time_factor | awk '{print $2}')
        if [ -n "$v" ]; then
            total=$(awk "BEGIN{print $total + $v}")
            n=$((n + 1))
        fi
    done
    if [ "$n" -eq 0 ]; then
        echo "n/a"
    else
        awk "BEGIN{printf \"%.3f\", $total / $n}"
    fi
}

echo "=========================================="
echo "Vehicle scaling benchmark"
echo "=========================================="
echo "  world     : $WORLD"
echo "  model     : $MODEL (autostart $AUTOSTART)"
echo "  headless  : $HEADLESS"
echo "  max       : $MAX vehicles"
echo "  settle    : ${SETTLE_S}s per instance, $SAMPLES RTF samples"
echo

cleanup

echo "Starting Gazebo..."
if [ "$HEADLESS" = "1" ]; then
    bash "$REPO_ROOT/scripts/sim/gz_launch.sh" "$WORLD" --headless \
        > /tmp/bench_gz.log 2>&1 &
else
    bash "$REPO_ROOT/scripts/sim/gz_launch.sh" "$WORLD" \
        > /tmp/bench_gz.log 2>&1 &
fi
sleep "$GZ_BOOT_S"

BASE=$(measure_rtf)
echo "  0 vehicles: RTF $BASE"
RESULTS+=("0 $BASE")

for i in $(seq 0 $((MAX - 1))); do
    pose="$((i * SPAWN_STEP_M + SPAWN_X0_M)),${SPAWN_Y_M},0"
    # stdin redirected from /dev/null: a backgrounded PX4 tries to read its
    # pxh> prompt, receives SIGTTIN and is suspended. A suspended client is
    # still attached to the lockstep, so it stalls Gazebo and the measurement
    # silently becomes meaningless.
    ( cd "$BUILD_DIR" && \
      PX4_GZ_STANDALONE=1 \
      PX4_GZ_NO_FOLLOW=1 \
      PX4_SYS_AUTOSTART="$AUTOSTART" \
      PX4_SIM_MODEL="$MODEL" \
      PX4_GZ_WORLD="$WORLD" \
      PX4_GZ_MODEL_POSE="$pose" \
      GZ_SIM_RESOURCE_PATH="$REPO_ROOT/src/guarded_swarms_gz/models" \
      ./bin/px4 -i "$i" > "/tmp/bench_px4_$i.log" 2>&1 < /dev/null & )
    sleep "$SETTLE_S"
    if ! pgrep -f "bin/px4 -i $i" > /dev/null; then
        echo "  $((i + 1)) vehicles: instance $i FAILED to start"
        echo "                see /tmp/bench_px4_$i.log"
        RESULTS+=("$((i + 1)) failed")
        continue
    fi
    rtf=$(measure_rtf)
    echo "  $((i + 1)) vehicles: RTF $rtf"
    RESULTS+=("$((i + 1)) $rtf")
done

echo
echo "=========================================="
echo "Results: $MODEL, headless=$HEADLESS"
echo "=========================================="
printf "  %-10s %s\n" "vehicles" "RTF"
for r in "${RESULTS[@]}"; do
    printf "  %-10s %s\n" $r
done
echo
echo "Reading: a simulated minute costs 1/RTF real minutes. Below about 0.4 a"
echo "metric campaign becomes impractical and the scenario should be sized down,"
echo "or the lidar sample count and physics rate reduced."