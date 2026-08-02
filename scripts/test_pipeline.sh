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
# Attack vector: ingress geometry of the intruder, chosen from the sensor
# coverage map. "frontal" is the well-covered sea front; "east-deep" and "rear"
# cross the sparse zones so the detection modality richness degrades. Used by
# the Group 4 (detection-by-vector) metric. Default frontal = the paper's
# nominal coastal ingress.
ATTACK_VECTOR="${ATTACK_VECTOR:-frontal}"
case "$ATTACK_VECTOR" in
  frontal)   IN_X=0.0;   IN_Y=180.0;  TG_X=0.0; TG_Y=10.0 ;;
  east-deep) IN_X=250.0; IN_Y=-120.0; TG_X=0.0; TG_Y=10.0 ;;
  rear)      IN_X=0.0;   IN_Y=-200.0; TG_X=0.0; TG_Y=-120.0 ;;
  demo)      IN_X=-24.0; IN_Y=180.0;  TG_X=-24.0; TG_Y=20.0; IN_Z=2.0; TG_Z=2.0 ;;
  # 'demo' is the end-to-end demonstration scenario, not a measurement vector.
  # The intruder ingresses down the EO camera's line of sight (the EO sits on
  # UAV0 at (-24,-24) looking north) and holds station on a coastal objective
  # at (-24, 20), squarely inside the 30-deg EO cone. The low altitude (3 m)
  # matters: the EO camera is pitched down 20 deg to watch the sea surface, so a
  # high-flying target passes ABOVE its vertical field of view; a low, sea-
  # skimming ingress stays inside it, and the EO then confirms continuously.
  # Once it arrives and holds, the ConfirmedThreat is stable rather than a brief
  # pass-through -- which is what a live console demonstration needs. This is a
  # realistic hostile profile (a low target penetrating to a coastal objective
  # and loitering over it), and it changes only the intruder's path, never the
  # sensor models, so the Group 4 detection metrics are untouched.
  *) echo "[test] unknown ATTACK_VECTOR '$ATTACK_VECTOR' (frontal|east-deep|rear|demo)"; exit 1 ;;
esac
                                           # (slow enough that all sensor
                                           # modalities coincide in T5's fusion
                                           # window even under bag-record load)
AUTH_TARGET="${AUTH_TARGET:-intruder}"
SUPERVISOR="${SUPERVISOR:-supervisor_luca}"
export EO_DELAY_S="${EO_DELAY_S:-0}"       # seconds to delay EO delivery;
                                           # >threat TTL reproduces the stale-EO
                                           # counterfactual (C2) of the paper.
RADAR_ENABLED="${RADAR_ENABLED:-true}"     # per-modality enables for the
RF_ENABLED="${RF_ENABLED:-true}"           # loss-of-modality metric (Group 4b):
ACOUSTIC_ENABLED="${ACOUSTIC_ENABLED:-true}"  # drop one and measure the degrade.
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
MANUAL_AUTH="${MANUAL_AUTH:-0}"          # 1 = wait for the supervisor to
                                         # authorise from the console/browser
                                         # instead of publishing it automatically
                                           # deny reproduces the "authorisation
                                           # withheld" counterfactual (Sec 5.3):
                                           # the threat forms but no mission is
                                           # released.
THREAT_TIMEOUT="${THREAT_TIMEOUT:-30}"     # s to wait for a ConfirmedThreat
                                           # (raised: a slower intruder takes
                                           # longer to reach full coverage)

PIDS=()
cleanup() {
  echo
  echo "[test] tearing down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null
  done
  # Killing a `ros2 launch` process does NOT reliably kill the nodes it spawned:
  # they are reparented and survive as orphans, which then run alongside the
  # next launch and produce a duplicated sensing chain (doubled observation
  # counts, overlapping timestamps). Explicitly sweep the nodes each launch
  # starts, so every run ends from a clean slate. Names are specific to this
  # pipeline; nothing else in the workspace shares them.
  for n in radar_agent_node rf_agent_node acoustic_agent_node eo_agent_node \
           interpretation_node candidate_transition_node \
           mission_transition_node dispatch_transition_node \
           uav_worker_node ugv_worker_node intruder_node; do
    pkill -f "$n" 2>/dev/null
  done
  pkill -f "sensing.launch" 2>/dev/null
  pkill -f "tbcspn.launch" 2>/dev/null
  pkill -f "intruder.launch" 2>/dev/null
  wait 2>/dev/null
  echo "[test] done."
}
trap cleanup EXIT INT TERM

