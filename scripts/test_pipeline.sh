#!/usr/bin/env bash
# =============================================================================
# test_pipeline.sh - one-command end-to-end test of the Guarded Swarms pipeline
#
# Launches the intruder, the sensing layer and the TB-CSPN coordination layer
# against an already-running coastal scenario, waits for the chain to raise a
# ConfirmedThreat, issues the supervisor authorisation automatically, and
# reports whether an assigned vehicle actually moved.
#
# It does NOT launch the scenario itself (that needs the Gazebo GUI and its own
# terminal). Start the scenario first:
#
#     make demo-coastal        # terminal 1, leave running
#     ./scripts/test_pipeline.sh   # terminal 2, does everything else
#
# Everything this script starts is torn down on exit, so a re-run is clean.
# =============================================================================
set -o pipefail

cd "$(dirname "$0")/.." || exit 1
source install/setup.bash

# --- tunables ---------------------------------------------------------------
INTRUDER_DELAY="${INTRUDER_DELAY:-8.0}"    # s before the intruder moves
INTRUDER_SPEED="${INTRUDER_SPEED:-3.0}"    # m/s, slow = wide detection window
AUTH_TARGET="${AUTH_TARGET:-intruder}"
SUPERVISOR="${SUPERVISOR:-supervisor_luca}"
THREAT_TIMEOUT="${THREAT_TIMEOUT:-90}"     # s to wait for a ConfirmedThreat

PIDS=()
cleanup() {
  echo
  echo "[test] tearing down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null
  done
  wait 2>/dev/null
  echo "[test] done."
}
trap cleanup EXIT INT TERM

echo "[test] launching intruder (delay ${INTRUDER_DELAY}s, speed ${INTRUDER_SPEED} m/s)..."
ros2 launch guarded_swarms_bringup intruder.launch.py \
  start_delay_s:="${INTRUDER_DELAY}" speed_mps:="${INTRUDER_SPEED}" \
  >/tmp/gs_intruder.log 2>&1 &
PIDS+=($!)

echo "[test] launching sensing layer..."
ros2 launch guarded_swarms_sensing sensing.launch.py \
  >/tmp/gs_sensing.log 2>&1 &
PIDS+=($!)

echo "[test] launching TB-CSPN layer (T1-T7)..."
ros2 launch guarded_swarms_tbcspn tbcspn.launch.py \
  >/tmp/gs_tbcspn.log 2>&1 &
PIDS+=($!)

# --- wait for a ConfirmedThreat --------------------------------------------
echo "[test] waiting for a ConfirmedThreat (up to ${THREAT_TIMEOUT}s)..."
deadline=$(( SECONDS + THREAT_TIMEOUT ))
got_threat=0
while (( SECONDS < deadline )); do
  # one line off /interp_tokens, non-blocking-ish
  line=$(timeout 3 ros2 topic echo /interp_tokens --field label --once 2>/dev/null)
  if [[ "$line" == *ConfirmedThreat* ]]; then
    got_threat=1
    break
  fi
done

if (( got_threat == 0 )); then
  echo "[test] FAIL: no ConfirmedThreat within ${THREAT_TIMEOUT}s."
  echo "[test] check /tmp/gs_sensing.log and /tmp/gs_tbcspn.log"
  exit 1
fi
echo "[test] ConfirmedThreat is up."

# --- record positions, authorise, record again -----------------------------
pose() { gz model -m "$1" -p 2>/dev/null | grep -A1 Pose | tail -1 | tr -d ' []'; }

before_uav0=$(pose x500_lidar_front_0)
before_uav1=$(pose x500_lidar_front_1)
before_ugv=$(pose r1_rover_2)

echo "[test] authorising interception of '${AUTH_TARGET}' as '${SUPERVISOR}'..."
ros2 topic pub --once /auth_tokens guarded_swarms_msgs/msg/SupervisorAuth \
  "{target_id: '${AUTH_TARGET}', authorised_by: '${SUPERVISOR}', decision: 'authorise', ttl_s: 15.0}" \
  >/dev/null 2>&1

echo "[test] letting the vehicles react (10s)..."
sleep 10

after_uav0=$(pose x500_lidar_front_0)
after_uav1=$(pose x500_lidar_front_1)
after_ugv=$(pose r1_rover_2)

moved() {
  # args: label before after  -> prints MOVED/still and the two poses
  local label="$1" b="$2" a="$3"
  if [[ "$b" == "$a" ]]; then
    echo "  $label: still   $a"
  else
    echo "  $label: MOVED   $b  ->  $a"
  fi
}

echo
echo "[test] === result ==="
moved "UAV0" "$before_uav0" "$after_uav0"
moved "UAV1" "$before_uav1" "$after_uav1"
moved "UGV " "$before_ugv"  "$after_ugv"
echo
echo "[test] dispatch log:"
grep -h "Dispatched\|RELEASED\|locked on\|observing from" /tmp/gs_tbcspn.log 2>/dev/null | tail -5
echo
echo "[test] leaving everything running so you can watch. Ctrl-C to tear down."
# keep the launches alive until the user is done looking
wait
