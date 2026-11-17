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
# test_pipeline.sh - one-command end-to-end test of the Guarded Swarms pipeline
#
# Launches the intruder, the sensing layer, the TB-CSPN coordination layer and
# the scripted supervisor against an already-running coastal scenario, waits
# for the chain to raise a ConfirmedThreat, lets the supervisor decide, and
# reports whether an assigned vehicle actually moved. With MANUAL_AUTH=1 the
# decision comes from the supervisor console instead.
#
# It does NOT launch the scenario itself (that needs the Gazebo GUI and its own
# terminal). Start the scenario first:
#
#     make demo-coastal            # terminal 1, leave running
#     ./scripts/pipeline/test_pipeline.sh  # terminal 2, does everything else
#
# Everything this script starts, and only that, is torn down on exit. The run
# refuses to start if the scenario is down or an earlier run left processes
# behind. It stops if the intruder's ground truth has not exactly one source,
# or does not arrive after the launch or before the result: the intruder
# publishes it on simulated time (see run_guards.sh). It stays up after the
# report until Ctrl-C, or ends on its own with STAY_UP=0. Exit codes: 0 report
# done (STAY_UP=0), 1 no ConfirmedThreat within THREAT_TIMEOUT, 2 refused to
# start, 3 stopped by a guard; Ctrl-C ends it with 130.
# ==============================================================================
set -o pipefail
cd "$(dirname "$0")/../.." || exit 1
source install/setup.bash
source scripts/pipeline/run_guards.sh

# --- tunables ---------------------------------------------------------------
INTRUDER_DELAY="${INTRUDER_DELAY:-8.0}"    # s before the intruder moves
INTRUDER_SPEED="${INTRUDER_SPEED:-6.0}"    # m/s, slow = wide detection window

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

# Seconds to delay EO delivery; a value above the threat TTL reproduces the
# stale-EO counterfactual (C2) of the paper.
export EO_DELAY_S="${EO_DELAY_S:-0}"

# Per-modality enables for the loss-of-modality metric (Group 4b): drop one and
# measure the degrade. Setting EO_ENABLED=false reproduces the "EO confirmation
# unavailable in the fusion window" counterfactual (C2): CandidateTarget forms
# but is never promoted to ConfirmedThreat.
RADAR_ENABLED="${RADAR_ENABLED:-true}"
RF_ENABLED="${RF_ENABLED:-true}"
ACOUSTIC_ENABLED="${ACOUSTIC_ENABLED:-true}"
EO_ENABLED="${EO_ENABLED:-true}"

# Seed of the run's random draws (sensor noise, missed detections, false
# alarms); each sensing agent derives its own seed from it. Drawn at random
# when unset, and printed, so that any run can be repeated.
export SEED="${SEED:-$(( (RANDOM << 15 | RANDOM) + 1 ))}"

# T2's emitted label; set to LikelyCivilianTraffic to reproduce the conflict
# counterfactual (C3).
export RF_LABEL="${RF_LABEL:-LikelyDroneLink}"

# The synchronisation window of T3 alone, in seconds. Empty: T3 shares
# sync_threshold_s with T5 and T6 (3 s). Exported, because tbcspn.launch.py
# reads it from the environment, as it reads RF_LABEL.
export T3_WINDOW_S="${T3_WINDOW_S:-}"
if [ -n "$T3_WINDOW_S" ] && ! [[ "$T3_WINDOW_S" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "[test] T3_WINDOW_S must be a number of seconds, got '$T3_WINDOW_S'."
  exit 2
fi

# The number of UAVs of the scenario, as given to scripts/sim/coastal_up.sh
# (2 by default, as in 'make demo-coastal'). Exported, because tbcspn.launch.py
# reads it from the environment: T7 dispatches to the first N_UAVS UAVs of the
# fleet.
export N_UAVS="${N_UAVS:-2}"
if ! [[ "$N_UAVS" =~ ^[0-9]+$ ]]; then
  echo "[test] N_UAVS must be a whole number, got '$N_UAVS'."
  exit 2
fi

# The waits of a run are in simulated time: with more vehicles the simulation
# runs slower than real time, and a wait on the real clock would then cover
# less of the run. scripts/pipeline/sim_sleep.py waits on /clock. A clock that
# does not advance for SIM_STALL_S real seconds ends the run, whose data cannot
# be used (exit 3).
SIM_STALL_S=30
sim_wait() {
  python3 scripts/pipeline/sim_sleep.py "$1" --stall "$SIM_STALL_S"
  case $? in
    0) ;;
    130) exit 130 ;;
    *) echo "[test] GUARD: the simulated time stopped during a wait of ${1}s; the run cannot be used (exit 3)."
       exit 3 ;;
  esac
}

