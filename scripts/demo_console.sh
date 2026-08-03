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
# demo_console.sh -- live end-to-end demonstration of the supervisor console.
#
# This is NOT the test harness (scripts/test_pipeline.sh). It is the clean demo
# path: it launches the adversary, the sensing layer and the TB-CSPN
# coordination layer, then simply follows /mission_tokens and prints every
# governed mission release the instant it happens. There are no phases, no
# ConfirmedThreat wait, no decision timeout -- you open the console, and
# whenever you press Authorise, the released mission appears here at once.
#
# Prereqs (start these first, each in its own terminal):
#   1. make demo-coastal                     # Gazebo + vehicles
#   2. rosbridge (workspace sourced):
#        source /opt/ros/humble/setup.bash
#        source ~/guarded-swarms-ros2/install/setup.bash
#        ros2 launch rosbridge_server rosbridge_websocket_launch.xml
#   3. the console bridge:
#        python3 console/console_bridge_node.py
# Then run THIS script, and finally open console/decision_panel.html.
#
# Ctrl-C tears the demo down.
# ==============================================================================
set -o pipefail

# Demo intruder profile: low, sea-skimming, holds on the coastal objective
# inside the EO cone, so the ConfirmedThreat is stable (see test_pipeline.sh
# 'demo' vector for the geometry rationale). Overridable from the environment.
IN_X="${IN_X:--24.0}";  IN_Y="${IN_Y:-180.0}"; IN_Z="${IN_Z:-2.0}"
TG_X="${TG_X:--24.0}";  TG_Y="${TG_Y:-20.0}";  TG_Z="${TG_Z:-2.0}"
SPEED="${INTRUDER_SPEED:-15.0}"
DELAY="${INTRUDER_DELAY:-8.0}"

PIDS=()

cleanup() {
  echo ""
  echo "[demo] tearing down..."
  for n in radar_agent_node rf_agent_node acoustic_agent_node eo_agent_node \
           interpretation_node candidate_transition_node \
           mission_transition_node dispatch_transition_node \
           uav_worker_node ugv_worker_node intruder_node; do
    pkill -f "$n" 2>/dev/null
  done
  pkill -f "sensing.launch"  2>/dev/null
  pkill -f "tbcspn.launch"   2>/dev/null
  pkill -f "intruder.launch" 2>/dev/null
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
  wait 2>/dev/null
  echo "[demo] done."
}
trap cleanup INT TERM EXIT

echo "[demo] launching intruder (low approach, holds on the objective)..."
ros2 launch guarded_swarms_bringup intruder.launch.py \
  ingress_x:="${IN_X}" ingress_y:="${IN_Y}" ingress_z:="${IN_Z}" \
  target_x:="${TG_X}" target_y:="${TG_Y}" target_z:="${TG_Z}" \
  speed_mps:="${SPEED}" start_delay_s:="${DELAY}" \
  >/tmp/gs_demo_intruder.log 2>&1 &
PIDS+=($!)

echo "[demo] launching sensing layer..."
ros2 launch guarded_swarms_sensing sensing.launch.py \
  >/tmp/gs_demo_sensing.log 2>&1 &
PIDS+=($!)

echo "[demo] launching TB-CSPN coordination layer (T1-T7)..."
ros2 launch guarded_swarms_tbcspn tbcspn.launch.py \
  >/tmp/gs_demo_tbcspn.log 2>&1 &
PIDS+=($!)

echo "[demo] =============================================================="
echo "[demo]  The console is live."
echo "[demo]  1. open  console/decision_panel.html  in your browser"
echo "[demo]  2. when the card arms (ConfirmedThreat), press Authorise"
echo "[demo]  3. each governed mission release prints below, immediately"
echo "[demo]  (press Deny, or do nothing, and no mission is released:"
echo "[demo]   without human authorisation the swarm does not act.)"
echo "[demo]  Ctrl-C to finish."
echo "[demo] =============================================================="

# Follow /mission_tokens from now on. Each mission_id printed is one governed
# release -- one human authorisation, one mission. Listening starts right away
# and never stops, so no matter when you click, the release shows up at once.
stdbuf -oL ros2 topic echo /mission_tokens --field mission_id 2>/dev/null \
  | stdbuf -oL grep --line-buffered '^mission-' \
  | while IFS= read -r mid; do
      echo "[swarm] $(date +%H:%M:%S)  mission released: ${mid}  (authorised from the console)"
    done
wait