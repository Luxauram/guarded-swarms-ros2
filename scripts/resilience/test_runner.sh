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
# @file test_runner.sh
#
# Guarded Swarms - Resilience Test Runner
#
# Runs all resilience tests sequentially and generates a final report.
# Requires the mock pipeline to be running before launching.
#
# Usage:
#   ./scripts/resilience/test_runner.sh [mock|uav_r1|ugv_r2]
#
# Example:
#   # Terminal 1: start the pipeline
#   ros2 launch guarded_swarms_bringup mock_pipeline.launch.py
#
#   # Terminal 2: run all tests
#   ./scripts/resilience/test_runner.sh mock
#
# @author Luca D'Aurizio
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
TESTS_DIR="$SCRIPT_DIR/tests"
CONFIG_DIR="$SCRIPT_DIR/config"
RESULTS_DIR="$SCRIPT_DIR/results"

SCENARIO="${1:-mock}"
CONFIG_FILE="$CONFIG_DIR/${SCENARIO}.yaml"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[runner]${NC} $1"; }
ok()   { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: config not found: $CONFIG_FILE"
    echo "Available scenarios: mock, uav_r1, ugv_r2"
    exit 1
fi

source /opt/ros/humble/setup.bash
if [ -f "$REPO_DIR/install/setup.bash" ]; then
    source "$REPO_DIR/install/setup.bash"
fi
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
mkdir -p "$RESULTS_DIR"

echo ""
echo "============================================================"
echo "  Guarded Swarms - Resilience Test Suite"
echo "  Scenario: $SCENARIO"
echo "  Config:   $CONFIG_FILE"
echo "============================================================"
echo ""
warn "Prerequisites: pipeline already running for scenario '$SCENARIO'"
warn "  mock:   ros2 launch guarded_swarms_bringup mock_pipeline.launch.py"
warn "  uav_r1: make demo-px4-uav-urban (then make demo-uav-urban-pipeline)"
warn "  ugv_r2: make demo-px4-ugv-urban (then make demo-ugv-urban-pipeline)"
echo ""

PASSED=0
FAILED=0
TOTAL=0

run_test() {
    local test_file="$1"
    local test_name
    test_name="$(basename "$test_file" .py)"
    TOTAL=$((TOTAL + 1))
    log "Running: $test_name..."
    if python3 "$test_file" "$CONFIG_FILE"; then
        ok "$test_name"
        PASSED=$((PASSED + 1))
    else
        fail "$test_name"
        FAILED=$((FAILED + 1))
    fi
    echo ""
}

run_test "$TESTS_DIR/test_forged_tokens.py"
run_test "$TESTS_DIR/test_dropped_tokens.py"

# Sensor tests only in the mock scenario: with PX4 running, the real
# mock_sensor_publisher is absent and these would have nothing to drive them.
if [ "$SCENARIO" = "mock" ]; then
    run_test "$TESTS_DIR/test_sensor_staleness.py"
    run_test "$TESTS_DIR/test_sensor_spike.py"
fi

echo ""
echo "============================================================"
echo "  Final Summary - Scenario: $SCENARIO"
echo "============================================================"
echo "  Total:  $TOTAL"
echo -e "  Passed: ${GREEN}$PASSED${NC}"
echo -e "  Failed: ${RED}$FAILED${NC}"
echo "  Results: $RESULTS_DIR"
echo "============================================================"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All resilience tests passed.${NC}"
    exit 0
else
    echo -e "${RED}$FAILED test(s) failed.${NC}"
    exit 1
fi