# yes | no. no = do not wait for a ConfirmedThreat (it must NOT come, as in the
# C3 conflict run); instead let the pipeline run for OBSERVE_S and just record.
EXPECT_THREAT="${EXPECT_THREAT:-yes}"
OBSERVE_S="${OBSERVE_S:-90}"   # simulated seconds

# The scripted supervisor's decision: authorise | deny | none. deny reproduces
# the "authorisation withheld" counterfactual (Sec 5.3): the threat forms but no
# mission is released. none issues no decision at all. Exported, because
# supervisor.launch.py reads these three from the environment.
export DECISION="${DECISION:-authorise}"
# Supervisor decision time, in simulated seconds from the first ConfirmedThreat.
export AUTH_DELAY_S="${AUTH_DELAY_S:-0}"
# Validity of the decision, in seconds.
export AUTH_TTL_S="${AUTH_TTL_S:-15}"

# 1 = the supervisor decides from the console/browser, and the scripted
# supervisor is not started.
MANUAL_AUTH="${MANUAL_AUTH:-0}"

# s to wait for a ConfirmedThreat (a slower intruder takes longer to reach full
# coverage).
THREAT_TIMEOUT="${THREAT_TIMEOUT:-60}"

# Simulated seconds to let the vehicles react after an automatic authorisation.
REACT_S="${REACT_S:-10}"

# none | obstacle. obstacle places one mission directly on the dispatch topic
# after the decision (scripts/pipeline/publish_mission.py), to exercise the UAV
# safety layer. FORGE_X/FORGE_Y is the target, the centre of a building in the
# world frame, so the UAV dispatched to it flies toward that building.
FORGE_MISSION="${FORGE_MISSION:-none}"
FORGE_X="${FORGE_X:--22.53}"
FORGE_Y="${FORGE_Y:--47.07}"

# none | ghost. ghost runs scripts/pipeline/publish_observations.py, which puts
# forged radar, RF and EO observations of a target that is not there on
# /obs_tokens. Use it with the four sensing agents off, so the forged stream is
# the only evidence: the chain fuses it into a ConfirmedThreat, and the mission
# forms only if the supervisor authorises it. Started before the threat wait,
# below.
FORGE_OBS="${FORGE_OBS:-none}"

# Metres a vehicle must travel between the two pose snapshots to count as
# MOVED. The hover alone jitters by about 0.1 m.
MOVE_THRESHOLD_M="${MOVE_THRESHOLD_M:-0.5}"

# 1 = stay up after the report until Ctrl-C, to watch the vehicles; 0 = tear
# down and exit with 0 once the report is printed (used by the campaigns).
STAY_UP="${STAY_UP:-1}"

PIDS=()

# --- pre-run checks ----------------------------------------------------------
# Before anything is started, so a refused run leaves nothing behind.
guard_scenario_running || exit 2
guard_no_leftovers || exit 2
# One PX4 instance per UAV and one for the UGV: otherwise T7 would dispatch to
# a fleet that is not the one flying.
px4_running=$(pgrep -cx px4)
if [ "$px4_running" -ne $((N_UAVS + 1)) ]; then
  echo "[test] the scenario runs ${px4_running} PX4 instances; N_UAVS=${N_UAVS} needs $((N_UAVS + 1))."
  exit 2
fi

