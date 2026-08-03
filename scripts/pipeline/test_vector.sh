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
# test_vector.sh - quick check of detection asymmetry by attack vector.
#
# Records a short bag while the intruder ingresses along one vector, then prints
# how many observations each modality produced.
#
# Prereq (in other terminals, left running):
#   make demo-coastal
#   ros2 launch guarded_swarms_sensing sensing.launch.py eo:=false
#
# Usage:  ./test_vector.sh sea       (ingress from the open sea, north)
#         ./test_vector.sh east-deep (ingress through the coverage hole)
#         ./test_vector.sh rear      (ingress from behind the radar)
#         ./test_vector.sh inland    (ingress from behind the town, south)
#         ./test_vector.sh lateral   (ingress from the east flank)
# ==============================================================================
set -o pipefail

INTRUDER_SPEED_MPS=8.0    # fast ingress: this is a coverage probe, not a demo
INTRUDER_DELAY_S=5.0      # s before the intruder starts moving
INGRESS_Z_M=15.0          # ingress and target altitude
RECORD_S=40               # bag duration
BAG_FLUSH_S=3             # let rosbag2 flush and close the db before reading

VECTOR="${1:-sea}"
case "$VECTOR" in
  sea|frontal) IX=0.0;    IY=180.0;   TX=0.0; TY=10.0 ;;   # well-covered front
  east-deep)   IX=250.0;  IY=-120.0;  TX=0.0; TY=10.0 ;;   # coverage hole (map)
  rear)        IX=0.0;    IY=-200.0;  TX=0.0; TY=-120.0 ;; # behind the radar
  inland)      IX=-140.0; IY=-80.0;   TX=0.0; TY=10.0 ;;
  lateral)     IX=200.0;  IY=60.0;    TX=0.0; TY=40.0 ;;
  *) echo "unknown vector: $VECTOR (use sea|east-deep|rear|inland|lateral)"; exit 1 ;;
esac

BAG="/tmp/vec_${VECTOR}"
rm -rf "$BAG"
echo "[vec] vector=$VECTOR  ingress=($IX,$IY)  target=($TX,$TY)"

pkill -f intruder_node 2>/dev/null
sleep 2

echo "[vec] starting bag..."
ros2 bag record -o "$BAG" /obs_tokens /interp_tokens /intruder/ground_truth \
  >/tmp/vec_bag.log 2>&1 &
BAGPID=$!
sleep 2

echo "[vec] launching intruder..."
ros2 launch guarded_swarms_bringup intruder.launch.py \
  ingress_x:=$IX ingress_y:=$IY ingress_z:=$INGRESS_Z_M \
  target_x:=$TX target_y:=$TY target_z:=$INGRESS_Z_M \
  speed_mps:=$INTRUDER_SPEED_MPS start_delay_s:=$INTRUDER_DELAY_S \
  >/tmp/vec_intruder.log 2>&1 &
LAUNCHPID=$!

echo "[vec] recording ${RECORD_S} s..."
sleep "$RECORD_S"

echo "[vec] stopping..."
kill "$BAGPID" 2>/dev/null
kill "$LAUNCHPID" 2>/dev/null
pkill -f intruder_node 2>/dev/null
sleep "$BAG_FLUSH_S"

echo "[vec] counting detections by modality..."
python3 - "$BAG" <<'PY'
import sys
sys.path.insert(0, "scripts/metrics")
from metrics_chain import read_bag
from collections import Counter
bag = sys.argv[1]
d = read_bag(bag)
obs = Counter(getattr(m, "source", "?") for _, m in d.get("/obs_tokens", []))
interp = Counter(getattr(m, "label", "?") for _, m in d.get("/interp_tokens", []))
print(f"  vector bag: {bag}")
print(f"  observations by source : {dict(obs)}")
print(f"  interpretations by label: {dict(interp)}")
PY