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
INTRUDER_SPEED="${INTRUDER_SPEED:-1.5}"    # m/s, slow = wide detection window
                                           # (slow enough that all sensor
                                           # modalities coincide in T5's fusion
                                           # window even under bag-record load)
AUTH_TARGET="${AUTH_TARGET:-intruder}"
SUPERVISOR="${SUPERVISOR:-supervisor_luca}"
export EO_DELAY_S="${EO_DELAY_S:-0}"       # seconds to delay EO delivery;
                                           # >threat TTL reproduces the stale-EO
                                           # counterfactual (C2) of the paper.
EO_ENABLED="${EO_ENABLED:-true}"          # set false to reproduce the
                                           # "EO confirmation unavailable in
                                           # the fusion window" counterfactual
                                           # (C2): CandidateTarget forms but
                                           # is never promoted to
                                           # ConfirmedThreat.
export RF_LABEL="${RF_LABEL:-LikelyDroneLink}"   # T2's emitted label; set to
                                           # LikelyCivilianTraffic to reproduce
                                           # the conflict counterfactual (C3)
EXPECT_THREAT="${EXPECT_THREAT:-yes}"      # yes | no. no = do not wait for a
                                           # ConfirmedThreat (it must NOT come,
                                           # as in the C3 conflict run); instead
                                           # let the pipeline run for OBSERVE_S
                                           # and just record.
OBSERVE_S="${OBSERVE_S:-90}"               # seconds to let a no-threat run breathe
DECISION="${DECISION:-authorise}"        # authorise | deny
                                           # deny reproduces the "authorisation
                                           # withheld" counterfactual (Sec 5.3):
                                           # the threat forms but no mission is
                                           # released.
THREAT_TIMEOUT="${THREAT_TIMEOUT:-150}"    # s to wait for a ConfirmedThreat
                                           # (raised: a slower intruder takes
                                           # longer to reach full coverage)

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
  eo:="${EO_ENABLED}" \
  >/tmp/gs_sensing.log 2>&1 &
PIDS+=($!)

echo "[test] launching TB-CSPN layer (T1-T7)..."
# RF_LABEL is exported above; tbcspn.launch.py reads it from the environment
# (a launch-argument substitution inside a parameter dict did not resolve).
ros2 launch guarded_swarms_tbcspn tbcspn.launch.py \
  >/tmp/gs_tbcspn.log 2>&1 &
PIDS+=($!)

# --- wait for a ConfirmedThreat --------------------------------------------
# In a counterfactual run where the threat must NOT form (EXPECT_THREAT=no, the
# C3 conflict case), waiting for it would be waiting for something that is
# correctly never produced. Instead let the pipeline run for OBSERVE_S so the
# sensors and interpretations do their work, then record and finish. The
# counterfactual check on the bag then confirms the forbidden token is absent.
if [[ "$EXPECT_THREAT" == "no" ]]; then
  echo "[test] counterfactual run: NOT expecting a ConfirmedThreat."
  echo "[test] letting the pipeline run for ${OBSERVE_S}s..."
  sleep "${OBSERVE_S}"
  echo "[test] done observing; the bag holds the (non-)result."
  echo "[test] leaving everything running so you can watch. Ctrl-C to tear down."
  wait
  exit 0
fi

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

echo "[test] supervisor decision '${DECISION}' for '${AUTH_TARGET}' as '${SUPERVISOR}'..."
# Publish the authorisation repeatedly for ~2s rather than with --once.
# A single --once publisher is created and destroyed immediately; with RELIABLE
# QoS the DDS handshake with T6's subscription may not complete in time and the
# message is lost. Publishing at 5 Hz for 2s guarantees delivery. T6 releases
# the mission once and ignores repeats for the same live threat.
# Publish with transient_local durability, matching T6's subscription, so the
# authorisation is delivered even if T6's DDS handshake is not yet complete when
# we publish. A short repeated burst on top removes any residual timing gap.
ros2 topic pub --rate 5 --times 10 --qos-durability transient_local \
  /supervisor_auth guarded_swarms_msgs/msg/SupervisorAuth \
  "{target_id: '${AUTH_TARGET}', authorised_by: '${SUPERVISOR}', decision: '${DECISION}', ttl_s: 15.0}" \
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