# Tear down everything this script started, and only that: the scenario's own
# nodes (vehicle workers, safety boards, bridges) belong to demo-coastal and
# stay up.
#
# Killing a `ros2 launch` process does NOT reliably kill the nodes it spawned:
# they are reparented and survive as orphans, which then run alongside the next
# launch and produce a duplicated sensing chain (doubled observation counts,
# overlapping timestamps). stop_pipeline_processes therefore also sweeps the
# nodes by name, and checks that nothing survives.
cleanup() {
  # Ignore a second Ctrl-C: an interrupted teardown would leave nodes running.
  trap '' INT TERM
  echo
  echo "[test] tearing down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null
  done
  stop_pipeline_processes
  wait 2>/dev/null
  echo "[test] done."
}
# The teardown runs once, on exit; Ctrl-C and SIGTERM only trigger the exit.
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "[test] launching intruder (vector ${ATTACK_VECTOR}, delay ${INTRUDER_DELAY}s, speed ${INTRUDER_SPEED} m/s)..."
ros2 launch guarded_swarms_bringup intruder.launch.py \
  start_delay_s:="${INTRUDER_DELAY}" speed_mps:="${INTRUDER_SPEED}" \
  ingress_x:="${IN_X}" ingress_y:="${IN_Y}" ingress_z:="${IN_Z:-15.0}" \
  target_x:="${TG_X}" target_y:="${TG_Y}" target_z:="${TG_Z:-15.0}" \
  >/tmp/gs_intruder.log 2>&1 &
PIDS+=($!)

echo "[test] launching sensing layer (seed ${SEED})..."
ros2 launch guarded_swarms_sensing sensing.launch.py \
  radar:="${RADAR_ENABLED}" rf:="${RF_ENABLED}" \
  acoustic:="${ACOUSTIC_ENABLED}" eo:="${EO_ENABLED}" \
  >/tmp/gs_sensing.log 2>&1 &
PIDS+=($!)

echo "[test] launching TB-CSPN layer (T1-T7), ${N_UAVS} UAVs${T3_WINDOW_S:+, T3 window ${T3_WINDOW_S} s}..."
# RF_LABEL, T3_WINDOW_S and N_UAVS are exported above; tbcspn.launch.py reads
# them from the environment (a launch-argument substitution inside a parameter
# dict did not resolve).
ros2 launch guarded_swarms_tbcspn tbcspn.launch.py \
  >/tmp/gs_tbcspn.log 2>&1 &
PIDS+=($!)

# In automatic mode the scripted supervisor issues the T6 decision. It runs for
# the whole test, so its decision cannot be lost. In manual mode the console
# decides instead.
if [ "$MANUAL_AUTH" != "1" ]; then
  echo "[test] launching scripted supervisor ('${DECISION}', ${AUTH_DELAY_S}s after the first ConfirmedThreat)..."
  ros2 launch guarded_swarms_supervisor supervisor.launch.py \
    >/tmp/gs_supervisor.log 2>&1 &
  PIDS+=($!)
fi

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

# One intruder only: a second source of ground truth would mix two trajectories
# in the data.
guard_single_ground_truth || exit 3
# Its ground truth must also arrive. The intruder publishes it on simulated
# time: a run whose nodes receive no /clock stays frozen, and would only time
# out waiting for a threat.
guard_ground_truth_flowing || exit 3

# Ground-truth position "x,y,z" of a Gazebo model, or empty if not found.
pose() {
  gz model -m "$1" -p 2>/dev/null | grep -A1 Pose | tail -1 | tr -d '[]' \
    | awk '{ if (NF >= 3) printf "%s,%s,%s", $1, $2, $3 }'
}

# Starting poses, taken now: the intruder is still far from the sensors, so no
# vehicle has a task yet. The three gz calls take several seconds, and after
# the ConfirmedThreat a mission may already be flying.
before_uav0=$(pose x500_lidar_front_0)
before_uav1=$(pose x500_lidar_front_1)
before_ugv=$(pose r1_rover_2)