echo "[test] launching intruder (vector ${ATTACK_VECTOR}, delay ${INTRUDER_DELAY}s, speed ${INTRUDER_SPEED} m/s)..."
ros2 launch guarded_swarms_bringup intruder.launch.py \
  start_delay_s:="${INTRUDER_DELAY}" speed_mps:="${INTRUDER_SPEED}" \
  ingress_x:="${IN_X}" ingress_y:="${IN_Y}" ingress_z:="${IN_Z:-15.0}" \
  target_x:="${TG_X}" target_y:="${TG_Y}" target_z:="${TG_Z:-15.0}" \
  >/tmp/gs_intruder.log 2>&1 &
PIDS+=($!)

echo "[test] launching sensing layer..."
ros2 launch guarded_swarms_sensing sensing.launch.py \
  radar:="${RADAR_ENABLED}" rf:="${RF_ENABLED}" \
  acoustic:="${ACOUSTIC_ENABLED}" eo:="${EO_ENABLED}" \
  >/tmp/gs_sensing.log 2>&1 &
PIDS+=($!)

echo "[test] launching TB-CSPN layer (T1-T7)..."
# RF_LABEL is exported above; tbcspn.launch.py reads it from the environment
# (a launch-argument substitution inside a parameter dict did not resolve).
ros2 launch guarded_swarms_tbcspn tbcspn.launch.py \
  >/tmp/gs_tbcspn.log 2>&1 &
PIDS+=($!)

# Start watching /mission_tokens IMMEDIATELY, in the background, writing every
# released mission_id to a file. This must begin now -- not later in the manual
# phase -- because the ConfirmedThreat can form while we are still waiting for
# it, and the supervisor may authorise the instant the console arms, before the
# script reaches the manual-decision phase. Watching from the start means no
# release is ever missed, whatever the timing of the human click.
: > /tmp/gs_missions.log
if [ "$MANUAL_AUTH" = "1" ]; then
  ( stdbuf -oL ros2 topic echo /mission_tokens --field mission_id 2>/dev/null \
      | stdbuf -oL grep -v '^---$' \
      | while IFS= read -r mid; do
          [ -z "$mid" ] && continue
          echo "$(date +%H:%M:%S) $mid" >> /tmp/gs_missions.log
        done ) &
  MISSION_WATCH_PID=$!
  PIDS+=($MISSION_WATCH_PID)
fi

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

if [ "$MANUAL_AUTH" = "1" ]; then
  # Manual mode: the supervisor authorises from the console/browser. The script
  # does not publish the authorisation. Instead it follows the TB-CSPN log in
  # real time and prints every mission release the instant it appears, so the
  # moment you press Authorise in the panel you see the swarm act here -- no
  # blind wait, no fragile before/after counting. Following the log with tail -f
  # is immune to the QoS/DDS quirks that make `ros2 topic echo` unreliable from
  # a second process, and it catches a release whenever it happens, even if you
  # authorise while the threat is still forming.
  #
  # The intruder keeps holding station in the EO cone, so ConfirmedThreat keeps
  # streaming and the panel stays armed until you decide. Press Ctrl-C when done.
  echo "[test] MANUAL_AUTH: the console is live. Open console/decision_panel.html."
  echo "[test] Press Authorise in the panel; each released mission appears below"
  echo "[test] the instant T6 fires. Ctrl-C to finish."
  echo "[test] ----------------------------------------------------------------"
  # The background watcher started at pipeline launch has been recording every
  # release to /tmp/gs_missions.log since before the ConfirmedThreat even
  # formed. Show anything already captured (a mission authorised while the
  # threat was forming is not lost), then follow the file for new ones. This is
  # what makes the feedback immediate regardless of WHEN you clicked Authorise.
  if [ -s /tmp/gs_missions.log ]; then
    while IFS= read -r rec; do
      echo "[swarm] mission released: ${rec#* }  (authorised from the console)"
    done < /tmp/gs_missions.log
  fi
  stdbuf -oL tail -n0 -f /tmp/gs_missions.log 2>/dev/null | \
    while IFS= read -r rec; do
      echo "[swarm] mission released: ${rec#* }  (authorised from the console)"
    done
  # tail -f runs until the user Ctrl-C's; the trap tears everything down.
else

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
fi

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