# --- wait for a ConfirmedThreat --------------------------------------------
# In a counterfactual run where the threat must NOT form (EXPECT_THREAT=no, the
# C3 conflict case), waiting for it would be waiting for something that is
# correctly never produced. Instead let the pipeline run for OBSERVE_S so the
# sensors and interpretations do their work, then record and finish. The
# counterfactual check on the bag then confirms the forbidden token is absent.
if [[ "$EXPECT_THREAT" == "no" ]]; then
  echo "[test] counterfactual run: NOT expecting a ConfirmedThreat."
  echo "[test] letting the pipeline run for ${OBSERVE_S}s of simulated time..."
  sim_wait "${OBSERVE_S}"
  # The ground truth must still arrive: an observation that the simulated time
  # stopped reaching is not a result.
  guard_ground_truth_flowing || exit 3
  echo "[test] done observing; the bag holds the (non-)result."
  if [ "$STAY_UP" = "1" ]; then
    echo "[test] leaving everything running so you can watch. Ctrl-C to tear down."
    wait
  fi
  exit 0
fi

# Forged observations: start the injector now, before the wait, so the forged
# ConfirmedThreat forms from injected evidence alone (run this configuration
# with the four sensing agents off). It streams in the background through the
# supervisor's decision and exits on its own; the wait below then detects the
# threat it creates, exactly as it would a real one.
if [ "$FORGE_OBS" != none ]; then
  echo "[test] FORGE_OBS=${FORGE_OBS}: injecting forged observations on /obs_tokens..."
  python3 scripts/pipeline/publish_observations.py --target-id ghost-1 \
    >/tmp/gs_forge_obs.log 2>&1 &
  PIDS+=($!)
fi

echo "[test] waiting for a ConfirmedThreat (up to ${THREAT_TIMEOUT}s)..."
got_threat=0
# Stream /interp_tokens continuously and stop at the first ConfirmedThreat.
# (A per-message --once in a loop samples ONE arbitrary token from the mixed
# stream -- usually a PossibleUAV or CandidateTarget -- and only rarely lands
# on a ConfirmedThreat, so it misses threats that are in fact present. A
# continuous grep sees every token and cannot miss it.)
#
# The watch runs in the background, and the script waits for it: timeout puts
# itself in a process group of its own, which Ctrl-C does not reach, so in the
# foreground it would hold a Ctrl-C back for up to THREAT_TIMEOUT. The wait
# builtin lets Ctrl-C through at once, and the teardown then stops the watch.
timeout "${THREAT_TIMEOUT}" bash -c '
    stdbuf -oL ros2 topic echo /interp_tokens --field label 2>/dev/null \
      | grep -q -m1 ConfirmedThreat
  ' &
THREAT_WATCH_PID=$!
PIDS+=($THREAT_WATCH_PID)
if wait "$THREAT_WATCH_PID"; then
  got_threat=1
fi
if (( got_threat == 0 )); then
  # No threat counts only if the simulated time reached the run to the end.
  guard_ground_truth_flowing || exit 3
  echo "[test] FAIL: no ConfirmedThreat within ${THREAT_TIMEOUT}s."
  echo "[test] check /tmp/gs_sensing.log and /tmp/gs_tbcspn.log"
  # With forged observations the ConfirmedThreat is expected to form from the
  # injected stream; its absence is a failed injection, not a valid outcome, so
  # stop the run (exit 3) and let the campaign repeat it with the same seed.
  [ "$FORGE_OBS" != none ] && exit 3
  exit 1
fi
echo "[test] ConfirmedThreat is up."

# --- the decision, then the vehicles' reaction -----------------------------

if [ "$MANUAL_AUTH" = "1" ]; then
  # Manual mode: the supervisor authorises from the console/browser. The script
  # does not publish the authorisation. Instead it follows the release log in
  # real time and prints every mission the instant it appears, so the moment you
  # press Authorise in the panel you see the swarm act here -- no blind wait, no
  # fragile before/after counting. Following a file with tail -f is immune to
  # the QoS/DDS quirks that make `ros2 topic echo` unreliable from a second
  # process, and it catches a release whenever it happens.
  echo "[test] MANUAL_AUTH: the console is live. Open console/decision_panel.html."
  echo "[test] Press Authorise in the panel; each released mission appears below"
  echo "[test] the instant T6 fires. Ctrl-C to finish."
  echo "[test] ----------------------------------------------------------------"
  # The background watcher started at pipeline launch has been recording every
  # release since before the ConfirmedThreat even formed. Show anything already
  # captured (a mission authorised while the threat was forming is not lost),
  # then follow the file for new ones.
  if [ -s /tmp/gs_missions.log ]; then
    while IFS= read -r rec; do
      echo "[swarm] mission released: ${rec#* }  (authorised from the console)"
    done < /tmp/gs_missions.log
  fi
  stdbuf -oL tail -n0 -f /tmp/gs_missions.log 2>/dev/null | \
    while IFS= read -r rec; do
      echo "[swarm] mission released: ${rec#* }  (authorised from the console)"
    done
else
  # The scripted supervisor, running since the start, decides on its own
  # AUTH_DELAY_S simulated seconds after the first ConfirmedThreat. The script
  # only waits for the decision and for the vehicles' reaction.
  echo "[test] scripted supervisor: '${DECISION}' ${AUTH_DELAY_S}s after the first ConfirmedThreat."
  if [ "$FORGE_MISSION" != none ]; then
    echo "[test] FORGE_MISSION=${FORGE_MISSION}: placing a mission on the dispatch topic (${FORGE_X}, ${FORGE_Y})..."
    # A target_id with no live track: the honest worker then flies to the given
    # position (the building) instead of following the real intruder.
    if ! python3 scripts/pipeline/publish_mission.py --target-id forged-1 \
         --x "${FORGE_X}" --y "${FORGE_Y}" --z 12.0 --ttl 30.0; then
      echo "[test] the forged mission was not dispatched; stopping the run (exit 3)."
      exit 3
    fi
  fi
  echo "[test] letting the vehicles react (${AUTH_DELAY_S}s + ${REACT_S}s of simulated time)..."
  sim_wait "$(LC_ALL=C awk -v a="${AUTH_DELAY_S}" -v b="${REACT_S}" 'BEGIN { print a + b }')"
fi

# The simulated time must have reached the run through the decision and the
# reaction of the vehicles.
guard_ground_truth_flowing || exit 3

after_uav0=$(pose x500_lidar_front_0)
after_uav1=$(pose x500_lidar_front_1)
after_ugv=$(pose r1_rover_2)

# Report whether a vehicle moved more than MOVE_THRESHOLD_M between the
# before/after snapshots.
moved() {
  local label="$1" b="$2" a="$3" d
  if [ -z "$b" ] || [ -z "$a" ]; then
    echo "  $label: unknown (no pose from Gazebo)"
    return
  fi
  d=$(LC_ALL=C awk -v b="$b" -v a="$a" 'BEGIN {
        split(b, p, ","); split(a, q, ",")
        printf "%.1f", sqrt((q[1]-p[1])^2 + (q[2]-p[2])^2 + (q[3]-p[3])^2) }')
  if LC_ALL=C awk -v d="$d" -v t="$MOVE_THRESHOLD_M" 'BEGIN { exit !(d > t) }'; then
    echo "  $label: MOVED ${d} m   ($b -> $a)"
  else
    echo "  $label: still (${d} m)   $a"
  fi
}

echo
echo "[test] === result ==="
moved "UAV0" "$before_uav0" "$after_uav0"
moved "UAV1" "$before_uav1" "$after_uav1"
moved "UGV " "$before_ugv"  "$after_ugv"
echo
echo "[test] supervisor log:"
grep -h "Decision for" /tmp/gs_supervisor.log 2>/dev/null | tail -5
echo
echo "[test] dispatch log:"
grep -h "Dispatched\|RELEASED\|locked on\|observing from" /tmp/gs_tbcspn.log 2>/dev/null | tail -5
echo
[ "$STAY_UP" = "1" ] || exit 0
echo "[test] leaving everything running so you can watch. Ctrl-C to tear down."
wait
